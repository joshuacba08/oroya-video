from __future__ import annotations

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
    get_exports_path,
    get_project_export_dir,
    project_display_name,
    remove_empty_export_dirs,
    safe_folder_name,
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
from app.schemas.video_schema import VideoProbeRequest
from app.services import desktop_open_service, video_probe_service
from app.services.audit_log_service import record_audit_event
from app.services.frame_extraction_service import time_to_datetime
from app.services.pipeline_progress import EXPORT_PROGRESS_END, EXPORT_PROGRESS_START
from app.utils.enhancement_config import parse_enhancement_config_json

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _format_size_mb(size_bytes: int) -> float:
    return round(size_bytes / (1024**2), 2)


def _job_export_config(job) -> dict[str, object]:
    # Instantánea del job: cambiar el proyecto mientras procesa no altera su exportación.
    return parse_enhancement_config_json(job.export_config_json)


def _existing_parent(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path


def ensure_export_storage_capacity(
    muxed_video_path: Path,
    settings: Settings | None = None,
    target_dir: Path | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    target = target_dir or get_exports_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(_existing_parent(target))
    required_bytes = max(muxed_video_path.stat().st_size, 1)
    if free_bytes < required_bytes:
        raise InsufficientExportStorageError()


def _export_label(job) -> str:
    """`Oroya 2x`, `Oroya 4x 60fps`...: what was done, readable in the file name."""
    enhancement = parse_enhancement_config_json(job.enhancement_config_json)
    parts = ["Oroya"]
    scale = str(enhancement.get("scale") or "").lower()
    if scale in {"2x", "4x"}:
        parts.append(scale)
    interpolation = enhancement.get("interpolation")
    if isinstance(interpolation, dict) and interpolation.get("enabled"):
        # Los fps con que se codificó (resuelve "2x"); antes de codificar, el objetivo fijo.
        target_fps = getattr(job, "encoding_fps", None) or interpolation.get("target_fps")
        if isinstance(target_fps, (int, float)) and not isinstance(target_fps, bool):
            parts.append(f"{round(target_fps):g}fps")
    return " ".join(parts)


def build_export_file_name(project, job) -> str:
    custom_name = _job_export_config(job).get("file_name")
    if isinstance(custom_name, str) and custom_name.strip():
        stem = safe_folder_name(project_display_name(custom_name))
    else:
        stem = f"{safe_folder_name(project_display_name(project.name))} ({_export_label(job)})"
    return f"{stem}.mp4"


def get_export_directory(project, job, settings: Settings | None = None) -> Path:
    output_dir = _job_export_config(job).get("output_dir")
    return get_project_export_dir(
        project.name,
        settings,
        output_dir if isinstance(output_dir, str) and output_dir.strip() else None,
    )


def _build_unique_export_destination(export_dir: Path, file_name: str) -> Path:
    destination = export_dir / file_name
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 2
    while True:
        candidate = export_dir / f"{stem} ({counter}){suffix}"
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
        output_dir = _job_export_config(job).get("output_dir")
        ensure_export_storage_capacity(
            muxed_video_path,
            active_settings,
            Path(output_dir) if isinstance(output_dir, str) and output_dir.strip() else None,
        )
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

    export_dir = get_export_directory(project, job, active_settings)
    export_dir.mkdir(parents=True, exist_ok=True)
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
    width, height = _probe_output_dimensions(copied_path)
    if width is None or height is None:
        width, height = video_asset.width, video_asset.height
    resolution_label = f"{width}x{height}" if width and height else video_asset.resolution_label
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
            "resolution_label": resolution_label,
            "width": width,
            "height": height,
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


def get_export_file_path(
    db: Session,
    export_id: str,
) -> Path:
    export_asset = export_repository.get_export_by_id(db, export_id)
    if not export_asset or not export_asset.file_path:
        raise ExportAssetNotFoundError()
    file_path = Path(export_asset.file_path)
    if not file_path.exists() or not file_path.is_file():
        raise ExportAssetNotFoundError()
    return file_path


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
        remove_empty_export_dirs(file_path)

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


def _probe_output_dimensions(path: Path) -> tuple[int | None, int | None]:
    """Real output size: after a 2x/4x upscale it differs from the source video."""
    try:
        probe = video_probe_service.probe_video(VideoProbeRequest(file_path=str(path)))
    except Exception:  # noqa: BLE001 - metadata only; never fail the export over it
        logger.warning("Could not probe export dimensions: %s", path)
        return None, None
    return probe.video.width, probe.video.height


def build_export_open_response(
    db: Session,
    export_id: str,
    *,
    open_folder: bool = False,
    launch: bool = False,
    settings: Settings | None = None,
) -> ExportOpenResponse:
    active_settings = _get_active_settings(settings)
    export_asset = export_repository.get_export_by_id(db, export_id)
    if not export_asset:
        raise ExportAssetNotFoundError()

    file_path = Path(export_asset.file_path)
    target_path = file_path.parent if open_folder else file_path

    available = target_path.exists()
    label = "folder" if open_folder else "file"
    opened = False
    if available and launch:
        if open_folder:
            opened = desktop_open_service.reveal_in_folder(
                file_path if file_path.exists() else target_path
            )
        else:
            opened = desktop_open_service.open_file(target_path)

    if not available:
        message = f"Export {label} is not available."
    elif launch and not opened:
        message = f"Export {label} is available but could not be opened."
    elif opened:
        message = f"Export {label} opened."
    else:
        message = f"Export {label} is available."

    return ExportOpenResponse(
        export_id=export_id,
        path=to_client_path(target_path, active_settings),
        available=available,
        opened=opened,
        message=message,
    )
