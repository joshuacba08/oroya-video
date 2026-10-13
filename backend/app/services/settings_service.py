from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import InvalidProjectConfigurationError, SettingsLockedByRunningJobError
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
    "storage": {},
    # Últimos ajustes de proceso usados (lote): base de los proyectos nuevos.
    "defaults": {},
}
ALLOWED_FRAME_ENHANCERS = {"mock", "realesrgan"}
ALLOWED_AI_DEVICES = {"auto", "cpu", "cuda"}

# Lectura-modificación-escritura de settings.json desde peticiones y desde el hilo de
# instalación de IA: sin el lock, una escritura podía pisar la otra.
_settings_lock = threading.RLock()
# Copia del settings.json ilegible que se apartó al arrancar (se avisa en /bootstrap).
corrupt_settings_backup: Path | None = None


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _get_settings_file(settings: Settings | None = None) -> Path:
    settings_file = get_settings_file_path(settings)
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    return settings_file


def _set_aside_corrupt_file(settings_file: Path) -> None:
    """Keep the unreadable file for support instead of overwriting it on the next save."""
    global corrupt_settings_backup
    backup = settings_file.with_name(
        f"{settings_file.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    try:
        os.replace(settings_file, backup)
        corrupt_settings_backup = backup
        logger.warning("Settings file was unreadable; moved to %s. Using defaults.", backup)
    except OSError:
        logger.warning("Settings file is unreadable and could not be moved. Using defaults.")


def _load_ui_settings(settings: Settings | None = None) -> dict:
    settings_file = _get_settings_file(settings)
    with _settings_lock:
        if not settings_file.exists():
            return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))
        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            _set_aside_corrupt_file(settings_file)
            return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))
        except OSError:
            logger.warning("Settings file could not be read. Using defaults.")
            return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))

        if not isinstance(loaded, dict):
            _set_aside_corrupt_file(settings_file)
            return json.loads(json.dumps(DEFAULT_SETTINGS_FILE))

    merged = json.loads(json.dumps(DEFAULT_SETTINGS_FILE))
    for section in ("general", "processing", "cleanup", "storage", "defaults"):
        value = loaded.get(section)
        if isinstance(value, dict):
            merged[section].update(value)
    return merged


def _save_ui_settings(data: dict, settings: Settings | None = None) -> None:
    settings_file = _get_settings_file(settings)
    temp_file = settings_file.with_name(f"{settings_file.name}.tmp")
    with _settings_lock:
        # Atómico: un corte de luz o un cierre a mitad nunca deja un JSON a medias.
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp_file, settings_file)


def _validated(field_name: str, value: Any) -> Any:
    """Value coerced to the Settings field type, or None when it is not valid."""
    annotation = Settings.model_fields[field_name].annotation
    try:
        return TypeAdapter(annotation).validate_python(value)
    except ValidationError:
        logger.warning("Ignoring invalid saved setting %s=%r", field_name, value)
        return None


def set_frame_enhancer_engine(engine: str, settings: Settings | None = None) -> None:
    """Change and persist the enhancer engine (used after installing the AI runtime)."""
    active_settings = _get_active_settings(settings)
    with _settings_lock:
        ui_settings = _load_ui_settings(active_settings)
        ui_settings.setdefault("processing", {})["frame_enhancer_engine"] = engine
        _save_ui_settings(ui_settings, active_settings)
    active_settings.frame_enhancer_engine = engine
    logger.info("Frame enhancer engine set to %s", engine)


# Propios de cada proyecto: no tiene sentido heredarlos.
PROJECT_SPECIFIC_EXPORT_KEYS = ("file_name", "trim")


def get_processing_defaults(settings: Settings | None = None) -> dict[str, dict]:
    defaults = _load_ui_settings(_get_active_settings(settings)).get("defaults", {})
    return {
        "enhancement_config": dict(defaults.get("enhancement_config") or {}),
        "export_config": dict(defaults.get("export_config") or {}),
    }


def save_processing_defaults(
    enhancement_config: dict | None,
    export_config: dict | None,
    settings: Settings | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    export = {
        key: value
        for key, value in (export_config or {}).items()
        if key not in PROJECT_SPECIFIC_EXPORT_KEYS
    }
    with _settings_lock:
        ui_settings = _load_ui_settings(active_settings)
        ui_settings["defaults"] = {
            "enhancement_config": dict(enhancement_config or {}),
            "export_config": export,
        }
        _save_ui_settings(ui_settings, active_settings)


def apply_persisted_settings(settings: Settings | None = None) -> Settings:
    active_settings = _get_active_settings(settings)
    saved_settings = _load_ui_settings(active_settings)
    processing_settings = saved_settings.get("processing", {})
    cleanup_settings = saved_settings.get("cleanup", {})
    exports_dir = saved_settings.get("storage", {}).get("exports_dir")
    if isinstance(exports_dir, str) and exports_dir.strip():
        active_settings.exports_dir = exports_dir

    for field_name in (
        "frame_enhancer_engine",
        "pipeline_mode",
        "ai_device",
        "ai_allow_cpu",
        "ai_half_precision",
        "realesrgan_tile_size",
        "realesrgan_tile_pad",
        "realesrgan_pre_pad",
    ):
        value = processing_settings.get(field_name)
        if value is not None and (value := _validated(field_name, value)) is not None:
            setattr(active_settings, field_name, value)

    for field_name in (
        "cleanup_temp_on_success",
        "cleanup_keep_preview_frames",
        "cleanup_temp_older_than_hours",
    ):
        value = cleanup_settings.get(field_name)
        if value is not None and (value := _validated(field_name, value)) is not None:
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
        raise SettingsLockedByRunningJobError()


def update_settings(
    db: Session,
    payload: SettingsUpdateRequest,
    settings: Settings | None = None,
) -> SettingsUpdateResponse:
    with _settings_lock:
        return _update_settings_locked(db, payload, settings)


def _update_settings_locked(
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
                raise InvalidProjectConfigurationError("cleanup_keep_preview_frames must be >= 0.")
            active_settings.cleanup_keep_preview_frames = cleanup_update[
                "cleanup_keep_preview_frames"
            ]
            ui_settings.setdefault("cleanup", {})["cleanup_keep_preview_frames"] = cleanup_update[
                "cleanup_keep_preview_frames"
            ]
        if cleanup_update.get("cleanup_temp_older_than_hours") is not None:
            if cleanup_update["cleanup_temp_older_than_hours"] <= 0:
                raise InvalidProjectConfigurationError(
                    "cleanup_temp_older_than_hours must be greater than zero."
                )
            active_settings.cleanup_temp_older_than_hours = cleanup_update[
                "cleanup_temp_older_than_hours"
            ]
            ui_settings.setdefault("cleanup", {})["cleanup_temp_older_than_hours"] = cleanup_update[
                "cleanup_temp_older_than_hours"
            ]

    if "storage" in update_data and update_data["storage"] is not None:
        exports_dir = update_data["storage"].get("exports_dir")
        if exports_dir is not None:
            _ensure_no_running_jobs(db)
            folder = _validated_exports_dir(exports_dir)
            active_settings.exports_dir = str(folder)
            ui_settings.setdefault("storage", {})["exports_dir"] = str(folder)

    _save_ui_settings(ui_settings, active_settings)
    return SettingsUpdateResponse(updated=True, settings=build_settings_response(active_settings))


def _validated_exports_dir(raw_path: str) -> Path:
    """Absolute, existing (or creatable) and writable folder for the exported videos."""
    folder = Path(raw_path.strip()).expanduser()
    if not raw_path.strip() or not folder.is_absolute():
        raise InvalidProjectConfigurationError("The export folder must be an absolute path.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".oroya-write-test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise InvalidProjectConfigurationError(
            "The export folder cannot be created or written to."
        ) from exc
    return folder.resolve()
