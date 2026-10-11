from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ProcessInfo:
    job_id: str
    process_id: int
    process_kind: str
    started_at: float
    process: subprocess.Popen[str] | None = None


_process_registry: dict[str, ProcessInfo] = {}
# Se activa al apagar el backend: las etapas ffmpeg dejan el job tal cual (la recuperación
# al arrancar lo marca `interrupted`) en vez de marcarlo como fallido.
_shutdown_requested = threading.Event()


def request_shutdown() -> None:
    _shutdown_requested.set()


def clear_shutdown() -> None:
    _shutdown_requested.clear()


def is_shutting_down() -> bool:
    return _shutdown_requested.is_set()


def register_process(
    job_id: str,
    process_id: int,
    process_kind: str,
    process: subprocess.Popen[str] | None = None,
) -> None:
    _process_registry[job_id] = ProcessInfo(
        job_id=job_id,
        process_id=process_id,
        process_kind=process_kind,
        started_at=time.time(),
        process=process,
    )
    logger.info("Process registered: %s %s", job_id, process_kind)


def unregister_process(job_id: str) -> None:
    if job_id in _process_registry:
        logger.info("Process unregistered: %s", job_id)
        _process_registry.pop(job_id, None)


def get_process_for_job(job_id: str) -> ProcessInfo | None:
    return _process_registry.get(job_id)


def terminate_process_for_job(job_id: str, timeout_seconds: int = 5) -> bool:
    process_info = _process_registry.get(job_id)
    if process_info is None or process_info.process is None:
        return False

    process = process_info.process
    if process.poll() is not None:
        unregister_process(job_id)
        return True

    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)
    unregister_process(job_id)
    logger.warning("Process terminated for job %s", job_id)
    return True


def terminate_all_processes(timeout_seconds: int = 5) -> int:
    terminated = 0
    for job_id in list(_process_registry):
        try:
            if terminate_process_for_job(job_id, timeout_seconds=timeout_seconds):
                terminated += 1
        except (OSError, subprocess.SubprocessError):
            logger.exception("Could not terminate process for job %s", job_id)
    return terminated


def clear_registry() -> None:
    _process_registry.clear()
