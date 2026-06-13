from __future__ import annotations

import re
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    ExportAssetNotFoundError,
    FinalExportFailedError,
    InsufficientExportStorageError,
    JobNotFoundError,
    MuxedVideoNotFoundError,
)
from app.core.logging import get_logger
from app.core.paths import (
    ensure_job_export_directory,
    get_exports_path,
    to_client_path,
)
from app.db.repositories import (
    export_repository,
    job_repository,
    project_repository,
    video_repository,
)
from app.schemas.export_schema import (
    ExportAssetResponse,
    ExportDeleteResponse,
    ExportListResponse,
    ExportOpenResponse,
)
from app.schemas.job_schema import FinalExportSummaryResponse
from app.services.audit_log_service import record_audit_event
from app.services.frame_extraction_service import time_to_datetime
from app.services.pipeline_progress import EXPORT_PROGRESS_END, EXPORT_PROGRESS_START

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "oroya_project"


def _format_size_mb(size_bytes: int) -> float:
    return round(size_bytes / (1024**2), 2)


def ensure_export_storage_capacity(
    muxed_video_path: Path,
    settings: Settings | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    exports_path = get_exports_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(exports_path)
    required_bytes = max(muxed_video_path.stat().st_size, 1)
    if free_bytes < required_bytes:
        raise InsufficientExportStorageError()


def build_export_file_name(project, job) -> str:
    base_name = f"{_slugify(project.name)}_oroya_export"
    return f"{base_name}.mp4"


def _build_unique_export_destination(export_dir: Path, file_name: str) -> Path:
    destination = export_dir / file_name
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 2
    while True:
        candidate = export_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def copy_muxed_video_to_exports(
    muxed_video_path: Path,
    destination_path: Path,
) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(muxed_video_path, destination_path)
    return destination_path


def _mark_export_failed(
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
            "export_error_code": error_code,
            "export_error_message": error_message,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "error",
        f"Final export failed: {error_message}",
        stage="failed",
    )
    db.commit()


def create_final_export_for_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
):
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    if job.cancel_requested or job.status == "cancelled":
        return None
    if not job.muxed_video_path:
        _mark_export_failed(
            db,
            job,
            error_code="muxed_video_not_found",
            error_message="Muxed video was not found for this job.",
        )
        raise MuxedVideoNotFoundError()

    muxed_video_path = Path(job.muxed_video_path)
    if not muxed_video_path.exists() or not muxed_video_path.is_file():
        _mark_export_failed(
            db,
            job,
            error_code="muxed_video_not_found",
            error_message="Muxed video was not found for this job.",
        )
        raise MuxedVideoNotFoundError()

    try:
        ensure_export_storage_capacity(muxed_video_path, active_settings)
    except InsufficientExportStorageError as exc:
        _mark_export_failed(
            db,
            job,
            error_code=exc.error_code,
            error_message=exc.message,
        )
        raise

    project = project_repository.get_project_by_id(db, job.project_id)
    video_asset = video_repository.get_video_asset_by_id(db, job.video_asset_id)
    if project is None or video_asset is None:
        _mark_export_failed(
            db,
            job,
            error_code="final_export_failed",
            error_message="Final export could not be created.",
        )
        raise FinalExportFailedError()

    export_dir = ensure_job_export_directory(project.id, job.id, active_settings)
    destination_path = _build_unique_export_destination(
        export_dir,
        build_export_file_name(project, job),
    )
    started_at = time.monotonic()
    now = time.time()

    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "exporting",
            "export_started_at": job.export_started_at or time_to_datetime(now),
            "export_error_code": None,
            "export_error_message": None,
            "error_code": None,
            "error_message": None,
            "progress_percent": max(job.progress_percent, EXPORT_PROGRESS_START),
        },
    )
    job_repository.create_job_log(db, job.id, "info", "Final export started.", stage="exporting")
    db.commit()

    db.refresh(job)
    if job.cancel_requested or job.status == "cancelled":
        job_repository.update_job(
            db,
            job,
            {
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancelled_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "warning",
            "Final export cancelled by user.",
            stage="cancelled",
        )
        db.commit()
        return None

    try:
        copied_path = copy_muxed_video_to_exports(muxed_video_path, destination_path)
    except (OSError, shutil.Error, SQLAlchemyError) as exc:
        db.rollback()
        _mark_export_failed(
            db,
            job,
            error_code="final_export_failed",
            error_message="Final export could not be created.",
        )
        raise FinalExportFailedError() from exc

    db.refresh(job)
    if job.cancel_requested or job.status == "cancelled":
        job_repository.update_job(
            db,
            job,
            {
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancelled_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "warning",
            "Final export cancelled by user.",
            stage="cancelled",
        )
        db.commit()
        return None

    copied_size = copied_path.stat().st_size
    export_asset = export_repository.create_export_asset(
        db,
        {
            "id": str(uuid.uuid4()),
            "project_id": project.id,
            "job_id": job.id,
            "video_asset_id": video_asset.id,
            "file_path": str(copied_path),
            "file_name": copied_path.name,
            "file_extension": copied_path.suffix.lower(),
            "file_size_bytes": copied_size,
            "file_size_mb": _format_size_mb(copied_size),
            "format": "mp4",
            "video_codec": job.encoding_codec or video_asset.video_codec,
            "audio_codec": job.audio_codec,
            "has_audio": job.audio_strategy not in {None, "none"},
            "audio_strategy": job.audio_strategy,
            "resolution_label": video_asset.resolution_label,
            "width": video_asset.width,
            "height": video_asset.height,
            "fps": job.encoding_fps or video_asset.fps,
            "duration_seconds": video_asset.duration_seconds,
            "duration_label": video_asset.duration_label,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        },
    )
    job_repository.update_job(
        db,
        job,
        {
            "export_id": export_asset.id,
            "final_export_path": str(copied_path),
            "final_export_file_name": copied_path.name,
            "final_export_size_bytes": copied_size,
            "output_path": str(copied_path),
            "export_completed_at": time_to_datetime(time.time()),
            "progress_percent": EXPORT_PROGRESS_END,
            "elapsed_time_seconds": int(time.monotonic() - started_at),
            "exports_size_bytes": copied_size,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Final export path: {copied_path}",
        stage="exporting",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Final export completed.",
        stage="exporting",
    )
    db.commit()
    db.refresh(export_asset)
    record_audit_event(
        "export_created",
        "export",
        export_asset.id,
        "Final export created.",
        {"job_id": job.id, "path": str(copied_path)},
        active_settings,
    )
    logger.info("Final export completed: %s", job.id)
    return export_asset


def get_export_by_id(
    db: Session,
    export_id: str,
) -> ExportAssetResponse:
    export_asset = export_repository.get_export_by_id(db, export_id)
    if not export_asset:
        raise ExportAssetNotFoundError()
    return export_repository.to_export_asset_response(export_asset)


def list_exports(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    project_id: str | None = None,
    job_id: str | None = None,
) -> ExportListResponse:
    items = export_repository.list_exports(
        db,
        limit=limit,
        offset=offset,
        project_id=project_id,
        job_id=job_id,
    )
    total = export_repository.count_exports(db, project_id=project_id, job_id=job_id)
    return ExportListResponse(
        items=[export_repository.to_export_asset_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_export_for_job(
    db: Session,
    job_id: str,
) -> ExportAssetResponse:
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()

    export_asset = None
    if job.export_id:
        export_asset = export_repository.get_export_by_id(db, job.export_id)
    if export_asset is None:
        exports = export_repository.get_exports_by_job_id(db, job_id)
        export_asset = exports[0] if exports else None
    if export_asset is None:
        raise ExportAssetNotFoundError()
    return export_repository.to_export_asset_response(export_asset)


def get_final_export_summary(
    db: Session,
    job_id: str,
) -> FinalExportSummaryResponse:
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    return FinalExportSummaryResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        export_id=job.export_id,
        final_export_path=job.final_export_path,
        final_export_file_name=job.final_export_file_name,
        final_export_size_bytes=job.final_export_size_bytes,
        export_started_at=job.export_started_at,
        export_completed_at=job.export_completed_at,
        export_error_code=job.export_error_code,
        export_error_message=job.export_error_message,
    )


def delete_export(
    db: Session,
    export_id: str,
    delete_file: bool = False,
) -> ExportDeleteResponse:
    export_asset = export_repository.get_export_by_id(db, export_id)
    if not export_asset:
        raise ExportAssetNotFoundError()

    file_deleted = False
    file_path = Path(export_asset.file_path)
    if delete_file and file_path.exists() and file_path.is_file():
        file_path.unlink()
        file_deleted = True

    job = job_repository.get_job_by_id(db, export_asset.job_id)
    if job and job.export_id == export_asset.id:
        job_repository.update_job(
            db,
            job,
            {
                "export_id": None,
                "final_export_path": None,
                "final_export_file_name": None,
                "final_export_size_bytes": None,
                "output_path": None,
            },
        )

    export_repository.delete_export_asset(db, export_asset)
    db.commit()
    record_audit_event(
        "export_deleted",
        "export",
        export_id,
        "Export deleted.",
        {"file_deleted": file_deleted},
    )
    return ExportDeleteResponse(
        deleted=True,
        export_id=export_id,
        file_deleted=file_deleted,
    )


def build_export_open_response(
    db: Session,
    export_id: str,
    *,
    open_folder: bool = False,
    settings: Settings | None = None,
) -> ExportOpenResponse:
    active_settings = _get_active_settings(settings)
    export_asset = export_repository.get_export_by_id(db, export_id)
    if not export_asset:
        raise ExportAssetNotFoundError()

    target_path = Path(export_asset.file_path)
    if open_folder:
        target_path = target_path.parent

    available = target_path.exists()
    label = "folder" if open_folder else "file"
    path_value = to_client_path(target_path, active_settings)
    return ExportOpenResponse(
        export_id=export_id,
        path=path_value,
        available=available,
        message=(
            f"Export {label} is available. Desktop open integration will be handled by Tauri."
            if available
            else f"Export {label} is not available."
        ),
    )
