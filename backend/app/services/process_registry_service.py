from __future__ import annotations

import subprocess
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


def clear_registry() -> None:
    _process_registry.clear()
