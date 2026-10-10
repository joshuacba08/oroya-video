from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import InvalidProjectConfigurationError, JobInvalidStateError
from app.core.logging import get_logger
from app.core.paths import get_exports_path, get_models_path, get_settings_file_path, get_temp_path
from app.db.models import ProcessingJob
from app.schemas.settings_schema import (
    CleanupSettingsResponse,
    GeneralSettingsResponse,
    ProcessingSettingsResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
    StorageSettingsResponse,
)

logger = get_logger(__name__)
DEFAULT_SETTINGS_FILE = {
    "general": {
        "language": "en",
        "theme": "dark",
    },
    "processing": {},
    "cleanup": {},
}
ALLOWED_FRAME_ENHANCERS = {"mock", "realesrgan"}
ALLOWED_AI_DEVICES = {"auto", "cpu", "cuda"}


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _get_settings_file(settings: Settings | None = None) -> Path:
    settings_file = get_settings_file_path(settings)
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    return settings_file


def _load_ui_settings(settings: Settings | None = None) -> dict:
    settings_file = _get_settings_file(settings)
    if not settings_file.exists():
        return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))
    try:
        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        logger.warning("Settings file is invalid JSON. Using defaults.")
        return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))

    if not isinstance(loaded, dict):
        return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))

    merged = json.loads(json.dumps(DEFAULT_SETTINGS_FILE))
    for section in ("general", "processing", "cleanup"):
        value = loaded.get(section)
        if isinstance(value, dict):
            merged[section].update(value)
    return merged


def _save_ui_settings(data: dict, settings: Settings | None = None) -> None:
    settings_file = _get_settings_file(settings)
    settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def apply_persisted_settings(settings: Settings | None = None) -> Settings:
    active_settings = _get_active_settings(settings)
    saved_settings = _load_ui_settings(active_settings)
    processing_settings = saved_settings.get("processing", {})
    cleanup_settings = saved_settings.get("cleanup", {})

    for field_name in (
        "frame_enhancer_engine",
        "ai_device",
        "ai_allow_cpu",
        "ai_half_precision",
        "realesrgan_tile_size",
        "realesrgan_tile_pad",
        "realesrgan_pre_pad",
    ):
        value = processing_settings.get(field_name)
        if value is not None:
            setattr(active_settings, field_name, value)

    for field_name in (
        "cleanup_temp_on_success",
        "cleanup_keep_preview_frames",
        "cleanup_temp_older_than_hours",
    ):
        value = cleanup_settings.get(field_name)
        if value is not None:
            setattr(active_settings, field_name, value)

    return active_settings


def build_settings_response(settings: Settings | None = None) -> SettingsResponse:
    active_settings = apply_persisted_settings(_get_active_settings(settings))
    ui_settings = _load_ui_settings(active_settings)
    general_data = ui_settings.get("general", DEFAULT_SETTINGS_FILE["general"])
    return SettingsResponse(
        general=GeneralSettingsResponse(
            language=str(general_data.get("language", "en")),
            theme=str(general_data.get("theme", "dark")),
        ),
        processing=ProcessingSettingsResponse(
            frame_enhancer_engine=active_settings.frame_enhancer_engine,
            ai_device=active_settings.ai_device,
            ai_allow_cpu=active_settings.ai_allow_cpu,
            ai_half_precision=active_settings.ai_half_precision,
            realesrgan_tile_size=active_settings.realesrgan_tile_size,
            realesrgan_tile_pad=active_settings.realesrgan_tile_pad,
            realesrgan_pre_pad=active_settings.realesrgan_pre_pad,
        ),
        storage=StorageSettingsResponse(
            storage_path=active_settings.storage_path,
            temp_path=str(get_temp_path(active_settings)),
            exports_path=str(get_exports_path(active_settings)),
            models_path=str(get_models_path(active_settings)),
        ),
        cleanup=CleanupSettingsResponse(
            cleanup_temp_on_success=active_settings.cleanup_temp_on_success,
            cleanup_keep_preview_frames=active_settings.cleanup_keep_preview_frames,
            cleanup_temp_older_than_hours=active_settings.cleanup_temp_older_than_hours,
        ),
    )


def _ensure_no_running_jobs(db: Session) -> None:
    running_job = db.query(ProcessingJob).filter(ProcessingJob.status == "running").first()
    if running_job is not None:
        raise JobInvalidStateError()


def update_settings(
    db: Session,
    payload: SettingsUpdateRequest,
    settings: Settings | None = None,
) -> SettingsUpdateResponse:
    active_settings = _get_active_settings(settings)
    update_data = payload.model_dump(exclude_unset=True)
    ui_settings = _load_ui_settings(active_settings)

    if "general" in update_data and update_data["general"] is not None:
        general_update = update_data["general"]
        ui_settings.setdefault("general", {}).update(general_update)

    if "processing" in update_data and update_data["processing"] is not None:
        _ensure_no_running_jobs(db)
        processing_update = update_data["processing"]
        if (
            "frame_enhancer_engine" in processing_update
            and processing_update["frame_enhancer_engine"] is not None
        ):
            value = processing_update["frame_enhancer_engine"].strip().lower()
            if value not in ALLOWED_FRAME_ENHANCERS:
                raise InvalidProjectConfigurationError("frame_enhancer_engine is invalid.")
            active_settings.frame_enhancer_engine = value
            ui_settings.setdefault("processing", {})["frame_enhancer_engine"] = value
        if "ai_device" in processing_update and processing_update["ai_device"] is not None:
            value = processing_update["ai_device"].strip().lower()
            if value not in ALLOWED_AI_DEVICES:
                raise InvalidProjectConfigurationError("ai_device is invalid.")
            active_settings.ai_device = value
            ui_settings.setdefault("processing", {})["ai_device"] = value
        for field_name in (
            "ai_allow_cpu",
            "ai_half_precision",
            "realesrgan_tile_size",
            "realesrgan_tile_pad",
            "realesrgan_pre_pad",
        ):
            value = processing_update.get(field_name)
            if value is not None:
                if field_name.startswith("realesrgan_") and int(value) < 0:
                    raise InvalidProjectConfigurationError(f"{field_name} must be >= 0.")
                setattr(active_settings, field_name, value)
                ui_settings.setdefault("processing", {})[field_name] = value

    if "cleanup" in update_data and update_data["cleanup"] is not None:
        cleanup_update = update_data["cleanup"]
        if cleanup_update.get("cleanup_temp_on_success") is not None:
            active_settings.cleanup_temp_on_success = cleanup_update["cleanup_temp_on_success"]
            ui_settings.setdefault("cleanup", {})["cleanup_temp_on_success"] = cleanup_update[
                "cleanup_temp_on_success"
            ]
        if cleanup_update.get("cleanup_keep_preview_frames") is not None:
            if cleanup_update["cleanup_keep_preview_frames"] < 0:
                raise InvalidProjectConfigurationError(
                    "cleanup_keep_preview_frames must be >= 0."
                )
            active_settings.cleanup_keep_preview_frames = cleanup_update[
                "cleanup_keep_preview_frames"
            ]
            ui_settings.setdefault("cleanup", {})["cleanup_keep_preview_frames"] = (
                cleanup_update["cleanup_keep_preview_frames"]
            )
        if cleanup_update.get("cleanup_temp_older_than_hours") is not None:
            if cleanup_update["cleanup_temp_older_than_hours"] <= 0:
                raise InvalidProjectConfigurationError(
                    "cleanup_temp_older_than_hours must be greater than zero."
                )
            active_settings.cleanup_temp_older_than_hours = cleanup_update[
                "cleanup_temp_older_than_hours"
            ]
            ui_settings.setdefault("cleanup", {})["cleanup_temp_older_than_hours"] = (
                cleanup_update["cleanup_temp_older_than_hours"]
            )

    _save_ui_settings(ui_settings, active_settings)
    return SettingsUpdateResponse(updated=True, settings=build_settings_response(active_settings))
