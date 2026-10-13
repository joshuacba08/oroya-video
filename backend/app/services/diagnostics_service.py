"""Diagnostic bundle for bug reports: logs, system state and recent jobs in one zip.

Built locally and opened in the file explorer; nothing is sent anywhere. The user's home
folder is replaced by `~` in every text file so the zip can be shared without exposing the
Windows user name.
"""

from __future__ import annotations

import json
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import get_logs_path, get_settings_file_path, get_storage_path
from app.db.models import JobLog, ProcessingJob

logger = get_logger(__name__)

RECENT_JOBS = 20
JOB_LOG_LINES = 200
BUNDLES_TO_KEEP = 5
JOB_FIELDS = (
    "id",
    "project_id",
    "status",
    "current_stage",
    "progress_percent",
    "error_code",
    "error_message",
    "ai_model_slug",
    "enhancer_engine",
    "realesrgan_device",
    "realesrgan_tile_size",
    "realesrgan_failed_frames",
    "realesrgan_average_frame_time_ms",
    "frames_total",
    "frames_processed",
    "enhancement_config_json",
    "export_config_json",
    "retry_count",
    "created_at",
    "started_at",
    "updated_at",
)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def get_diagnostics_path(settings: Settings | None = None) -> Path:
    return get_storage_path(_get_active_settings(settings)) / "diagnostics"


def _anonymize(value: str) -> str:
    home = str(Path.home())
    for variant in {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}:
        value = value.replace(variant, "~")
    return value


def _safe(callable_, default: Any = None) -> Any:
    try:
        return callable_()
    except Exception as exc:  # noqa: BLE001 - el diagnóstico nunca debe fallar por una sección
        return {"error": f"{type(exc).__name__}: {exc}"} if default is None else default


def _system_snapshot(db: Session, settings: Settings) -> dict[str, Any]:
    from app.db.migrations import get_schema_version
    from app.services.ai_runtime_service import get_ai_runtime_status
    from app.services.cleanup_service import get_storage_usage
    from app.services.gpu_detection_service import get_gpu_status
    from app.services.system_service import get_requirements_status
    from app.services.tool_detection_service import get_tools_status

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "app": {
            "version": settings.app_version,
            "environment": settings.environment,
            "frame_enhancer_engine": settings.frame_enhancer_engine,
            "ai_device": settings.ai_device,
            "half_precision": settings.ai_half_precision,
            "tile_size": settings.realesrgan_tile_size,
        },
        "platform": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "database": {
            "schema_version": _safe(lambda: get_schema_version(db.get_bind())),
            "integrity": _safe(lambda: db.execute(text("PRAGMA quick_check")).scalar()),
        },
        "requirements": _safe(lambda: get_requirements_status(settings).model_dump()),
        "tools": _safe(lambda: get_tools_status().model_dump()),
        "gpu": _safe(lambda: get_gpu_status().model_dump()),
        "ai_runtime": _safe(lambda: get_ai_runtime_status(settings).model_dump()),
        "storage": _safe(lambda: get_storage_usage(settings)),
    }


def _recent_jobs(db: Session) -> list[dict[str, Any]]:
    jobs = db.query(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(RECENT_JOBS)
    result = []
    for job in jobs:
        entry = {field: getattr(job, field, None) for field in JOB_FIELDS}
        # Las últimas líneas: el error suele estar al final.
        logs = list(
            reversed(
                db.query(JobLog)
                .filter(JobLog.job_id == job.id)
                .order_by(JobLog.created_at.desc())
                .limit(JOB_LOG_LINES)
                .all()
            )
        )
        entry["logs"] = [
            {
                "created_at": log.created_at,
                "level": log.level,
                "stage": log.stage,
                "message": log.message,
            }
            for log in logs
        ]
        result.append(entry)
    return result


def _prune_old_bundles(folder: Path) -> None:
    bundles = sorted(folder.glob("oroya-diagnostico-*.zip"))
    for old in bundles[:-BUNDLES_TO_KEEP]:
        old.unlink(missing_ok=True)


def create_diagnostics_bundle(db: Session, settings: Settings | None = None) -> Path:
    active_settings = _get_active_settings(settings)
    folder = get_diagnostics_path(active_settings)
    folder.mkdir(parents=True, exist_ok=True)
    bundle = folder / f"oroya-diagnostico-{time.strftime('%Y%m%d-%H%M%S')}.zip"

    def dump(data: Any) -> str:
        return _anonymize(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.json", dump(_system_snapshot(db, active_settings)))
        archive.writestr("jobs.json", dump(_safe(lambda: _recent_jobs(db), default=[])))
        settings_file = get_settings_file_path(active_settings)
        if settings_file.is_file():
            archive.writestr("settings.json", _anonymize(settings_file.read_text(encoding="utf-8")))
        for log_file in sorted(get_logs_path(active_settings).glob("*.log*")):
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            archive.writestr(f"logs/{log_file.name}", _anonymize(content))

    _prune_old_bundles(folder)
    logger.info("Diagnostic bundle created: %s", bundle.name)
    return bundle
