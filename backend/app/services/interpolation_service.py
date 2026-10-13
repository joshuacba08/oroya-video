"""Frame interpolation (RIFE 4.25) settings and setup for a job (REQ-037)."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import FrameInterpolationNotAvailableError
from app.core.paths import get_model_path
from app.db.models import ProcessingJob
from app.db.repositories import ai_model_repository
from app.enhancers.rife_interpolator import (
    InterpolationSchedule,
    RIFEInterpolator,
    is_scene_change,
    resolve_output_fps,
    source_fps_fraction,
)
from app.enhancers.stream import InterpolationStage
from app.services.ai_runtime_service import resolve_ai_device
from app.utils.enhancement_config import parse_enhancement_config_json

RIFE_MODEL_SLUG = "rife-4.25"


def get_interpolation_config(enhancement_config: dict[str, Any]) -> dict[str, Any] | None:
    """`{"enabled": True, "target_fps": ...}` when interpolation is on, else None."""
    config = enhancement_config.get("interpolation")
    if isinstance(config, dict) and config.get("enabled") is True:
        return config
    return None


def get_job_interpolation(job: ProcessingJob) -> dict[str, Any] | None:
    return get_interpolation_config(parse_enhancement_config_json(job.enhancement_config_json))


def resolve_job_output_fps(job: ProcessingJob, source_fps: float) -> Fraction | None:
    config = get_job_interpolation(job)
    if config is None:
        return None
    return resolve_output_fps(source_fps, config.get("target_fps", "2x"))


def is_rife_model_ready(db: Session) -> bool:
    model = ai_model_repository.get_ai_model_by_slug(db, RIFE_MODEL_SLUG)
    return bool(model and model.is_enabled and model.is_installed)


def build_interpolation_stage(
    db: Session,
    job: ProcessingJob,
    settings: Settings,
    source_fps: float,
) -> tuple[InterpolationStage | None, Fraction | None]:
    """Interpolation stage and output frame rate for the job, or (None, None) when off."""
    output_fps = resolve_job_output_fps(job, source_fps)
    if output_fps is None:
        return None, None
    model = ai_model_repository.get_ai_model_by_slug(db, RIFE_MODEL_SLUG)
    if model is None or not model.is_enabled or not model.relative_path:
        raise FrameInterpolationNotAvailableError()
    model_path = get_model_path(model.relative_path, settings)
    if not model_path.is_file():
        raise FrameInterpolationNotAvailableError()
    device = resolve_ai_device(settings.ai_device, allow_cpu=settings.ai_allow_cpu)
    try:
        schedule = InterpolationSchedule(source_fps_fraction(source_fps), output_fps)
    except ValueError as exc:
        raise FrameInterpolationNotAvailableError() from exc
    interpolator = RIFEInterpolator(
        model_path=model_path,
        device=device,
        half_precision=settings.ai_half_precision,
    )
    return InterpolationStage(interpolator, schedule, is_scene_change), output_fps
