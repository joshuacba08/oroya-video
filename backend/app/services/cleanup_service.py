from __future__ import annotations

import shutil
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import JobCleanupFailedError, JobInvalidStateError, JobNotFoundError
from app.core.logging import get_logger
from app.core.paths import (
    get_directory_size_bytes,
    get_job_encoded_path,
    get_job_enhanced_frames_path,
    get_job_muxed_path,
    get_job_original_frames_path,
    get_jobs_temp_path,
    get_storage_path,
)
from app.db.repositories import job_repository
from app.schemas.hardening_schema import CleanupBatchItem, CleanupBatchResponse, CleanupResponse
from app.services.audit_log_service import record_audit_event
from app.services.frame_extraction_service import time_to_datetime

logger = get_logger(__name__)


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

    for job_dir in sorted(item for item in jobs_temp_path.iterdir() if item.is_dir()):
        jobs_scanned += 1
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
        warnings=[],
    )


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
        "exports_bytes": get_directory_size_bytes(storage_path / "exports"),
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
