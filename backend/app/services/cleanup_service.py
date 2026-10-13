from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import JobCleanupFailedError, JobInvalidStateError, JobNotFoundError
from app.core.logging import get_logger
from app.core.paths import (
    get_directory_size_bytes,
    get_exports_path,
    get_job_encoded_path,
    get_job_enhanced_frames_path,
    get_job_filtered_frames_path,
    get_job_muxed_path,
    get_job_original_frames_path,
    get_jobs_temp_path,
    get_storage_path,
)
from app.db.models import ProcessingJob
from app.db.repositories import job_repository
from app.schemas.hardening_schema import CleanupBatchItem, CleanupBatchResponse, CleanupResponse
from app.services.audit_log_service import record_audit_event
from app.services.frame_extraction_service import time_to_datetime

logger = get_logger(__name__)


# Interrumpidos (app cerrada a mitad) incluidos: al reintentar reutilizan sus frames.
TEMP_PROTECTED_JOB_STATUSES = (
    "pending",
    "queued",
    "running",
    "paused",
    "retrying",
    "cleaning",
    "interrupted",
)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _get_job_or_raise(db: Session, job_id: str):
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    return job


def calculate_job_temp_size(job_id: str, settings: Settings | None = None) -> dict[str, int]:
    active_settings = _get_active_settings(settings)
    original_path = get_job_original_frames_path(job_id, active_settings)
    enhanced_path = get_job_enhanced_frames_path(job_id, active_settings)
    encoded_path = get_job_encoded_path(job_id, active_settings)
    muxed_path = get_job_muxed_path(job_id, active_settings)

    original_frames_size = get_directory_size_bytes(original_path)
    enhanced_frames_size = get_directory_size_bytes(enhanced_path)
    encoded_size = get_directory_size_bytes(encoded_path)
    muxed_size = get_directory_size_bytes(muxed_path)
    total = original_frames_size + enhanced_frames_size + encoded_size + muxed_size
    return {
        "temp_size_bytes": total,
        "original_frames_size_bytes": original_frames_size,
        "enhanced_frames_size_bytes": enhanced_frames_size,
        "encoded_size_bytes": encoded_size,
        "muxed_size_bytes": muxed_size,
    }


def _delete_path_if_requested(
    path: Path,
    *,
    enabled: bool,
    deleted_paths: list[str],
) -> int:
    if not enabled or not path.exists():
        return 0
    freed_bytes = get_directory_size_bytes(path)
    if path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
    deleted_paths.append(str(path))
    return freed_bytes


def cleanup_job_temp_files(
    db: Session,
    job_id: str,
    *,
    include_original_frames: bool = True,
    include_enhanced_frames: bool = True,
    include_encoded: bool = True,
    include_muxed: bool = True,
    settings: Settings | None = None,
) -> CleanupResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.status in {"running", "queued", "retrying", "cleaning"}:
        raise JobInvalidStateError()

    deleted_paths: list[str] = []
    warnings: list[str] = []
    cleanup_started_at = time_to_datetime(time.time())
    original_stage = job.current_stage

    try:
        job_repository.update_job(
            db,
            job,
            {
                "cleanup_started_at": cleanup_started_at,
                "cleanup_completed_at": None,
                "cleanup_error_code": None,
                "cleanup_error_message": None,
                "status": job.status,
                "current_stage": "cleaning",
            },
        )
        db.commit()

        freed_bytes = 0
        freed_bytes += _delete_path_if_requested(
            get_job_original_frames_path(job.id, active_settings),
            enabled=include_original_frames,
            deleted_paths=deleted_paths,
        )
        freed_bytes += _delete_path_if_requested(
            get_job_enhanced_frames_path(job.id, active_settings),
            enabled=include_enhanced_frames,
            deleted_paths=deleted_paths,
        )
        # Las vistas previas con filtros salen de los mejorados: sin ellos quedarían obsoletas.
        freed_bytes += _delete_path_if_requested(
            get_job_filtered_frames_path(job.id, active_settings),
            enabled=include_enhanced_frames,
            deleted_paths=deleted_paths,
        )
        freed_bytes += _delete_path_if_requested(
            get_job_encoded_path(job.id, active_settings),
            enabled=include_encoded,
            deleted_paths=deleted_paths,
        )
        freed_bytes += _delete_path_if_requested(
            get_job_muxed_path(job.id, active_settings),
            enabled=include_muxed,
            deleted_paths=deleted_paths,
        )

        updated_sizes = calculate_job_temp_size(job.id, active_settings)
        update_data: dict[str, object] = {
            "cleanup_completed_at": time_to_datetime(time.time()),
            "cleanup_error_code": None,
            "cleanup_error_message": None,
            "temp_size_bytes": updated_sizes["temp_size_bytes"],
            "original_frames_size_bytes": updated_sizes["original_frames_size_bytes"],
            "enhanced_frames_size_bytes": updated_sizes["enhanced_frames_size_bytes"],
            "encoded_size_bytes": updated_sizes["encoded_size_bytes"],
            "muxed_size_bytes": updated_sizes["muxed_size_bytes"],
            "current_stage": original_stage,
        }
        if include_original_frames:
            update_data["original_frames_dir"] = None
            update_data["frames_processed"] = 0
            update_data["extracted_frames"] = 0
            update_data["frame_file_pattern"] = None
            update_data["extraction_started_at"] = None
            update_data["extraction_completed_at"] = None
        if include_enhanced_frames:
            update_data["enhanced_frames_dir"] = None
            update_data["enhanced_frames"] = 0
            update_data["enhancement_started_at"] = None
            update_data["enhancement_completed_at"] = None
            update_data["enhancement_error_code"] = None
            update_data["enhancement_error_message"] = None
        if include_encoded:
            update_data["encoded_dir"] = None
            update_data["encoded_video_path"] = None
            update_data["encoded_video_file_name"] = None
            update_data["encoded_video_size_bytes"] = None
            update_data["encoding_started_at"] = None
            update_data["encoding_completed_at"] = None
            update_data["encoding_error_code"] = None
            update_data["encoding_error_message"] = None
        if include_muxed:
            update_data["muxed_video_path"] = None
            update_data["muxed_video_file_name"] = None
            update_data["muxed_video_size_bytes"] = None
            update_data["audio_mux_started_at"] = None
            update_data["audio_mux_completed_at"] = None
            update_data["audio_mux_error_code"] = None
            update_data["audio_mux_error_message"] = None
        job_repository.update_job(
            db,
            job,
            update_data,
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Job temp cleanup completed. Freed bytes: {freed_bytes}",
            stage="cleaning",
        )
        db.commit()
        record_audit_event(
            "job_cleaned",
            "job",
            job.id,
            "Job temporary files cleaned.",
            {"freed_bytes": freed_bytes, "deleted_paths": deleted_paths},
            active_settings,
        )
        return CleanupResponse(
            deleted=True,
            job_id=job.id,
            freed_bytes=freed_bytes,
            deleted_paths=deleted_paths,
            warnings=warnings,
        )
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        job_repository.update_job(
            db,
            job,
            {
                "cleanup_completed_at": time_to_datetime(time.time()),
                "cleanup_error_code": "job_cleanup_failed",
                "cleanup_error_message": "Job temporary files could not be cleaned safely.",
                "current_stage": "failed" if job.status == "failed" else job.current_stage,
            },
        )
        db.commit()
        logger.exception("Job cleanup failed")
        raise JobCleanupFailedError() from exc


def _trim_frames_directory(
    frames_dir: Path,
    *,
    keep_frames: int,
    deleted_paths: list[str],
) -> int:
    if not frames_dir.exists() or not frames_dir.is_dir():
        return 0

    freed_bytes = 0
    frame_files = sorted(frame for frame in frames_dir.glob("*.png") if frame.is_file())
    for frame in frame_files[keep_frames:]:
        freed_bytes += frame.stat().st_size
        frame.unlink()
        deleted_paths.append(str(frame))
    return freed_bytes


def trim_original_frames_after_enhancement(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> int:
    """Free disk as soon as enhancement ends: encoding only reads the enhanced frames.

    Keeps the same first N originals that the post-success cleanup keeps, so the
    before/after preview is unaffected. Best effort: never raises into the pipeline.
    """
    active_settings = _get_active_settings(settings)
    if not active_settings.cleanup_temp_on_success:
        return 0
    try:
        job = _get_job_or_raise(db, job_id)
        originals = get_job_original_frames_path(job.id, active_settings)
        freed_bytes = _trim_frames_directory(
            originals,
            keep_frames=max(0, active_settings.cleanup_keep_preview_frames),
            deleted_paths=[],
        )
        job_repository.update_job(
            db,
            job,
            {"original_frames_size_bytes": get_directory_size_bytes(originals)},
        )
        db.commit()
        logger.info("Original frames trimmed after enhancement: %s (%s bytes)", job.id, freed_bytes)
        return freed_bytes
    except (OSError, SQLAlchemyError, JobNotFoundError):
        db.rollback()
        logger.exception("Could not trim original frames for job %s", job_id)
        return 0


def cleanup_job_temp_after_success(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> CleanupResponse | None:
    """Best-effort temp cleanup after a completed job.

    Keeps the first N frames in both frame directories so the before/after
    preview keeps working, and never raises into the pipeline: a cleanup
    failure must not mark a completed job as failed.
    """
    active_settings = _get_active_settings(settings)
    try:
        job = _get_job_or_raise(db, job_id)
        keep_frames = max(0, active_settings.cleanup_keep_preview_frames)
        deleted_paths: list[str] = []
        freed_bytes = 0

        freed_bytes += _trim_frames_directory(
            get_job_original_frames_path(job.id, active_settings),
            keep_frames=keep_frames,
            deleted_paths=deleted_paths,
        )
        freed_bytes += _trim_frames_directory(
            get_job_enhanced_frames_path(job.id, active_settings),
            keep_frames=keep_frames,
            deleted_paths=deleted_paths,
        )
        freed_bytes += _delete_path_if_requested(
            get_job_encoded_path(job.id, active_settings),
            enabled=True,
            deleted_paths=deleted_paths,
        )
        freed_bytes += _delete_path_if_requested(
            get_job_muxed_path(job.id, active_settings),
            enabled=True,
            deleted_paths=deleted_paths,
        )

        updated_sizes = calculate_job_temp_size(job.id, active_settings)
        job_repository.update_job(
            db,
            job,
            {
                "cleanup_started_at": time_to_datetime(time.time()),
                "cleanup_completed_at": time_to_datetime(time.time()),
                "cleanup_error_code": None,
                "cleanup_error_message": None,
                "temp_size_bytes": updated_sizes["temp_size_bytes"],
                "original_frames_size_bytes": updated_sizes["original_frames_size_bytes"],
                "enhanced_frames_size_bytes": updated_sizes["enhanced_frames_size_bytes"],
                "encoded_size_bytes": updated_sizes["encoded_size_bytes"],
                "muxed_size_bytes": updated_sizes["muxed_size_bytes"],
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Temp cleanup after success completed. Freed bytes: {freed_bytes}. "
            f"Preview frames kept: {keep_frames}",
            stage="completed",
        )
        db.commit()
        record_audit_event(
            "job_cleaned",
            "job",
            job.id,
            "Job temporary files cleaned after successful completion.",
            {"freed_bytes": freed_bytes, "kept_preview_frames": keep_frames},
            active_settings,
        )
        return CleanupResponse(
            deleted=True,
            job_id=job.id,
            freed_bytes=freed_bytes,
            deleted_paths=deleted_paths,
            warnings=[],
        )
    except (OSError, SQLAlchemyError, JobNotFoundError):
        db.rollback()
        logger.warning("Temp cleanup after success failed for job %s", job_id, exc_info=True)
        try:
            job = job_repository.get_job_by_id(db, job_id)
            if job is not None:
                job_repository.update_job(
                    db,
                    job,
                    {
                        "cleanup_error_code": "job_cleanup_failed",
                        "cleanup_error_message": (
                            "Job temporary files could not be cleaned after success."
                        ),
                    },
                )
                db.commit()
        except SQLAlchemyError:
            db.rollback()
        return None


def cleanup_old_temp_files(
    db: Session,
    *,
    older_than_hours: int,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> CleanupBatchResponse:
    active_settings = _get_active_settings(settings)
    jobs_temp_path = get_jobs_temp_path(active_settings)
    jobs_temp_path.mkdir(parents=True, exist_ok=True)
    now = time.time()
    threshold_seconds = older_than_hours * 3600
    items: list[CleanupBatchItem] = []
    freed_total = 0
    jobs_cleaned = 0
    jobs_scanned = 0
    warnings: list[str] = []
    # Jobs que aún necesitan sus frames (en curso, pausados o interrumpidos).
    protected_job_ids = {
        job_id
        for (job_id,) in db.query(ProcessingJob.id).filter(
            ProcessingJob.status.in_(TEMP_PROTECTED_JOB_STATUSES)
        )
    }

    for job_dir in sorted(item for item in jobs_temp_path.iterdir() if item.is_dir()):
        jobs_scanned += 1
        if job_dir.name in protected_job_ids:
            warnings.append(f"Skipped active job {job_dir.name}.")
            continue
        age_seconds = now - job_dir.stat().st_mtime
        if age_seconds < threshold_seconds:
            continue

        freed_bytes = get_directory_size_bytes(job_dir)
        deleted_paths = [str(job_dir)]
        if not dry_run:
            shutil.rmtree(job_dir, ignore_errors=True)
            jobs_cleaned += 1
            freed_total += freed_bytes
        items.append(
            CleanupBatchItem(
                job_id=job_dir.name,
                freed_bytes=freed_bytes,
                deleted_paths=deleted_paths,
            )
        )

    return CleanupBatchResponse(
        dry_run=dry_run,
        deleted=not dry_run,
        jobs_scanned=jobs_scanned,
        jobs_cleaned=jobs_cleaned,
        freed_bytes=freed_total,
        items=items,
        warnings=warnings,
    )


def _cleanup_old_temp_files_in_background(settings: Settings) -> None:
    from app.db import database

    if database.SessionLocal is None:
        return
    db = database.SessionLocal()
    try:
        result = cleanup_old_temp_files(
            db,
            older_than_hours=settings.cleanup_temp_older_than_hours,
            settings=settings,
        )
        if result.jobs_cleaned:
            logger.info(
                "Startup temp cleanup: %s job folders older than %s h, %s bytes freed.",
                result.jobs_cleaned,
                settings.cleanup_temp_older_than_hours,
                result.freed_bytes,
            )
    except Exception:
        logger.exception("Startup temp cleanup failed")
    finally:
        db.close()


def start_startup_temp_cleanup(settings: Settings) -> threading.Thread:
    """Apply the temp max-age setting once per start, without delaying it.

    Without this the setting only worked through POST /system/cleanup/temp, which the UI
    never calls, and the frames of old jobs piled up (gigabytes per long video).
    """
    thread = threading.Thread(
        target=_cleanup_old_temp_files_in_background,
        args=(settings,),
        daemon=True,
        name="startup-temp-cleanup",
    )
    thread.start()
    return thread


def cleanup_all_safe_temp_files(
    db: Session,
    *,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> CleanupBatchResponse:
    active_settings = _get_active_settings(settings)
    return cleanup_old_temp_files(
        db,
        older_than_hours=active_settings.cleanup_temp_older_than_hours,
        dry_run=dry_run,
        settings=active_settings,
    )


def get_storage_usage(settings: Settings | None = None) -> dict[str, int | str | dict[str, int]]:
    active_settings = _get_active_settings(settings)
    storage_path = get_storage_path(active_settings)
    storage_path.mkdir(parents=True, exist_ok=True)
    total_bytes, _, free_bytes = shutil.disk_usage(storage_path)
    breakdown = {
        "db_bytes": get_directory_size_bytes(storage_path / "db"),
        "temp_bytes": get_directory_size_bytes(storage_path / "temp"),
        "imports_bytes": get_directory_size_bytes(storage_path / "imports"),
        "exports_bytes": get_directory_size_bytes(get_exports_path(active_settings)),
        "models_bytes": get_directory_size_bytes(storage_path / "models"),
    }
    used_by_oroya_bytes = sum(breakdown.values())
    return {
        "storage_path": str(storage_path),
        "total_bytes": total_bytes,
        "free_bytes": free_bytes,
        "used_by_oroya_bytes": used_by_oroya_bytes,
        "breakdown": breakdown,
    }
