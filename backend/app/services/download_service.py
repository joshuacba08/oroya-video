from __future__ import annotations

import hashlib
import os
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import DownloadAlreadyRunningError
from app.core.logging import get_logger

logger = get_logger(__name__)
DOWNLOAD_CHUNK_SIZE = 1024 * 256
DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass
class DownloadState:
    status: str = "idle"  # idle | downloading | completed | failed
    bytes_done: int = 0
    bytes_total: int | None = None
    percent: float = 0.0
    error_code: str | None = None
    error_message: str | None = None


_registry: dict[str, DownloadState] = {}
_lock = threading.Lock()


def get_download_state(key: str) -> DownloadState:
    with _lock:
        state = _registry.get(key)
        if state is None:
            return DownloadState()
        return DownloadState(**state.__dict__)


def reset_download_state(key: str) -> None:
    with _lock:
        _registry.pop(key, None)


def start_download(
    key: str,
    url: str,
    dest_path: Path,
    *,
    sha256: str | None = None,
    on_complete: Callable[[], None] | None = None,
) -> DownloadState:
    with _lock:
        current = _registry.get(key)
        if current is not None and current.status == "downloading":
            raise DownloadAlreadyRunningError()
        state = DownloadState(status="downloading")
        _registry[key] = state

    thread = threading.Thread(
        target=_run_download,
        args=(key, url, dest_path, sha256, on_complete),
        daemon=True,
        name=f"download-{key}",
    )
    thread.start()
    return get_download_state(key)


def _set_state(key: str, **changes: object) -> None:
    with _lock:
        state = _registry.get(key)
        if state is None:
            return
        for name, value in changes.items():
            setattr(state, name, value)


def _run_download(
    key: str,
    url: str,
    dest_path: Path,
    sha256: str | None,
    on_complete: Callable[[], None] | None,
) -> None:
    part_path = dest_path.with_name(f"{dest_path.name}.part")
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "oroya-video"})
        digest = hashlib.sha256()
        bytes_done = 0

        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_length = response.headers.get("Content-Length")
            bytes_total = int(content_length) if content_length else None
            _set_state(key, bytes_total=bytes_total)

            with open(part_path, "wb") as output:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    bytes_done += len(chunk)
                    percent = (
                        round(bytes_done / bytes_total * 100, 1)
                        if bytes_total
                        else 0.0
                    )
                    _set_state(key, bytes_done=bytes_done, percent=percent)

        if sha256 is not None and digest.hexdigest().lower() != sha256.lower():
            part_path.unlink(missing_ok=True)
            _set_state(
                key,
                status="failed",
                error_code="download_checksum_mismatch",
                error_message="Downloaded file failed the SHA256 integrity check.",
            )
            logger.warning("Download checksum mismatch: %s", key)
            return

        os.replace(part_path, dest_path)

        if on_complete is not None:
            try:
                on_complete()
            except Exception as exc:
                # La descarga terminó pero el paso posterior (extraer, registrar) falló:
                # no está instalado, así que no se puede reportar "completed".
                _set_state(
                    key,
                    status="failed",
                    error_code="download_post_process_failed",
                    error_message=str(exc)[:300] or "Downloaded file could not be installed.",
                )
                logger.exception("Download completion callback failed: %s", key)
                return

        _set_state(key, status="completed", percent=100.0)
        logger.info("Download completed: %s -> %s", key, dest_path)
    except Exception as exc:
        part_path.unlink(missing_ok=True)
        _set_state(
            key,
            status="failed",
            error_code="download_failed",
            error_message=str(exc)[:300] or "Download failed.",
        )
        logger.exception("Download failed: %s", key)
