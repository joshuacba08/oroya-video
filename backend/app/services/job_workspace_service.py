from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import (
    delete_job_frames_directories,
    ensure_job_directories,
    get_export_roots,
    get_job_encoded_path,
    get_job_enhanced_frames_path,
    get_job_original_frames_path,
    get_job_working_path,
)

logger = get_logger(__name__)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def prepare_job_workspace(
    job_id: str,
    settings: Settings | None = None,
) -> dict[str, Path]:
    active_settings = _get_active_settings(settings)
    directories = ensure_job_directories(job_id, active_settings)
    metadata_path = directories["working_dir"] / "metadata.json"
    if not metadata_path.exists():
        metadata_path.write_text(json.dumps({"job_id": job_id}), encoding="utf-8")
    logger.info("Job workspace prepared: %s", job_id)
    return directories


def get_job_workspace_summary(
    job_id: str,
    settings: Settings | None = None,
) -> dict[str, str]:
    active_settings = _get_active_settings(settings)
    return {
        "working_dir": str(get_job_working_path(job_id, active_settings)),
        "original_frames_dir": str(get_job_original_frames_path(job_id, active_settings)),
        "enhanced_frames_dir": str(get_job_enhanced_frames_path(job_id, active_settings)),
        "encoded_dir": str(get_job_encoded_path(job_id, active_settings)),
    }


def clean_job_workspace(job_id: str, settings: Settings | None = None) -> None:
    active_settings = _get_active_settings(settings)
    delete_job_frames_directories(job_id, active_settings)


def delete_job_files(
    job_id: str,
    project_id: str,
    settings: Settings | None = None,
) -> None:
    """Remove a deleted job's temp workspace and export folder. Call only after the DB commit."""
    active_settings = _get_active_settings(settings)
    working = get_job_working_path(job_id, active_settings)
    if working.exists():
        shutil.rmtree(working, ignore_errors=True)

    # Las exportaciones pueden estar en la carpeta actual o en la anterior al cambiarla.
    for root in get_export_roots(active_settings):
        project_exports = root / project_id
        job_exports = project_exports / job_id
        if job_exports.exists():
            shutil.rmtree(job_exports, ignore_errors=True)
        if project_exports.is_dir() and not any(project_exports.iterdir()):
            project_exports.rmdir()
    logger.info("Job files deleted: %s", job_id)
