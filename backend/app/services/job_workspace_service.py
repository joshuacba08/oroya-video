from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import (
    delete_job_frames_directories,
    ensure_job_directories,
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
