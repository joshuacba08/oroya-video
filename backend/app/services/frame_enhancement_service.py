from __future__ import annotations

import shutil
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIModelFileNotFoundError,
    AIRuntimeNotAvailableError,
    CUDANotAvailableError,
    CUDAOutOfMemoryError,
    EnhancedFramesNotFoundError,
    FrameEnhancementFailedError,
    FrameEnhancerNotFoundError,
    InsufficientTempStorageError,
    JobNotFoundError,
    OriginalFramesNotFoundError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
    RealESRGANUnsupportedModelError,
    TorchNotAvailableError,
)
from app.core.logging import get_logger
from app.core.paths import (
    get_directory_size_bytes,
    get_job_enhanced_frames_path,
    get_temp_path,
)
from app.db.repositories import job_repository
from app.enhancers.registry import get_frame_enhancer
from app.schemas.job_schema import JobEnhancedFrameItem, JobEnhancedFramesResponse
from app.services.frame_extraction_service import time_to_datetime
from app.services.pipeline_progress import (
    ENHANCEMENT_PROGRESS_END,
    ENHANCEMENT_PROGRESS_START,
    calculate_stage_progress,
)
from app.services.realesrgan_service import process_realesrgan_frames_for_job

logger = get_logger(__name__)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def count_enhanced_frames(frames_dir: Path) -> int:
    return sum(1 for item in frames_dir.glob("*.png") if item.is_file())


def ensure_enhancement_storage_capacity(
    original_frames_dir: Path,
    settings: Settings | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    temp_path = get_temp_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(temp_path)
    required_bytes = max(get_directory_size_bytes(original_frames_dir), 1)
    if free_bytes < required_bytes:
        raise InsufficientTempStorageError(
            "Not enough temporary storage space to enhance frames."
        )


def _mark_enhancement_failed(
    db: Session,
    job,
    *,
    error_code: str,
    error_message: str,
) -> None:
    job_repository.update_job(
        db,
        job,
        {
            "status": "failed",
            "current_stage": "failed",
            "error_code": error_code,
            "error_message": error_message,
            "enhancement_error_code": error_code,
            "enhancement_error_message": error_message,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "error",
        f"Frame enhancement failed: {error_message}",
        stage="failed",
    )
    db.commit()


def enhance_frames_for_job(
    db: Session,
    job_id: str,
    engine: str = "mock",
    settings: Settings | None = None,
):
    active_settings = _get_active_settings(settings)
    normalized_engine = engine.strip().lower()
    if normalized_engine == "realesrgan":
        return process_realesrgan_frames_for_job(db, job_id, active_settings)

    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    if job.cancel_requested or job.status == "cancelled":
        return job

    original_frames_value = job.original_frames_dir
    if not original_frames_value:
        _mark_enhancement_failed(
            db,
            job,
            error_code="original_frames_not_found",
            error_message="No original frames were found for this job.",
        )
        raise OriginalFramesNotFoundError()

    original_frames_dir = Path(original_frames_value)
    if not original_frames_dir.exists():
        _mark_enhancement_failed(
            db,
            job,
            error_code="original_frames_not_found",
            error_message="No original frames were found for this job.",
        )
        raise OriginalFramesNotFoundError()

    enhanced_frames_dir = get_job_enhanced_frames_path(job.id, active_settings)
    enhanced_frames_dir.mkdir(parents=True, exist_ok=True)

    try:
        ensure_enhancement_storage_capacity(original_frames_dir, active_settings)
        enhancer = get_frame_enhancer(engine)
    except (InsufficientTempStorageError, FrameEnhancerNotFoundError) as exc:
        _mark_enhancement_failed(
            db,
            job,
            error_code=exc.error_code,
            error_message=exc.message,
        )
        raise

    logger.info("Frame enhancement requested: %s", job_id)
    logger.info("Frame enhancer resolved: %s", enhancer.engine)
    total_frames = max(job.extracted_frames, count_enhanced_frames(original_frames_dir))
    started_at = time.monotonic()
    now = time.time()
    last_logged_frame = -100

    def progress_callback(processed: int, total: int) -> None:
        nonlocal last_logged_frame
        progress_percent = calculate_stage_progress(
            processed,
            total,
            start=ENHANCEMENT_PROGRESS_START,
            end=ENHANCEMENT_PROGRESS_END,
            clamp_to=59.9,
        )
        job_repository.update_job(
            db,
            job,
            {
                "frames_processed": processed,
                "enhanced_frames": processed,
                "progress_percent": progress_percent,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
            },
        )
        if processed - last_logged_frame >= 100:
            last_logged_frame = processed
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                f"Frame enhancement progress: {processed}/{total}",
                stage="enhancing_frames",
            )
        db.commit()
        logger.info("Frame enhancement progress updated: %s", processed)

    def cancel_callback() -> bool:
        db.refresh(job)
        return job.cancel_requested or job.status == "cancelled"

    def pause_callback() -> bool:
        db.refresh(job)
        return bool(job.pause_requested)

    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "enhancing_frames",
            "frames_processed": 0,
            "enhancer_engine": enhancer.engine,
            "enhanced_frames_dir": str(enhanced_frames_dir),
            "enhancement_started_at": job.enhancement_started_at or time_to_datetime(now),
            "enhancement_error_code": None,
            "enhancement_error_message": None,
            "error_code": None,
            "error_message": None,
            "process_kind": "mock",
            "process_started_at": job.process_started_at or time_to_datetime(now),
            "process_ended_at": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Frame enhancement started.",
        stage="enhancing_frames",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Requested model: {job.ai_model_slug}",
        stage="enhancing_frames",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Enhancer engine: {enhancer.engine}",
        stage="enhancing_frames",
    )
    db.commit()

    try:
        processed = enhancer.enhance_frames(
            original_frames_dir,
            enhanced_frames_dir,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            pause_callback=pause_callback,
        )
    except (
        AIRuntimeNotAvailableError,
        AIModelFileNotFoundError,
        CUDANotAvailableError,
        CUDAOutOfMemoryError,
        OriginalFramesNotFoundError,
        RealESRGANFrameProcessingFailedError,
        RealESRGANModelLoadFailedError,
        RealESRGANNotAvailableError,
        RealESRGANUnsupportedModelError,
        TorchNotAvailableError,
        OSError,
        SQLAlchemyError,
    ) as exc:
        db.rollback()
        if isinstance(exc, OriginalFramesNotFoundError):
            _mark_enhancement_failed(
                db,
                job,
                error_code=exc.error_code,
                error_message=exc.message,
            )
            raise
        if isinstance(
            exc,
            (
                AIRuntimeNotAvailableError,
                AIModelFileNotFoundError,
                CUDANotAvailableError,
                CUDAOutOfMemoryError,
                RealESRGANFrameProcessingFailedError,
                RealESRGANModelLoadFailedError,
                RealESRGANNotAvailableError,
                RealESRGANUnsupportedModelError,
                TorchNotAvailableError,
            ),
        ):
            _mark_enhancement_failed(
                db,
                job,
                error_code=exc.error_code,
                error_message=exc.message,
            )
            raise
        _mark_enhancement_failed(
            db,
            job,
            error_code="frame_enhancement_failed",
            error_message="Frames could not be enhanced.",
        )
        logger.exception("Frame enhancement failed")
        raise FrameEnhancementFailedError() from exc

    db.refresh(job)
    if job.cancel_requested or job.status == "cancelled":
        job_repository.update_job(
            db,
            job,
            {
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancelled_at": time_to_datetime(time.time()),
                "enhanced_frames": processed,
                "process_kind": None,
                "process_ended_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "warning",
            "Frame enhancement cancelled by user.",
            stage="cancelled",
        )
        db.commit()
        logger.warning("Frame enhancement cancelled: %s", job_id)
        return job

    if job.pause_requested:
        job_repository.update_job(
            db,
            job,
            {
                "status": "paused",
                "current_stage": "enhancing_frames",
                "enhanced_frames": processed,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
                "enhanced_frames_size_bytes": get_directory_size_bytes(enhanced_frames_dir),
                "process_kind": None,
                "process_ended_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Enhancement paused by user.",
            stage="enhancing_frames",
        )
        db.commit()
        logger.info("Frame enhancement paused: %s", job_id)
        return job

    enhanced_frames = count_enhanced_frames(enhanced_frames_dir)
    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "enhancing_frames",
            "frames_processed": enhanced_frames,
            "enhanced_frames": enhanced_frames,
            "frames_total": job.frames_total or total_frames,
            "progress_percent": ENHANCEMENT_PROGRESS_END,
            "elapsed_time_seconds": int(time.monotonic() - started_at),
            "enhancement_completed_at": time_to_datetime(time.time()),
            "enhanced_frames_size_bytes": get_directory_size_bytes(enhanced_frames_dir),
            "process_kind": None,
            "process_ended_at": time_to_datetime(time.time()),
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Frame enhancement completed using mock enhancer.",
        stage="enhancing_frames",
    )
    db.commit()
    logger.info("Frame enhancement completed: %s", job_id)
    return job


def list_enhanced_frames(
    job,
    limit: int = 100,
    offset: int = 0,
) -> JobEnhancedFramesResponse:
    frames_dir_value = job.enhanced_frames_dir
    if not frames_dir_value:
        raise EnhancedFramesNotFoundError()

    frames_dir = Path(frames_dir_value)
    if not frames_dir.exists():
        raise EnhancedFramesNotFoundError()

    frame_files = sorted(frame for frame in frames_dir.glob("*.png") if frame.is_file())
    if not frame_files:
        raise EnhancedFramesNotFoundError()

    paged_files = frame_files[offset : offset + limit]
    items = [
        JobEnhancedFrameItem(index=offset + index, file_name=frame.name, path=str(frame))
        for index, frame in enumerate(paged_files)
    ]
    logger.info("Enhanced frames listed: %s", job.id)
    return JobEnhancedFramesResponse(
        job_id=job.id,
        frames_dir=str(frames_dir),
        items=items,
        total=len(frame_files),
        limit=limit,
        offset=offset,
    )


def clean_enhanced_frames(job_id: str, settings: Settings | None = None) -> Path:
    active_settings = _get_active_settings(settings)
    enhanced_frames_dir = get_job_enhanced_frames_path(job_id, active_settings)
    if enhanced_frames_dir.exists():
        shutil.rmtree(enhanced_frames_dir)
    enhanced_frames_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Enhanced frames deleted: %s", job_id)
    return enhanced_frames_dir
