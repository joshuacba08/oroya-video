from __future__ import annotations

import asyncio
import threading
import time

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIModelFileNotFoundError,
    AIRuntimeNotAvailableError,
    AudioMuxFailedError,
    CUDANotAvailableError,
    CUDAOutOfMemoryError,
    EncodedVideoNotFoundError,
    EnhancedFramesRequiredError,
    ExportAssetNotFoundError,
    FaceRestoreFailedError,
    FaceRestoreNotAvailableError,
    FFmpegNotAvailableError,
    FFmpegStalledError,
    FinalExportFailedError,
    FrameEnhancementFailedError,
    FrameEnhancerNotFoundError,
    FrameExtractionFailedError,
    InsufficientDiskSpaceError,
    InsufficientExportStorageError,
    InsufficientTempStorageError,
    MuxedVideoNotFoundError,
    OriginalFramesNotFoundError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANJobNotReadyError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
    RealESRGANUnsupportedModelError,
    TorchNotAvailableError,
    VideoAssetFileMissingError,
    VideoEncodingFailedError,
)
from app.core.logging import get_logger
from app.db import database
from app.db.repositories import job_repository, project_repository
from app.services.audio_mux_service import mux_audio_for_job
from app.services.audit_log_service import record_audit_event
from app.services.cleanup_service import (
    cleanup_job_temp_after_success,
    trim_original_frames_after_enhancement,
)
from app.services.export_service import create_final_export_for_job
from app.services.face_restore_service import restore_faces_for_job
from app.services.frame_enhancement_service import enhance_frames_for_job
from app.services.frame_extraction_service import extract_frames_for_job, time_to_datetime
from app.services.job_contract_service import PAUSABLE_STAGES
from app.services.process_registry_service import (
    clear_shutdown,
    is_shutting_down,
    request_shutdown,
    terminate_all_processes,
)
from app.services.streaming_pipeline_service import process_job_streaming
from app.services.video_encoding_service import encode_video_for_job
from app.workers.queue import job_queue

logger = get_logger(__name__)
_worker_task: asyncio.Task | None = None
_worker_settings: Settings | None = None
# Activo mientras un hilo procesa un job: el apagado espera a que termine (con límite).
_job_in_progress = threading.Event()


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or _worker_settings or get_settings()


def is_job_worker_running() -> bool:
    return _worker_task is not None and not _worker_task.done()


def _record_job_failed_if_needed(job, settings: Settings | None = None) -> None:
    if job is None or job.status != "failed":
        return
    record_audit_event(
        "job_failed",
        "job",
        job.id,
        "Job failed during processing.",
        {
            "stage": job.current_stage,
            "error_code": job.error_code,
            "error_message": job.error_message,
        },
        settings,
    )


def _mark_job_failed_after_error(
    db,
    job_id: str,
    error_code: str,
    message: str,
    settings: Settings | None = None,
) -> None:
    """Leave the job in a terminal state when a stage raised without marking it failed."""
    try:
        db.rollback()
        job = job_repository.get_job_by_id(db, job_id)
        if job is None:
            return
        if job.status in {"completed", "failed", "cancelled"}:
            _record_job_failed_if_needed(job, settings)
            return

        job = job_repository.update_job(
            db,
            job,
            {
                "status": "failed",
                "current_stage": "failed",
                "error_code": error_code,
                "error_message": message,
                "process_id": None,
                "process_kind": None,
                "process_ended_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "error",
            message,
            stage="failed",
        )
        db.commit()
        db.refresh(job)
        _record_job_failed_if_needed(job, settings)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not mark job %s as failed after worker error.", job_id)


def _mark_unexpected_worker_failure(
    db,
    job_id: str,
    exc: Exception,
    settings: Settings | None = None,
) -> None:
    details = str(exc).strip()
    message = f"Unexpected worker error: {exc.__class__.__name__}"
    if details:
        message = f"{message}: {details[:500]}"
    _mark_job_failed_after_error(db, job_id, "unknown_error", message, settings)


# Estado del proyecto según el estado del job que lo procesó.
PROJECT_STATUS_BY_JOB_STATUS = {
    "running": "processing",
    "queued": "processing",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "ready",
    "paused": "ready",
    "interrupted": "ready",
}


def _sync_project_status(db, job_id: str) -> None:
    try:
        db.rollback()
        job = job_repository.get_job_by_id(db, job_id)
        if job is None:
            return
        project_status = PROJECT_STATUS_BY_JOB_STATUS.get(job.status)
        project = project_repository.get_project_by_id(db, job.project_id)
        if project is None or project_status is None or project.status == project_status:
            return
        project_repository.update_project(
            db,
            project,
            {"status": project_status, "updated_at": time_to_datetime(time.time())},
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not sync project status for job %s", job_id)


def resolve_pipeline_mode(job, settings: Settings) -> str:
    """The job keeps the pipeline it started with; jobs from before 0.5 (frames already
    extracted to PNG) continue with the classic one."""
    if job.pipeline_mode in {"streaming", "legacy"}:
        return job.pipeline_mode
    if job.extraction_started_at is not None:
        return "legacy"
    return settings.pipeline_mode


def start_job_worker(settings: Settings | None = None) -> None:
    global _worker_task, _worker_settings

    _worker_settings = _get_active_settings(settings)
    clear_shutdown()
    job_queue.clear()
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(run_job_worker())


def _request_pause_of_running_enhancement() -> None:
    """La mejora de frames respeta `pause_requested`: queda `paused` y se puede reanudar."""
    if database.SessionLocal is None:
        return
    db = database.SessionLocal()
    try:
        running_jobs = job_repository.list_jobs(db, limit=50, offset=0, status="running")
        for job in running_jobs:
            if job.current_stage in PAUSABLE_STAGES:
                job_repository.update_job(db, job, {"pause_requested": True})
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not request pause of running jobs on shutdown.")
    finally:
        db.close()


async def stop_job_worker() -> None:
    global _worker_task

    request_shutdown()
    if _job_in_progress.is_set():
        timeout_seconds = _get_active_settings().process_shutdown_timeout_seconds
        await asyncio.to_thread(_request_pause_of_running_enhancement)
        await asyncio.to_thread(terminate_all_processes, timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        while _job_in_progress.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if _job_in_progress.is_set():
            logger.warning("Job still running after %ss shutdown timeout.", timeout_seconds)

    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    job_queue.clear()


async def run_job_worker() -> None:
    while True:
        job_id = await job_queue.dequeue()
        try:
            _job_in_progress.set()
            await asyncio.to_thread(process_job_skeleton_sync, job_id, _worker_settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker failed while processing job %s", job_id)
        finally:
            _job_in_progress.clear()
            job_queue.task_done()


def _run_legacy_frame_stages(db, job, settings: Settings) -> bool:
    """Classic pipeline: every frame to PNG, enhance, faces, encode. False when it stopped."""
    job_id = job.id
    extract_frames_for_job(db, job_id, settings)
    db.refresh(job)
    if job.status in {"cancelled", "failed", "paused"} or is_shutting_down():
        return False
    enhance_frames_for_job(
        db,
        job_id,
        engine=settings.frame_enhancer_engine,
        settings=settings,
    )
    db.refresh(job)
    if job.status in {"cancelled", "failed", "paused"} or is_shutting_down():
        return False
    trim_original_frames_after_enhancement(db, job_id, settings)
    restore_faces_for_job(db, job_id, settings)
    db.refresh(job)
    if job.status in {"cancelled", "failed", "paused"} or is_shutting_down():
        return False
    encode_video_for_job(db, job_id, settings)
    return True


def process_job_skeleton_sync(job_id: str, settings: Settings | None = None) -> None:
    active_settings = _get_active_settings(settings)
    if database.SessionLocal is None:
        database.init_db(active_settings)
    if database.SessionLocal is None:
        return

    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        # Solo se procesan jobs en cola: un job pausado/cancelado mientras esperaba, o una
        # entrada duplicada de la cola (p. ej. pausa + reanudar), no debe volver a ejecutarse.
        if not job or job.status != "queued":
            if job is not None:
                logger.info("Skipping job %s dequeued with status %s", job_id, job.status)
            return

        job_repository.create_job_log(db, job.id, "info", "Job picked by worker.", stage="queued")
        db.commit()
        _sync_project_status(db, job_id)
        job = job_repository.get_job_by_id(db, job_id)
        if resolve_pipeline_mode(job, active_settings) == "streaming":
            process_job_streaming(db, job_id, active_settings)
        else:
            job_repository.update_job(db, job, {"pipeline_mode": "legacy"})
            db.commit()
            if not _run_legacy_frame_stages(db, job, active_settings):
                return
        db.refresh(job)
        if job.status in {"cancelled", "failed", "paused"} or is_shutting_down():
            return
        mux_audio_for_job(db, job_id, active_settings)
        db.refresh(job)
        if job.status in {"cancelled", "failed", "paused"} or is_shutting_down():
            return
        export_asset = create_final_export_for_job(db, job_id, active_settings)
        db.refresh(job)
        if export_asset is None or job.status in {"cancelled", "failed", "paused"}:
            _record_job_failed_if_needed(job, active_settings)
            return

        job_repository.update_job(
            db,
            job,
            {
                "status": "completed",
                "current_stage": "completed",
                "progress_percent": 100.0,
                "completed_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Job completed successfully.",
            stage="completed",
        )
        db.commit()
        record_audit_event(
            "job_completed",
            "job",
            job.id,
            "Job completed successfully.",
            {"export_id": job.export_id, "final_export_path": job.final_export_path},
            active_settings,
        )
        if active_settings.cleanup_temp_on_success:
            cleanup_job_temp_after_success(db, job.id, active_settings)
    except (
        AudioMuxFailedError,
        AIRuntimeNotAvailableError,
        FFmpegStalledError,
        InsufficientDiskSpaceError,
        AIModelFileNotFoundError,
        CUDANotAvailableError,
        CUDAOutOfMemoryError,
        EncodedVideoNotFoundError,
        FaceRestoreFailedError,
        FaceRestoreNotAvailableError,
        ExportAssetNotFoundError,
        FrameEnhancerNotFoundError,
        OriginalFramesNotFoundError,
        FrameEnhancementFailedError,
        EnhancedFramesRequiredError,
        FFmpegNotAvailableError,
        FinalExportFailedError,
        InsufficientTempStorageError,
        InsufficientExportStorageError,
        MuxedVideoNotFoundError,
        VideoAssetFileMissingError,
        FrameExtractionFailedError,
        RealESRGANFrameProcessingFailedError,
        RealESRGANJobNotReadyError,
        RealESRGANModelLoadFailedError,
        RealESRGANNotAvailableError,
        RealESRGANUnsupportedModelError,
        TorchNotAvailableError,
        VideoEncodingFailedError,
    ) as exc:
        _mark_job_failed_after_error(
            db,
            job_id,
            exc.error_code,
            exc.message,
            active_settings,
        )
    except Exception as exc:
        logger.exception("Unexpected worker failure while processing job %s", job_id)
        _mark_unexpected_worker_failure(db, job_id, exc, active_settings)
    finally:
        _sync_project_status(db, job_id)
        db.close()
