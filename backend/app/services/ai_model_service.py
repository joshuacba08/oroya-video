from __future__ import annotations

import json
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIModelAlreadyExistsError,
    AIModelCreateFailedError,
    AIModelDisabledError,
    AIModelNotFoundError,
    AIModelUpdateFailedError,
    DefaultModelCannotBeDeletedError,
)
from app.core.logging import get_logger
from app.core.paths import get_model_path
from app.db.models import AIModel
from app.db.repositories import ai_model_repository
from app.schemas.ai_model_schema import (
    AIModelCreateRequest,
    AIModelListResponse,
    AIModelRefreshResponse,
    AIModelResponse,
    AIModelUpdateRequest,
)
from app.services.audit_log_service import record_audit_event

logger = get_logger(__name__)
ALLOWED_MODEL_STATUSES = {
    "available",
    "installed",
    "missing",
    "disabled",
    "incompatible",
    "error",
}
DEFAULT_MODELS = [
    {
        "name": "Real-ESRGAN x2",
        "slug": "realesrgan-x2",
        "description": "General purpose 2x video frame upscaling model.",
        "provider": "Real-ESRGAN",
        "category": "upscaling",
        "model_type": "realesrgan",
        "scale_factor": 2,
        "version": "mvp",
        "status": "missing",
        "is_enabled": True,
        "is_installed": False,
        "is_default": True,
        "file_name": "realesrgan-x2.pth",
        "relative_path": "realesrgan/realesrgan-x2.pth",
        "estimated_vram_mb": 4096,
        "supports_gpu": True,
        "supports_cpu": True,
        "capabilities_json": json.dumps(
            {
                "upscale": True,
                "restore": False,
                "frame_interpolation": False,
                "face_enhancement": False,
            }
        ),
        "metadata_json": json.dumps({"quality_tier": "high", "speed_tier": "medium"}),
    },
    {
        "name": "Real-ESRGAN x4",
        "slug": "realesrgan-x4",
        "description": "High quality 4x video frame upscaling model.",
        "provider": "Real-ESRGAN",
        "category": "upscaling",
        "model_type": "realesrgan",
        "scale_factor": 4,
        "version": "mvp",
        "status": "missing",
        "is_enabled": True,
        "is_installed": False,
        "is_default": True,
        "file_name": "realesrgan-x4.pth",
        "relative_path": "realesrgan/realesrgan-x4.pth",
        "estimated_vram_mb": 8192,
        "supports_gpu": True,
        "supports_cpu": True,
        "capabilities_json": json.dumps(
            {
                "upscale": True,
                "restore": False,
                "frame_interpolation": False,
                "face_enhancement": False,
            }
        ),
        "metadata_json": json.dumps({"quality_tier": "very_high", "speed_tier": "slow"}),
    },
    {
        "name": "Real-ESRGAN General",
        "slug": "realesrgan-general",
        "description": "General restoration model for improving compressed or degraded frames.",
        "provider": "Real-ESRGAN",
        "category": "restoration",
        "model_type": "realesrgan",
        "scale_factor": None,
        "version": "mvp",
        "status": "missing",
        "is_enabled": True,
        "is_installed": False,
        "is_default": True,
        "file_name": "realesrgan-general.pth",
        "relative_path": "realesrgan/realesrgan-general.pth",
        "estimated_vram_mb": 4096,
        "supports_gpu": True,
        "supports_cpu": True,
        "capabilities_json": json.dumps(
            {
                "upscale": False,
                "restore": True,
                "frame_interpolation": False,
                "face_enhancement": False,
            }
        ),
        "metadata_json": json.dumps({"quality_tier": "medium", "speed_tier": "fast"}),
    },
]


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _serialize_json(value: dict) -> str:
    return json.dumps(value)


def _resolve_model(model: AIModel, settings: Settings | None = None) -> AIModel:
    install_info = _get_installation_state(model, settings)
    model.is_installed = install_info["is_installed"]
    model.absolute_path = install_info["absolute_path"]
    model.file_size_bytes = install_info["file_size_bytes"]

    if not model.is_enabled:
        model.status = "disabled"
    else:
        model.status = install_info["status"]
    return model


def _get_installation_state(
    model: AIModel,
    settings: Settings | None = None,
) -> dict[str, object]:
    if not model.relative_path:
        return {
            "is_installed": False,
            "absolute_path": None,
            "file_size_bytes": None,
            "status": "available",
        }

    active_settings = _get_active_settings(settings)
    candidate_path = get_model_path(model.relative_path, active_settings)
    if candidate_path.exists() and candidate_path.is_file():
        try:
            file_size_bytes = candidate_path.stat().st_size
        except OSError:
            logger.warning("AI model file missing: %s", candidate_path)
        else:
            logger.info("AI model file detected: %s", candidate_path)
            return {
                "is_installed": True,
                "absolute_path": str(candidate_path),
                "file_size_bytes": file_size_bytes,
                "status": "installed",
            }

    logger.warning("AI model file missing: %s", candidate_path)
    return {
        "is_installed": False,
        "absolute_path": None,
        "file_size_bytes": None,
        "status": "missing",
    }


def _merge_default_metadata(model, default_metadata_json: str) -> bool:
    """Add metadata keys introduced in newer versions (e.g. quality/speed tiers) to
    models seeded by older ones, without overwriting existing values."""
    try:
        current = json.loads(model.metadata_json or "{}")
    except json.JSONDecodeError:
        current = {}
    defaults = json.loads(default_metadata_json)
    missing = {key: value for key, value in defaults.items() if key not in current}
    if not missing:
        return False
    model.metadata_json = json.dumps({**current, **missing})
    return True


def seed_default_models(db: Session, settings: Settings | None = None) -> None:
    active_settings = _get_active_settings(settings)
    logger.info("AI model seed started")
    changed = False
    for model_data in DEFAULT_MODELS:
        existing_model = ai_model_repository.get_ai_model_by_slug(db, model_data["slug"])
        if not existing_model:
            create_data = dict(model_data)
            create_data["id"] = str(uuid.uuid4())
            ai_model_repository.create_ai_model(db, create_data)
            changed = True
        elif _merge_default_metadata(existing_model, model_data["metadata_json"]):
            changed = True

    for model in ai_model_repository.list_ai_models(db, limit=100, offset=0):
        _resolve_model(model, active_settings)
        changed = True

    if changed:
        db.commit()
    logger.info("AI model seed completed")


def list_models(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> AIModelListResponse:
    items = ai_model_repository.list_ai_models(
        db=db,
        limit=limit,
        offset=offset,
        category=category,
        status=status,
        installed=installed,
        enabled=enabled,
    )
    total = ai_model_repository.count_ai_models(
        db=db,
        category=category,
        status=status,
        installed=installed,
        enabled=enabled,
    )
    logger.info("AI model listed")
    return AIModelListResponse(
        items=[ai_model_repository.to_ai_model_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def _get_model_or_raise(db: Session, model_id_or_slug: str) -> AIModel:
    model = ai_model_repository.get_ai_model_by_id(db, model_id_or_slug)
    if not model:
        model = ai_model_repository.get_ai_model_by_slug(db, model_id_or_slug)
    if not model:
        logger.warning("AI model not found: %s", model_id_or_slug)
        raise AIModelNotFoundError()

    return model


def get_model(db: Session, model_id_or_slug: str) -> AIModelResponse:
    model = _get_model_or_raise(db, model_id_or_slug)
    logger.info("AI model requested: %s", model.slug)
    return ai_model_repository.to_ai_model_response(model)


def create_model(
    db: Session,
    request: AIModelCreateRequest,
    settings: Settings | None = None,
) -> AIModelResponse:
    active_settings = _get_active_settings(settings)
    if ai_model_repository.get_ai_model_by_slug(db, request.slug):
        raise AIModelAlreadyExistsError()

    create_data = {
        "id": str(uuid.uuid4()),
        "name": request.name,
        "slug": request.slug,
        "description": request.description,
        "provider": request.provider,
        "category": request.category,
        "model_type": request.model_type,
        "scale_factor": request.scale_factor,
        "version": request.version,
        "status": "available",
        "is_enabled": True,
        "is_installed": False,
        "is_default": False,
        "file_name": request.file_name,
        "relative_path": request.relative_path,
        "absolute_path": None,
        "file_size_bytes": None,
        "estimated_vram_mb": request.estimated_vram_mb,
        "supports_gpu": request.supports_gpu,
        "supports_cpu": request.supports_cpu,
        "capabilities_json": _serialize_json(request.capabilities),
        "metadata_json": _serialize_json(request.metadata),
    }

    try:
        model = ai_model_repository.create_ai_model(db, create_data)
        _resolve_model(model, active_settings)
        db.commit()
        db.refresh(model)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("AI model creation failed")
        raise AIModelCreateFailedError() from exc

    logger.info("AI model created: %s", model.slug)
    return ai_model_repository.to_ai_model_response(model)


def update_model(
    db: Session,
    model_id_or_slug: str,
    request: AIModelUpdateRequest,
    settings: Settings | None = None,
) -> AIModelResponse:
    active_settings = _get_active_settings(settings)
    model = _get_model_or_raise(db, model_id_or_slug)
    update_data = request.model_dump(exclude_unset=True)
    patch_data: dict[str, object] = {}
    if "name" in update_data:
        patch_data["name"] = update_data["name"]
    if "description" in update_data:
        patch_data["description"] = update_data["description"]
    if "relative_path" in update_data:
        patch_data["relative_path"] = update_data["relative_path"]
    if "estimated_vram_mb" in update_data:
        patch_data["estimated_vram_mb"] = update_data["estimated_vram_mb"]
    if "capabilities" in update_data and update_data["capabilities"] is not None:
        patch_data["capabilities_json"] = _serialize_json(update_data["capabilities"])
    if "metadata" in update_data and update_data["metadata"] is not None:
        patch_data["metadata_json"] = _serialize_json(update_data["metadata"])
    if "is_enabled" in update_data:
        patch_data["is_enabled"] = update_data["is_enabled"]
    if "status" in update_data and update_data["status"] is not None:
        if update_data["status"] not in ALLOWED_MODEL_STATUSES:
            raise AIModelUpdateFailedError()
        patch_data["status"] = update_data["status"]

    try:
        model = ai_model_repository.update_ai_model(db, model, patch_data)
        _resolve_model(model, active_settings)
        db.commit()
        db.refresh(model)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("AI model update failed")
        raise AIModelUpdateFailedError() from exc

    logger.info("AI model updated: %s", model.slug)
    return ai_model_repository.to_ai_model_response(model)


def refresh_models(
    db: Session,
    settings: Settings | None = None,
) -> AIModelRefreshResponse:
    active_settings = _get_active_settings(settings)
    logger.info("AI model refresh started")
    items = ai_model_repository.list_ai_models(db, limit=1000, offset=0)
    try:
        for model in items:
            _resolve_model(model, active_settings)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("AI model refresh failed")
        raise AIModelUpdateFailedError() from exc

    refreshed_items = ai_model_repository.list_ai_models(db, limit=1000, offset=0)
    logger.info("AI model refresh completed")
    return AIModelRefreshResponse(
        refreshed=True,
        items=[ai_model_repository.to_ai_model_response(item) for item in refreshed_items],
        total=ai_model_repository.count_ai_models(db),
        limit=1000,
        offset=0,
    )


def set_model_enabled_state(
    db: Session,
    model_id_or_slug: str,
    enabled: bool,
    settings: Settings | None = None,
) -> AIModelResponse:
    active_settings = _get_active_settings(settings)
    model = _get_model_or_raise(db, model_id_or_slug)
    try:
        model = ai_model_repository.update_ai_model(db, model, {"is_enabled": enabled})
        _resolve_model(model, active_settings)
        db.commit()
        db.refresh(model)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("AI model update failed")
        raise AIModelUpdateFailedError() from exc

    logger.info("AI model %s: %s", "enabled" if enabled else "disabled", model.slug)
    record_audit_event(
        "model_enabled" if enabled else "model_disabled",
        "model",
        model.id,
        f"AI model {'enabled' if enabled else 'disabled'}.",
        {"slug": model.slug},
        active_settings,
    )
    return ai_model_repository.to_ai_model_response(model)


def delete_model(db: Session, model_id_or_slug: str) -> dict[str, object]:
    model = _get_model_or_raise(db, model_id_or_slug)
    if model.is_default:
        logger.warning("Default model delete blocked: %s", model.slug)
        raise DefaultModelCannotBeDeletedError()

    try:
        ai_model_repository.delete_ai_model(db, model)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("AI model update failed while deleting")
        raise AIModelUpdateFailedError() from exc

    return {"deleted": True, "model_id": model.id}


def validate_model_available(db: Session, model_slug: str) -> AIModelResponse:
    model = ai_model_repository.get_ai_model_by_slug(db, model_slug)
    if not model:
        raise AIModelNotFoundError()
    if not model.is_enabled:
        raise AIModelDisabledError()

    return ai_model_repository.to_ai_model_response(model)
