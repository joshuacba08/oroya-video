from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    FFmpegNotAvailableError,
    FFprobeNotAvailableError,
    JobNotFoundError,
    JobPreflightFailedError,
)
from app.core.logging import get_logger
from app.core.paths import (
    get_exports_path,
    get_storage_path,
    is_directory_writable,
    is_storage_writable,
)
from app.db.repositories import (
    ai_model_repository,
    job_repository,
    project_repository,
    video_repository,
)
from app.schemas.hardening_schema import JobPreflightResponse
from app.services import ai_runtime_service
from app.services.ai_runtime_service import get_ai_runtime_status
from app.services.audit_log_service import record_audit_event
from app.services.face_restore_service import FACE_RESTORE_MODEL_SLUG, get_face_restore_strength
from app.services.frame_extraction_service import resolve_job_input_video, validate_ffmpeg_available
from app.services.realesrgan_service import validate_realesrgan_model
from app.services.video_probe_service import _get_ffprobe_path
from app.utils.enhancement_config import parse_enhancement_config_json

logger = get_logger(__name__)
FINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_job_or_raise(db: Session, job_id: str):
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    return job


def _has_active_process(job) -> bool:
    return job.process_id is not None and job.process_ended_at is None


def run_job_preflight(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> JobPreflightResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    ai_runtime = get_ai_runtime_status(active_settings)
    checks: dict[str, bool] = {}
    warnings: list[str] = []
    errors: list[str] = []
    original_stage = job.current_stage

    project = project_repository.get_project_by_id(db, job.project_id)
    video_asset = video_repository.get_video_asset_by_id(db, job.video_asset_id)
    model = ai_model_repository.get_ai_model_by_slug(db, job.ai_model_slug)
    try:
        validate_ffmpeg_available()
        ffmpeg_available = True
    except FFmpegNotAvailableError:
        ffmpeg_available = False
    try:
        _get_ffprobe_path()
        ffprobe_available = True
    except FFprobeNotAvailableError:
        ffprobe_available = False

    checks["project_exists"] = project is not None
    checks["video_asset_exists"] = video_asset is not None
    checks["ffmpeg_available"] = ffmpeg_available
    checks["ffprobe_available"] = ffprobe_available
    checks["model_exists"] = model is not None
    checks["model_enabled"] = bool(model and model.is_enabled)
    checks["storage_temp_writable"] = is_storage_writable(active_settings)
    # La carpeta elegida para este job (si la hay) o la de exportación de Ajustes.
    custom_output_dir = parse_enhancement_config_json(job.export_config_json).get("output_dir")
    exports_path = (
        Path(custom_output_dir).expanduser()
        if isinstance(custom_output_dir, str) and custom_output_dir.strip()
        else get_exports_path(active_settings)
    )
    checks["storage_exports_writable"] = is_directory_writable(exports_path)
    checks["job_process_inactive"] = not _has_active_process(job)
    checks["job_state_allowed"] = job.status not in FINAL_JOB_STATUSES
    checks["cuda_available"] = active_settings.ai_device.strip().lower() != "cuda" or (
        ai_runtime.cuda_available
    )

    if project is None:
        errors.append("Project associated with this job is missing.")
    if video_asset is None:
        errors.append("Video asset associated with this job is missing.")

    video_file_exists = False
    if video_asset is not None:
        try:
            video_file_exists = resolve_job_input_video(job).exists()
        except Exception:
            video_file_exists = False
    checks["video_file_exists"] = video_file_exists
    if not video_file_exists:
        errors.append("Video file associated with this job is missing.")

    if not checks["ffmpeg_available"]:
        errors.append("FFmpeg is not available.")
    if not checks["ffprobe_available"]:
        errors.append("FFprobe is not available.")
    if model is None:
        errors.append("Selected model was not found in the registry.")
    elif not model.is_enabled:
        errors.append("Selected model is disabled.")
    if not checks["storage_temp_writable"]:
        errors.append("Temporary storage is not writable.")
    if not checks["storage_exports_writable"]:
        errors.append("Export storage is not writable.")
    if not checks["cuda_available"]:
        errors.append("CUDA was requested but is not available.")

    storage_path = get_storage_path(active_settings)
    total_bytes, _, free_bytes = shutil.disk_usage(storage_path)
    del total_bytes
    min_free_bytes = int(active_settings.preflight_min_free_disk_gb * (1024**3))
    checks["free_disk_space_ok"] = free_bytes >= min_free_bytes
    if not checks["free_disk_space_ok"]:
        errors.append("Free disk space is below the configured preflight threshold.")

    checks["ai_runtime_available"] = True
    checks["model_installed"] = True
    if active_settings.frame_enhancer_engine.strip().lower() == "realesrgan":
        model_validation = validate_realesrgan_model(db, job.ai_model_slug, active_settings)
        checks["model_installed"] = model_validation.is_installed
        checks["ai_runtime_available"] = model_validation.runtime_available
        if not model_validation.is_installed:
            warnings.append("Selected model is not installed.")
            errors.append("Selected model is not installed.")
        if not model_validation.runtime_available:
            warnings.extend(model_validation.warnings)
            errors.append("AI runtime is not available for Real-ESRGAN.")
        elif model_validation.device == "cpu":
            warnings.append("CPU fallback selected for Real-ESRGAN.")
    else:
        checks["model_installed"] = bool(model)

    if get_face_restore_strength(job) is not None:
        face_model = ai_model_repository.get_ai_model_by_slug(db, FACE_RESTORE_MODEL_SLUG)
        face_model_ready = bool(face_model and face_model.is_enabled and face_model.is_installed)
        missing_modules = ai_runtime_service.get_missing_face_restore_modules()
        checks["face_restore_ready"] = face_model_ready and not missing_modules
        if not face_model_ready:
            errors.append("Face restoration needs the GFPGAN model: download it in Models.")
        if missing_modules:
            errors.append(
                "Face restoration packages are missing: "
                + ", ".join(missing_modules)
                + ". Install the AI runtime from Setup."
            )

    if _has_active_process(job):
        errors.append("This job already has an active registered process.")
    if job.status in FINAL_JOB_STATUSES:
        errors.append("The job is already in a final state.")

    ready = all(checks.values()) and not errors
    started_at = _utcnow()
    completed_at = _utcnow()
    job_repository.update_job(
        db,
        job,
        {
            "preflight_started_at": started_at,
            "preflight_completed_at": completed_at,
            "preflight_error_code": None if ready else "job_preflight_failed",
            "preflight_error_message": None if ready else "; ".join(errors)[:500],
            "current_stage": original_stage if ready else "preflight",
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info" if ready else "warning",
        f"Job preflight completed. ready={ready}",
        stage="preflight",
    )
    db.commit()
    return JobPreflightResponse(
        job_id=job.id,
        ready=ready,
        checks=checks,
        warnings=warnings,
        errors=errors,
    )


def ensure_job_preflight_ready(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> JobPreflightResponse:
    response = run_job_preflight(db, job_id, settings)
    if not response.ready:
        record_audit_event(
            "job_failed",
            "job",
            job_id,
            "Job preflight failed.",
            {"checks": response.checks, "errors": response.errors},
            settings,
        )
        raise JobPreflightFailedError(
            details={
                "job_id": job_id,
                "checks": response.checks,
                "warnings": response.warnings,
                "errors": response.errors,
            }
        )
    return response
