import asyncio
import threading
import time
from unittest.mock import patch

from app.services import process_registry_service
from app.workers import job_runner


def test_stop_job_worker_pauses_kills_ffmpeg_and_waits_for_running_job() -> None:
    job_runner._job_in_progress.set()
    # Simulates the worker thread finishing once its ffmpeg/enhancement is stopped.
    finisher = threading.Timer(0.3, job_runner._job_in_progress.clear)

    try:
        with (
            patch.object(job_runner, "_request_pause_of_running_enhancement") as pause,
            patch.object(job_runner, "terminate_all_processes") as terminate,
        ):
            finisher.start()
            started = time.monotonic()
            asyncio.run(job_runner.stop_job_worker())
            elapsed = time.monotonic() - started

        assert pause.called
        assert terminate.called
        assert process_registry_service.is_shutting_down()
        assert not job_runner._job_in_progress.is_set()
        assert elapsed < 3
    finally:
        finisher.cancel()
        job_runner._job_in_progress.clear()
        process_registry_service.clear_shutdown()


def test_stop_job_worker_is_immediate_when_idle() -> None:
    with patch.object(job_runner, "terminate_all_processes") as terminate:
        asyncio.run(job_runner.stop_job_worker())
    process_registry_service.clear_shutdown()

    assert not terminate.called
