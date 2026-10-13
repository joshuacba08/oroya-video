from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger

logger = get_logger(__name__)

# Sondeos de la UI (cada 1-10 s): en DEBUG, salvo que fallen o tarden.
POLLING_PATHS = ("/health", "/queue", "/system/gpu", "/app-state")
POLLING_SUFFIXES = ("/progress", "/events")
SLOW_REQUEST_MS = 1000


def _is_polling(method: str, path: str) -> bool:
    if method != "GET":
        return False
    return path.endswith(POLLING_PATHS) or path.endswith(POLLING_SUFFIXES)


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        request_id = getattr(
            request.state,
            "request_id",
            response.headers.get("X-Request-ID", request.headers.get("X-Request-ID", "-")),
        )
        level = logging.INFO
        if (
            _is_polling(request.method, request.url.path)
            and response.status_code < 400
            and duration_ms < SLOW_REQUEST_MS
        ):
            level = logging.DEBUG
        elif response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400 or duration_ms >= SLOW_REQUEST_MS:
            level = logging.WARNING
        logger.log(
            level,
            "access method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
