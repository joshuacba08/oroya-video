"""Shut the sidecar backend down when the desktop app that launched it is gone.

Tauri stops the backend on a normal exit, but a crash or a forced kill of the app skips
that and would leave an orphan backend on the port (a later, updated app would then talk
to the old one). The app passes its PID in OROYA_PARENT_PID; this thread polls it.
"""

from __future__ import annotations

import os
import signal
import threading
import time

import psutil

from app.core.logging import get_logger

logger = get_logger(__name__)

PARENT_PID_ENV = "OROYA_PARENT_PID"
POLL_INTERVAL_SECONDS = 2.0
FORCED_EXIT_AFTER_SECONDS = 15.0


def _parent_identity(pid: int) -> float | None:
    """Process creation time: guards against the PID being reused by another process."""
    try:
        return psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def parent_is_alive(pid: int, created_at: float) -> bool:
    return _parent_identity(pid) == created_at


def _request_shutdown() -> None:
    # uvicorn atiende SIGINT con un apagado ordenado (lifespan incluido); si no termina a
    # tiempo, se fuerza la salida para no dejar el puerto ocupado.
    signal.raise_signal(signal.SIGINT)
    time.sleep(FORCED_EXIT_AFTER_SECONDS)
    os._exit(0)


def start_parent_watchdog() -> threading.Thread | None:
    raw_pid = os.environ.get(PARENT_PID_ENV)
    if not raw_pid:
        return None
    try:
        pid = int(raw_pid)
    except ValueError:
        logger.warning("Invalid %s=%r; parent watchdog disabled.", PARENT_PID_ENV, raw_pid)
        return None
    created_at = _parent_identity(pid)
    if created_at is None:
        logger.warning("Parent process %s not found at startup; shutting down.", pid)
        threading.Thread(target=_request_shutdown, daemon=True).start()
        return None

    def watch() -> None:
        while parent_is_alive(pid, created_at):
            time.sleep(POLL_INTERVAL_SECONDS)
        logger.warning("Parent process %s exited; shutting down the backend.", pid)
        _request_shutdown()

    thread = threading.Thread(target=watch, daemon=True, name="parent-watchdog")
    thread.start()
    logger.info("Parent watchdog active for PID %s.", pid)
    return thread
