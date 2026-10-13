from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    AIModelDisabledError,
    AIModelNotFoundError,
    InvalidProjectConfigurationError,
    JobInvalidStateError,
    OroyaVideoError,
    ProjectCreateFailedError,
    ProjectDeleteFailedError,
    ProjectNotFoundError,
    ProjectUpdateFailedError,
    VideoAssetFileMissingError,
    VideoAssetNotFoundError,
)
from app.core.logging import get_logger
from app.core.paths import resolve_path
from app.db.models import Project, VideoAsset
from app.db.repositories import (
    ai_model_repository,
    export_repository,
    job_repository,
    project_repository,
    video_repository,
)
from app.schemas.project_schema import (
    ProjectCreateRequest,
    ProjectDeleteResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectUpdateRequest,
    ProjectWorkspaceResponse,
)
from app.services import job_workspace_service
from app.services.job_contract_service import build_job_actions, is_preview_available
from app.services.preview_service import get_compare_frame_info, get_recommended_preview_frame_index

logger = get_logger(__name__)

# Jobs que el worker puede estar procesando: no se borran por cascada.
ACTIVE_JOB_STATUSES = {"queued", "running", "retrying"}

DEFAULT_ENHANCEMENT_CONFIG = {
    "model_id": "realesrgan-x2",
    "scale": "2x",
    "denoise": 0,
    "sharpen": 0,
    "compression_cleanup": False,
    "face_restore": {"enabled": False, "strength": 0.5},
}
DEFAULT_EXPORT_CONFIG = {
    "format": "mp4",
    "codec": "h264",
    "keep_audio": True,
    "output_resolution": "2x",
}
DEFAULT_WORKSPACE_STATE = {
    "selected_frame": 0,
    "compare_mode": "split",
    "zoom": "fit",
    "active_panel": "inspector",
    "timeline_position": 0,
    "inspector_open": True,
}
ALLOWED_PROJECT_STATUSES = {
    "draft",
    "ready",
    "processing",
    "completed",
    "failed",
    "archived",
}
ALLOWED_ENHANCEMENT_KEYS = {
    "model_id",
    "scale",
    "denoise",
    "sharpen",
    "compression_cleanup",
    "face_restore",
}
ALLOWED_EXPORT_KEYS = {
    "format",
    "codec",
    "keep_audio",
    "output_resolution",
    # Opcionales: nombre del archivo y carpeta elegidos por el usuario (vacío = por defecto).
    "file_name",
    "output_dir",
}
EXPORT_FILE_NAME_MAX_LENGTH = 120
ALLOWED_WORKSPACE_KEYS = {
    "selected_frame",
    "compare_mode",
    "zoom",
    "active_panel",
    "timeline_position",
    "inspector_open",
}
ALLOWED_SCALE_VALUES = {"original", "2x", "4x"}
ALLOWED_COMPARE_MODES = {"split", "slider", "side_by_side"}
ALLOWED_ZOOM_VALUES = {"fit", "50%", "100%", "200%", "400%"}
ALLOWED_ACTIVE_PANELS = {"inspector", "settings", "exports", "logs"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _merge_config(existing: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    if incoming is None:
        return dict(existing)
    merged = dict(existing)
    merged.update(incoming)
    return merged


def _validate_enhancement_config(config: dict[str, Any]) -> dict[str, Any]:
    unknown_keys = set(config) - ALLOWED_ENHANCEMENT_KEYS
    if unknown_keys:
        raise InvalidProjectConfigurationError("Enhancement config contains unsupported fields.")
    if config.get("scale") not in ALLOWED_SCALE_VALUES:
        raise InvalidProjectConfigurationError("Enhancement config scale is invalid.")
    if not _is_non_negative_int(config.get("denoise")) or config["denoise"] > 100:
        raise InvalidProjectConfigurationError(
            "Enhancement config denoise must be between 0 and 100."
        )
    if not _is_non_negative_int(config.get("sharpen")) or config["sharpen"] > 100:
        raise InvalidProjectConfigurationError(
            "Enhancement config sharpen must be between 0 and 100."
        )
    if not isinstance(config.get("compression_cleanup"), bool):
        raise InvalidProjectConfigurationError(
            "Enhancement config compression_cleanup must be boolean."
        )
    if not isinstance(config.get("model_id"), str) or not config["model_id"].strip():
        raise InvalidProjectConfigurationError("Enhancement config model_id is required.")
    face_restore = config.get("face_restore")
    if face_restore is not None:
        _validate_face_restore(face_restore)
    return config


def _validate_face_restore(value: Any) -> None:
    if not isinstance(value, dict) or set(value) - {"enabled", "strength"}:
        raise InvalidProjectConfigurationError("Enhancement config face_restore is invalid.")
    if not isinstance(value.get("enabled"), bool):
        raise InvalidProjectConfigurationError("face_restore.enabled must be boolean.")
    strength = value.get("strength")
    if (
        isinstance(strength, bool)
        or not isinstance(strength, (int, float))
        or not 0 <= strength <= 1
    ):
        raise InvalidProjectConfigurationError("face_restore.strength must be between 0 and 1.")


def _validate_export_config(config: dict[str, Any]) -> dict[str, Any]:
    unknown_keys = set(config) - ALLOWED_EXPORT_KEYS
    if unknown_keys:
        raise InvalidProjectConfigurationError("Export config contains unsupported fields.")
    if config.get("format") != "mp4":
        raise InvalidProjectConfigurationError("Export config format must be mp4.")
    if config.get("codec") != "h264":
        raise InvalidProjectConfigurationError("Export config codec must be h264.")
    if not isinstance(config.get("keep_audio"), bool):
        raise InvalidProjectConfigurationError("Export config keep_audio must be boolean.")
    if config.get("output_resolution") not in ALLOWED_SCALE_VALUES:
        raise InvalidProjectConfigurationError("Export config output_resolution is invalid.")
    file_name = config.get("file_name")
    if file_name is not None and (
        not isinstance(file_name, str) or len(file_name) > EXPORT_FILE_NAME_MAX_LENGTH
    ):
        raise InvalidProjectConfigurationError("Export file name is invalid.")
    output_dir = config.get("output_dir")
    if output_dir is not None and output_dir != "":
        if not isinstance(output_dir, str) or not Path(output_dir).expanduser().is_absolute():
            raise InvalidProjectConfigurationError("The export folder must be an absolute path.")
    return config


def _validate_workspace_state(config: dict[str, Any]) -> dict[str, Any]:
    unknown_keys = set(config) - ALLOWED_WORKSPACE_KEYS
    if unknown_keys:
        raise InvalidProjectConfigurationError("Workspace state contains unsupported fields.")
    if not _is_non_negative_int(config.get("selected_frame")):
        raise InvalidProjectConfigurationError("Workspace state selected_frame must be >= 0.")
    if config.get("compare_mode") not in ALLOWED_COMPARE_MODES:
        raise InvalidProjectConfigurationError("Workspace state compare_mode is invalid.")
    if config.get("zoom") not in ALLOWED_ZOOM_VALUES:
        raise InvalidProjectConfigurationError("Workspace state zoom is invalid.")
    if config.get("active_panel") not in ALLOWED_ACTIVE_PANELS:
        raise InvalidProjectConfigurationError("Workspace state active_panel is invalid.")
    if not _is_non_negative_int(config.get("timeline_position")):
        raise InvalidProjectConfigurationError("Workspace state timeline_position must be >= 0.")
    if not isinstance(config.get("inspector_open"), bool):
        raise InvalidProjectConfigurationError("Workspace state inspector_open must be boolean.")
    return config


def _get_project_or_raise(db: Session, project_id: str) -> Project:
    project = project_repository.get_project_by_id(db, project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        raise ProjectNotFoundError()

    return project


def _get_video_asset_or_raise(db: Session, video_asset_id: str) -> VideoAsset:
    video_asset = video_repository.get_video_asset_by_id(db, video_asset_id)
    if not video_asset:
        logger.warning("Video asset not found while creating project: %s", video_asset_id)
        raise VideoAssetNotFoundError()

    return video_asset


def _resolve_video_asset_active_path(video_asset: VideoAsset) -> Path:
    if video_asset.source_mode == "copy" and video_asset.stored_path:
        return resolve_path(video_asset.stored_path)
    return Path(video_asset.source_path).expanduser().resolve()


def _ensure_video_asset_file_available(video_asset: VideoAsset) -> None:
    active_path = _resolve_video_asset_active_path(video_asset)
    if not active_path.exists() or not active_path.is_file():
        logger.warning("Video asset file missing while creating project: %s", active_path)
        raise VideoAssetFileMissingError()


def _validate_model_reference(db: Session, model_id_or_slug: str) -> str:
    ai_model = ai_model_repository.get_ai_model_by_id(db, model_id_or_slug)
    if not ai_model:
        ai_model = ai_model_repository.get_ai_model_by_slug(db, model_id_or_slug)
    if not ai_model:
        raise AIModelNotFoundError()
    if not ai_model.is_enabled:
        raise AIModelDisabledError()
    return ai_model.slug


def _serialize_config(data: dict[str, Any]) -> str:
    return json.dumps(data)


def _build_project_configs(
    db: Session,
    enhancement_config: dict[str, Any] | None,
    export_config: dict[str, Any] | None,
    workspace_state: dict[str, Any] | None,
    existing_project: Project | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    existing_enhancement = (
        project_repository.to_project_response(existing_project).enhancement_config
        if existing_project
        else DEFAULT_ENHANCEMENT_CONFIG
    )
    existing_export = (
        project_repository.to_project_response(existing_project).export_config
        if existing_project
        else DEFAULT_EXPORT_CONFIG
    )
    existing_workspace = (
        project_repository.to_project_response(existing_project).workspace_state
        if existing_project
        else DEFAULT_WORKSPACE_STATE
    )

    merged_enhancement = _validate_enhancement_config(
        _merge_config(existing_enhancement, enhancement_config)
    )
    merged_export = _validate_export_config(_merge_config(existing_export, export_config))
    merged_workspace = _validate_workspace_state(_merge_config(existing_workspace, workspace_state))
    merged_enhancement["model_id"] = _validate_model_reference(
        db,
        merged_enhancement["model_id"],
    )
    return merged_enhancement, merged_export, merged_workspace


def create_project(db: Session, request: ProjectCreateRequest) -> ProjectDetailResponse:
    logger.info("Project create requested")
    video_asset = _get_video_asset_or_raise(db, request.video_asset_id)
    _ensure_video_asset_file_available(video_asset)
    enhancement_config, export_config, workspace_state = _build_project_configs(
        db=db,
        enhancement_config=request.enhancement_config,
        export_config=request.export_config,
        workspace_state=request.workspace_state,
    )

    project_data = {
        "id": str(uuid.uuid4()),
        "name": request.name,
        "description": request.description,
        "video_asset_id": request.video_asset_id,
        "status": "draft",
        "enhancement_config_json": _serialize_config(enhancement_config),
        "export_config_json": _serialize_config(export_config),
        "workspace_state_json": _serialize_config(workspace_state),
    }

    try:
        project = project_repository.create_project(db, project_data)
        db.commit()
        db.refresh(project)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Project creation failed")
        raise ProjectCreateFailedError() from exc

    logger.info("Project created: %s", project.id)
    return ProjectDetailResponse(
        project=project_repository.to_project_response(project),
        video=video_repository.to_video_asset_response(video_asset),
    )


def list_projects(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> ProjectListResponse:
    logger.info("Project list requested")
    items = project_repository.list_projects(
        db=db,
        limit=limit,
        offset=offset,
        status=status,
        search=search,
    )
    total = project_repository.count_projects(db=db, status=status, search=search)
    return ProjectListResponse(
        items=[project_repository.to_project_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_project_detail(
    db: Session,
    project_id: str,
    touch_last_opened: bool = True,
) -> ProjectDetailResponse:
    project = _get_project_or_raise(db, project_id)
    video_asset = _get_video_asset_or_raise(db, project.video_asset_id)
    logger.info("Project detail requested: %s", project.id)

    if touch_last_opened:
        try:
            project = project_repository.update_project(
                db,
                project,
                {"last_opened_at": _utcnow()},
            )
            db.commit()
            db.refresh(project)
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Project update failed while touching last_opened_at")
            raise ProjectUpdateFailedError() from exc

    return ProjectDetailResponse(
        project=project_repository.to_project_response(project),
        video=video_repository.to_video_asset_response(video_asset),
    )


def get_project_workspace(
    db: Session,
    project_id: str,
    touch_last_opened: bool = True,
    settings: Settings | None = None,
) -> ProjectWorkspaceResponse:
    detail = get_project_detail(db, project_id, touch_last_opened=touch_last_opened)
    latest_job = (
        job_repository.list_jobs(db, limit=1, offset=0, project_id=project_id)[0]
        if job_repository.count_jobs(db, project_id=project_id) > 0
        else None
    )
    latest_export = (
        export_repository.list_exports(db, limit=1, offset=0, project_id=project_id)[0]
        if export_repository.count_exports(db, project_id=project_id) > 0
        else None
    )
    selected_model = ai_model_repository.get_ai_model_by_slug(
        db,
        detail.project.enhancement_config["model_id"],
    )
    preview_payload: dict[str, Any] = {"available": False, "recommended": None}
    if latest_job is not None and is_preview_available(latest_job):
        # Los frames pueden haberse borrado (limpieza con 0 frames conservados, borrado
        # manual): el workspace debe abrir igualmente, solo que sin preview.
        try:
            frame_index = get_recommended_preview_frame_index(db, latest_job.id)
            preview_payload = {
                "available": True,
                "recommended": get_compare_frame_info(
                    db,
                    latest_job.id,
                    frame_index,
                    settings=settings,
                ).model_dump(mode="json"),
            }
        except OroyaVideoError as exc:
            logger.warning("Workspace preview unavailable for %s: %s", latest_job.id, exc)
    latest_job_actions = build_job_actions(latest_job) if latest_job is not None else None
    return ProjectWorkspaceResponse(
        project=detail.project,
        video=detail.video,
        latest_job=job_repository.to_job_response(latest_job).model_dump(mode="json")
        if latest_job is not None
        else None,
        latest_export=export_repository.to_export_asset_response(latest_export).model_dump(
            mode="json"
        )
        if latest_export is not None
        else None,
        models={
            "selected": ai_model_repository.to_ai_model_response(selected_model).model_dump(
                mode="json"
            )
            if selected_model is not None
            else None,
            "available": [
                ai_model_repository.to_ai_model_response(model).model_dump(mode="json")
                for model in ai_model_repository.list_ai_models(db, limit=100, offset=0)
            ],
        },
        preview=preview_payload,
        actions={
            "can_create_job": True,
            "can_start_latest_job": bool(latest_job_actions and latest_job_actions["can_start"]),
            "can_cancel_latest_job": latest_job is not None
            and latest_job_actions is not None
            and latest_job_actions["can_cancel"],
            "can_retry_latest_job": bool(latest_job_actions and latest_job_actions["can_retry"]),
            "can_export": latest_export is not None,
        },
    )


def update_project(
    db: Session,
    project_id: str,
    request: ProjectUpdateRequest,
) -> ProjectDetailResponse:
    project = _get_project_or_raise(db, project_id)
    video_asset = _get_video_asset_or_raise(db, project.video_asset_id)

    update_data = request.model_dump(exclude_unset=True)
    patch_data: dict[str, Any] = {}

    if "status" in update_data:
        if update_data["status"] not in ALLOWED_PROJECT_STATUSES:
            raise InvalidProjectConfigurationError("Project status is invalid.")
        patch_data["status"] = update_data["status"]
    if "name" in update_data:
        patch_data["name"] = update_data["name"]
    if "description" in update_data:
        patch_data["description"] = update_data["description"]

    enhancement_config, export_config, workspace_state = _build_project_configs(
        db=db,
        enhancement_config=update_data.get("enhancement_config"),
        export_config=update_data.get("export_config"),
        workspace_state=update_data.get("workspace_state"),
        existing_project=project,
    )
    if "enhancement_config" in update_data:
        patch_data["enhancement_config_json"] = _serialize_config(enhancement_config)
    if "export_config" in update_data:
        patch_data["export_config_json"] = _serialize_config(export_config)
    if "workspace_state" in update_data:
        patch_data["workspace_state_json"] = _serialize_config(workspace_state)

    try:
        project = project_repository.update_project(db, project, patch_data)
        db.commit()
        db.refresh(project)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Project update failed")
        raise ProjectUpdateFailedError() from exc

    logger.info("Project updated: %s", project.id)
    return ProjectDetailResponse(
        project=project_repository.to_project_response(project),
        video=video_repository.to_video_asset_response(video_asset),
    )


def delete_project(
    db: Session,
    project_id: str,
    settings: Settings | None = None,
) -> ProjectDeleteResponse:
    project = _get_project_or_raise(db, project_id)
    if any(job.status in ACTIVE_JOB_STATUSES for job in project.processing_jobs):
        raise JobInvalidStateError()
    job_ids = [job.id for job in project.processing_jobs]
    export_paths = job_workspace_service.collect_export_file_paths(db, job_ids)
    try:
        project_repository.delete_project(db, project)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Project delete failed")
        raise ProjectDeleteFailedError() from exc

    for job_id in job_ids:
        job_workspace_service.delete_job_files(
            job_id, project_id, settings, export_paths.get(job_id)
        )

    logger.info("Project deleted: %s", project_id)
    return ProjectDeleteResponse(deleted=True, project_id=project_id)
