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
    process: subprocess.Popen | None = None


# Por job, sus procesos por tipo: el pipeline por streaming tiene a la vez un decodificador
# y un codificador ffmpeg; las etapas clásicas, uno solo.
_process_registry: dict[str, dict[str, ProcessInfo]] = {}
_registry_lock = threading.Lock()
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
    process: subprocess.Popen | None = None,
) -> None:
    info = ProcessInfo(
        job_id=job_id,
        process_id=process_id,
        process_kind=process_kind,
        started_at=time.time(),
        process=process,
    )
    with _registry_lock:
        _process_registry.setdefault(job_id, {})[process_kind] = info
    logger.info("Process registered: %s %s", job_id, process_kind)


def unregister_process(job_id: str, process_kind: str | None = None) -> None:
    """Forget one process of the job, or all of them when no kind is given."""
    with _registry_lock:
        processes = _process_registry.get(job_id)
        if processes is None:
            return
        if process_kind is None:
            processes.clear()
        else:
            processes.pop(process_kind, None)
        if not processes:
            _process_registry.pop(job_id, None)
    logger.info("Process unregistered: %s %s", job_id, process_kind or "*")


def get_processes_for_job(job_id: str) -> list[ProcessInfo]:
    with _registry_lock:
        return list(_process_registry.get(job_id, {}).values())


def get_process_for_job(job_id: str) -> ProcessInfo | None:
    processes = get_processes_for_job(job_id)
    return processes[0] if processes else None


def _stop(process: subprocess.Popen, timeout_seconds: int) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)


def terminate_process_for_job(job_id: str, timeout_seconds: int = 5) -> bool:
    """Stop every process of the job. True when at least one was registered."""
    processes = [info for info in get_processes_for_job(job_id) if info.process is not None]
    if not processes:
        return False
    for info in processes:
        _stop(info.process, timeout_seconds)  # type: ignore[arg-type]
    unregister_process(job_id)
    logger.warning("Processes terminated for job %s", job_id)
    return True


def terminate_all_processes(timeout_seconds: int = 5) -> int:
    terminated = 0
    with _registry_lock:
        job_ids = list(_process_registry)
    for job_id in job_ids:
        try:
            if terminate_process_for_job(job_id, timeout_seconds=timeout_seconds):
                terminated += 1
        except (OSError, subprocess.SubprocessError):
            logger.exception("Could not terminate process for job %s", job_id)
    return terminated


def clear_registry() -> None:
    with _registry_lock:
        _process_registry.clear()
