from __future__ import annotations

import asyncio
import time

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
    FFmpegNotAvailableError,
    FinalExportFailedError,
    FrameEnhancementFailedError,
    FrameEnhancerNotFoundError,
    FrameExtractionFailedError,
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
from app.services.export_service import create_final_export_for_job
from app.services.frame_enhancement_service import enhance_frames_for_job
from app.services.frame_extraction_service import extract_frames_for_job, time_to_datetime
from app.services.video_encoding_service import encode_video_for_job
from app.workers.queue import job_queue

logger = get_logger(__name__)
_worker_task: asyncio.Task | None = None
_worker_settings: Settings | None = None


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


def start_job_worker(settings: Settings | None = None) -> None:
    global _worker_task, _worker_settings

    _worker_settings = _get_active_settings(settings)
    job_queue.clear()
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(run_job_worker())


async def stop_job_worker() -> None:
    global _worker_task

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
            await asyncio.to_thread(process_job_skeleton_sync, job_id, _worker_settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker failed while processing job %s", job_id)
        finally:
            job_queue.task_done()


def process_job_skeleton_sync(job_id: str, settings: Settings | None = None) -> None:
    active_settings = _get_active_settings(settings)
    if database.SessionLocal is None:
        database.init_db(active_settings)
    if database.SessionLocal is None:
        return

    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        if not job or job.status == "cancelled":
            return

        job_repository.create_job_log(db, job.id, "info", "Job picked by worker.", stage="queued")
        db.commit()
        extract_frames_for_job(db, job_id, active_settings)
        db.refresh(job)
        if job.status in {"cancelled", "failed"}:
            return
        enhance_frames_for_job(
            db,
            job_id,
            engine=active_settings.frame_enhancer_engine,
            settings=active_settings,
        )
        db.refresh(job)
        if job.status in {"cancelled", "failed"}:
            return
        encode_video_for_job(db, job_id, active_settings)
        db.refresh(job)
        if job.status in {"cancelled", "failed"}:
            return
        mux_audio_for_job(db, job_id, active_settings)
        db.refresh(job)
        if job.status in {"cancelled", "failed"}:
            return
        export_asset = create_final_export_for_job(db, job_id, active_settings)
        db.refresh(job)
        if export_asset is None or job.status in {"cancelled", "failed"}:
            _record_job_failed_if_needed(job, active_settings)
            return

        project = project_repository.get_project_by_id(db, job.project_id)
        if project is not None:
            project_repository.update_project(
                db,
                project,
                {
                    "status": "completed",
                    "updated_at": time_to_datetime(time.time()),
                },
            )

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
    except (
        AudioMuxFailedError,
        AIRuntimeNotAvailableError,
        AIModelFileNotFoundError,
        CUDANotAvailableError,
        CUDAOutOfMemoryError,
        EncodedVideoNotFoundError,
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
    ):
        db.rollback()
        failed_job = job_repository.get_job_by_id(db, job_id)
        _record_job_failed_if_needed(failed_job, active_settings)
    finally:
        db.close()
