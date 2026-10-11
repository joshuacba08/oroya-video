import hashlib
import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    InsufficientStorageSpaceError,
    JobInvalidStateError,
    VideoAssetNotFoundError,
    VideoCopyFailedError,
    VideoImportFailedError,
)
from app.core.logging import get_logger
from app.core.paths import get_imports_path, get_video_import_path
from app.db.repositories import video_repository
from app.schemas.video_schema import (
    VideoDeleteResponse,
    VideoImportResponse,
    VideoListResponse,
    VideoProbeRequest,
)
from app.services import job_workspace_service, video_probe_service, video_thumbnail_service

logger = get_logger(__name__)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def calculate_file_fingerprint(path: Path) -> str:
    resolved_path = path.expanduser().resolve()
    stat = resolved_path.stat()
    fingerprint_source = f"{resolved_path}:{stat.st_size}:{stat.st_mtime}"
    return hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()


def _build_stored_path_value(
    video_asset_id: str,
    file_extension: str,
    settings: Settings | None = None,
) -> str:
    active_settings = _get_active_settings(settings)
    storage_root = Path(active_settings.storage_path)
    stored_path = storage_root / "imports" / video_asset_id / f"original{file_extension.lower()}"
    return stored_path.as_posix()


def copy_video_to_storage(
    source_path: Path,
    video_asset_id: str,
    settings: Settings | None = None,
) -> Path:
    active_settings = _get_active_settings(settings)
    imports_path = get_imports_path(active_settings)
    video_import_path = get_video_import_path(video_asset_id, active_settings)
    file_size_bytes = source_path.stat().st_size
    _, _, free_bytes = shutil.disk_usage(imports_path)
    if free_bytes <= file_size_bytes:
        raise InsufficientStorageSpaceError()

    video_import_path.mkdir(parents=True, exist_ok=True)
    target_path = video_import_path / f"original{source_path.suffix.lower()}"

    try:
        shutil.copy2(source_path, target_path)
    except OSError as exc:
        logger.warning("Video copy failed: %s", exc)
        shutil.rmtree(video_import_path, ignore_errors=True)
        raise VideoCopyFailedError() from exc

    logger.info("Video asset copied to storage: %s", target_path)
    return target_path


def import_video_asset(
    db: Session,
    file_path: str,
    source_mode: str = "reference",
    settings: Settings | None = None,
) -> VideoImportResponse:
    active_settings = _get_active_settings(settings)
    logger.info("Video import requested")

    probe_response = video_probe_service.probe_video(VideoProbeRequest(file_path=file_path))
    resolved_source_path = Path(probe_response.file.path).expanduser().resolve()
    fingerprint = calculate_file_fingerprint(resolved_source_path)

    existing_video = video_repository.get_video_asset_by_fingerprint(db, fingerprint)
    if existing_video:
        logger.info("Video already imported: %s", existing_video.id)
        return VideoImportResponse(
            video=video_repository.to_video_asset_response(existing_video),
            already_imported=True,
        )

    video_asset_id = str(uuid.uuid4())
    copied_target_path: Path | None = None
    stored_path: str | None = None

    if source_mode == "copy":
        copied_target_path = copy_video_to_storage(
            source_path=resolved_source_path,
            video_asset_id=video_asset_id,
            settings=active_settings,
        )
        stored_path = _build_stored_path_value(
            video_asset_id=video_asset_id,
            file_extension=resolved_source_path.suffix,
            settings=active_settings,
        )

    video_data = {
        "id": video_asset_id,
        "source_path": str(resolved_source_path),
        "stored_path": stored_path,
        "source_mode": source_mode,
        "file_name": probe_response.file.name,
        "file_extension": probe_response.file.extension,
        "file_size_bytes": probe_response.file.size_bytes,
        "file_size_mb": probe_response.file.size_mb,
        "format_name": probe_response.format.format_name,
        "duration_seconds": probe_response.format.duration_seconds,
        "duration_label": probe_response.format.duration_label,
        "bit_rate": probe_response.format.bit_rate,
        "video_codec": probe_response.video.codec,
        "video_codec_long_name": probe_response.video.codec_long_name,
        "width": probe_response.video.width,
        "height": probe_response.video.height,
        "resolution_label": probe_response.video.resolution_label,
        "fps": probe_response.video.fps,
        "pix_fmt": probe_response.video.pix_fmt,
        "video_profile": probe_response.video.profile,
        "video_bit_rate": probe_response.video.bit_rate,
        "has_audio": probe_response.audio.available,
        "audio_codec": probe_response.audio.codec,
        "audio_codec_long_name": probe_response.audio.codec_long_name,
        "audio_sample_rate": probe_response.audio.sample_rate,
        "audio_channels": probe_response.audio.channels,
        "audio_channel_layout": probe_response.audio.channel_layout,
        "audio_bit_rate": probe_response.audio.bit_rate,
        "streams_json": json.dumps(
            [stream.model_dump(mode="json") for stream in probe_response.streams]
        ),
        "warnings_json": json.dumps(probe_response.warnings),
        "fingerprint": fingerprint,
    }

    try:
        video_asset = video_repository.create_video_asset(db, video_data)
        db.commit()
        db.refresh(video_asset)
    except SQLAlchemyError as exc:
        db.rollback()
        if copied_target_path is not None:
            shutil.rmtree(
                get_video_import_path(video_asset_id, active_settings),
                ignore_errors=True,
            )
        logger.exception("Video import failed for %s", resolved_source_path)
        raise VideoImportFailedError() from exc

    logger.info("Video asset created: %s", video_asset.id)
    return VideoImportResponse(
        video=video_repository.to_video_asset_response(video_asset),
        already_imported=False,
    )


def list_video_assets(db: Session, limit: int = 50, offset: int = 0) -> VideoListResponse:
    items = video_repository.list_video_assets(db, limit=limit, offset=offset)
    total = video_repository.count_video_assets(db)
    logger.info("Video asset listed")
    return VideoListResponse(
        items=[video_repository.to_video_asset_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_video_asset(db: Session, video_id: str):
    video_asset = video_repository.get_video_asset_by_id(db, video_id)
    if not video_asset:
        raise VideoAssetNotFoundError()

    logger.info("Video asset requested: %s", video_asset.id)
    return video_repository.to_video_asset_response(video_asset)


def delete_video_asset(
    db: Session,
    video_id: str,
    settings: Settings | None = None,
) -> VideoDeleteResponse:
    active_settings = _get_active_settings(settings)
    video_asset = video_repository.get_video_asset_by_id(db, video_id)
    if not video_asset:
        raise VideoAssetNotFoundError()

    if any(
        job.status in {"queued", "running", "retrying"}
        for project in video_asset.projects
        for job in project.processing_jobs
    ):
        raise JobInvalidStateError()

    import_path = get_video_import_path(video_asset.id, active_settings)
    delete_copied_file = video_asset.source_mode == "copy"
    job_files = [
        (job.id, project.id) for project in video_asset.projects for job in project.processing_jobs
    ]

    try:
        video_repository.delete_video_asset(db, video_asset)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Video delete failed for %s", video_id)
        raise VideoImportFailedError() from exc

    # Los archivos se borran solo tras confirmar el borrado en la DB.
    video_thumbnail_service.delete_thumbnail(video_id, active_settings)
    for job_id, project_id in job_files:
        job_workspace_service.delete_job_files(job_id, project_id, active_settings)
    if delete_copied_file and import_path.exists():
        try:
            shutil.rmtree(import_path)
        except OSError as exc:
            logger.warning("Could not remove imported files for %s: %s", video_id, exc)

    logger.info("Video asset deleted: %s", video_id)
    return VideoDeleteResponse(deleted=True, video_id=video_id)
