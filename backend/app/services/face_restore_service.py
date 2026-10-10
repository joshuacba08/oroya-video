"""Optional pipeline stage: GFPGAN face restoration between enhancement and encoding.

Restored frames are written to `frames/faces` and moved over the enhanced frames when the
stage completes, so encoding and preview keep reading `enhanced_frames_dir` unchanged and a
cancelled or interrupted run never leaves a half-restored enhanced folder.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIRuntimeNotAvailableError,
    CUDANotAvailableError,
    CUDAOutOfMemoryError,
    FaceRestoreFailedError,
    FaceRestoreNotAvailableError,
    JobNotFoundError,
    OroyaVideoError,
    TorchNotAvailableError,
)
from app.core.logging import get_logger
from app.core.paths import get_job_working_path, get_model_path, get_models_path
from app.db.models import ProcessingJob
from app.db.repositories import ai_model_repository, job_repository
from app.enhancers.gfpgan_enhancer import GFPGANFaceRestorer
from app.services.ai_runtime_service import resolve_ai_device
from app.services.frame_extraction_service import time_to_datetime
from app.services.pipeline_progress import (
    FACE_RESTORE_PROGRESS_END,
    FACE_RESTORE_PROGRESS_START,
    calculate_stage_progress,
)
from app.services.process_registry_service import is_shutting_down
from app.utils.enhancement_config import parse_enhancement_config_json

logger = get_logger(__name__)

FACE_RESTORE_MODEL_SLUG = "gfpgan-v1.4"
FACE_RESTORE_WEIGHTS_SUBDIR = "facexlib"
DB_SYNC_INTERVAL_SECONDS = 0.5
DEFAULT_STRENGTH = 0.5


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def get_face_restore_strength(job: ProcessingJob) -> float | None:
    """Strength (0-1) when face restoration is enabled for the job, else None."""
    config = parse_enhancement_config_json(job.enhancement_config_json).get("face_restore")
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return None
    strength = config.get("strength", DEFAULT_STRENGTH)
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        return DEFAULT_STRENGTH
    return float(min(max(strength, 0.0), 1.0))


def get_face_restore_model_path(db: Session, settings: Settings | None = None) -> Path | None:
    model = ai_model_repository.get_ai_model_by_slug(db, FACE_RESTORE_MODEL_SLUG)
    if model is None or not model.is_enabled or not model.relative_path:
        return None
    return get_model_path(model.relative_path, _get_active_settings(settings))


def _mark_failed(db: Session, job: ProcessingJob, exc: OroyaVideoError) -> None:
    db.rollback()
    job_repository.update_job(
        db,
        job,
        {
            "status": "failed",
            "current_stage": "failed",
            "error_code": exc.error_code,
            "error_message": exc.message,
            "process_kind": None,
            "process_ended_at": time_to_datetime(time.time()),
        },
    )
    job_repository.create_job_log(db, job.id, "error", exc.message, stage="restoring_faces")
    db.commit()


def restore_faces_for_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> ProcessingJob:
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if job is None:
        raise JobNotFoundError()
    strength = get_face_restore_strength(job)
    if strength is None or job.status != "running":
        return job

    enhanced_dir = Path(job.enhanced_frames_dir or "")
    faces_dir = get_job_working_path(job.id, active_settings) / "frames" / "faces"
    model_path = get_face_restore_model_path(db, active_settings)
    try:
        if model_path is None:
            raise FaceRestoreNotAvailableError()
        device = resolve_ai_device(
            active_settings.ai_device, allow_cpu=active_settings.ai_allow_cpu
        )
    except (
        FaceRestoreNotAvailableError,
        AIRuntimeNotAvailableError,
        CUDANotAvailableError,
        TorchNotAvailableError,
    ) as exc:
        _mark_failed(db, job, exc)
        raise

    restorer = GFPGANFaceRestorer(
        model_path=model_path,
        weights_dir=get_models_path(active_settings) / FACE_RESTORE_WEIGHTS_SUBDIR,
        device=device,
        strength=strength,
    )
    started_at = time.monotonic()
    last_sync = 0.0
    job_repository.update_job(
        db,
        job,
        {
            "current_stage": "restoring_faces",
            "progress_percent": FACE_RESTORE_PROGRESS_START,
            "process_kind": "gfpgan",
            "process_started_at": time_to_datetime(time.time()),
            "process_ended_at": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Face restoration started (GFPGAN, strength {strength:.2f}, {device}).",
        stage="restoring_faces",
    )
    db.commit()

    def progress_callback(processed: int, total: int) -> None:
        nonlocal last_sync
        job_repository.update_job(
            db,
            job,
            {
                "frames_processed": processed,
                "progress_percent": calculate_stage_progress(
                    processed,
                    total,
                    start=FACE_RESTORE_PROGRESS_START,
                    end=FACE_RESTORE_PROGRESS_END,
                    clamp_to=FACE_RESTORE_PROGRESS_END - 0.1,
                ),
                "elapsed_time_seconds": int(time.monotonic() - started_at),
            },
        )
        if processed >= total or time.monotonic() - last_sync >= DB_SYNC_INTERVAL_SECONDS:
            db.commit()
            last_sync = time.monotonic()

    def stop_callback() -> bool:
        nonlocal last_sync
        if is_shutting_down():
            return True
        if time.monotonic() - last_sync >= DB_SYNC_INTERVAL_SECONDS:
            db.commit()
            db.refresh(job)
            last_sync = time.monotonic()
        return job.cancel_requested or job.status == "cancelled"

    try:
        restorer.restore_frames(enhanced_dir, faces_dir, progress_callback, stop_callback)
    except (FaceRestoreNotAvailableError, FaceRestoreFailedError, CUDAOutOfMemoryError) as exc:
        logger.exception("Face restoration failed: %s", job.id)
        _mark_failed(db, job, exc)
        raise

    db.commit()
    db.refresh(job)
    if job.cancel_requested or job.status == "cancelled" or is_shutting_down():
        job_repository.update_job(db, job, {"process_kind": None})
        db.commit()
        logger.info("Face restoration stopped before completion: %s", job.id)
        return job

    # Etapa completa: los frames restaurados sustituyen a los mejorados.
    for restored in sorted(faces_dir.glob("*.png")):
        os.replace(restored, enhanced_dir / restored.name)
    faces_dir.rmdir()
    job_repository.update_job(
        db,
        job,
        {
            "progress_percent": FACE_RESTORE_PROGRESS_END,
            "elapsed_time_seconds": int(time.monotonic() - started_at),
            "process_kind": None,
            "process_ended_at": time_to_datetime(time.time()),
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Face restoration completed: {restorer.faces_restored} faces in "
        f"{restorer.processed_frames} frames"
        + (
            f" ({restorer.average_frame_time_ms} ms/frame)."
            if restorer.average_frame_time_ms
            else "."
        ),
        stage="restoring_faces",
    )
    db.commit()
    return job
