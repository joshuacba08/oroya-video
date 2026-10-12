"""Keep the local API reachable only by the Oroya Video UI on this machine.

The backend listens on 127.0.0.1, but a web page open in the user's browser can still reach
it: through DNS rebinding (a hostname that resolves to 127.0.0.1, sending a foreign Host) or
with "simple" cross-site POSTs, which CORS does not block (CORS only hides the response).
Either could, for example, start a multi-gigabyte AI install. This middleware rejects:

- any request whose Host is not a loopback name;
- state-changing requests coming from an origin outside `cors_origins`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.logging import get_logger

logger = get_logger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1", "testserver"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _hostname(host: str) -> str:
    host = host.strip().lower()
    if host.startswith("["):
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_origins = {origin.rstrip("/").lower() for origin in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        host = headers.get("host", "")
        if _hostname(host) not in LOOPBACK_HOSTS:
            await self._reject(send, scope, "forbidden_host", f"Host {host!r} is not allowed.")
            return

        if scope["method"].upper() not in SAFE_METHODS:
            origin = headers.get("origin", "").rstrip("/").lower()
            fetch_site = headers.get("sec-fetch-site", "")
            if origin and origin != "null" and origin not in self.allowed_origins:
                await self._reject(
                    send, scope, "forbidden_origin", f"Origin {origin!r} is not allowed."
                )
                return
            if (not origin or origin == "null") and fetch_site == "cross-site":
                await self._reject(
                    send, scope, "forbidden_origin", "Cross-site requests are not allowed."
                )
                return

        await self.app(scope, receive, send)

    async def _reject(self, send: Send, scope: Scope, error: str, message: str) -> None:
        logger.warning("Rejected %s %s: %s", scope["method"], scope["path"], message)
        body = json.dumps({"error": error, "message": message, "details": {}}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
