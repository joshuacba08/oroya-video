from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.error_codes import resolve_error_code_info
from app.core.errors import (
    AIModelDisabledError,
    AIModelNotFoundError,
    JobCancelFailedError,
    JobCreateFailedError,
    JobDeleteFailedError,
    JobFramesNotFoundError,
    JobInvalidStateError,
    JobNotFoundError,
    JobPauseNotSupportedError,
    JobRetryNotAllowedError,
    JobStartFailedError,
    ProcessTerminationFailedError,
)
from app.core.logging import get_logger
from app.core.paths import delete_job_frames_directories
from app.db.models import AIModel, ProcessingJob, Project, VideoAsset
from app.db.repositories import (
    ai_model_repository,
    job_repository,
    project_repository,
    video_repository,
)
from app.schemas.ai_model_schema import AIModelResponse
from app.schemas.hardening_schema import (
    CleanupResponse,
    JobDiagnosticsResponse,
    JobPipelineResponse,
    JobPipelineStage,
    JobPreflightResponse,
    JobRetryRequest,
)
from app.schemas.job_schema import (
    AudioMuxSummaryResponse,
    DeleteEncodedVideoResponse,
    DeleteEnhancedFramesResponse,
    DeleteFramesResponse,
    DeleteMuxedVideoResponse,
    EncodedVideoResponse,
    FinalExportSummaryResponse,
    FrameEnhancementSummaryResponse,
    FrameExtractionSummaryResponse,
    JobControlResponse,
    JobCreateRequest,
    JobDetailResponse,
    JobEnhancedFramesResponse,
    JobFrameItem,
    JobFramesResponse,
    JobListResponse,
    JobLogsResponse,
    JobProgressResponse,
    MuxedVideoResponse,
    VideoEncodingSummaryResponse,
)
from app.schemas.realesrgan_schema import (
    RealESRGANJobSummaryResponse,
    RealESRGANJobValidationResponse,
)
from app.services import (
    audio_mux_service,
    export_service,
    frame_enhancement_service,
    job_workspace_service,
    video_encoding_service,
)
from app.services.audit_log_service import record_audit_event
from app.services.cleanup_service import cleanup_job_temp_files
from app.services.job_contract_service import (
    build_job_actions,
    build_stage_label,
    build_stage_progress_percent,
    estimate_remaining_seconds,
    is_export_available,
    is_preview_available,
)
from app.services.job_preflight_service import ensure_job_preflight_ready, run_job_preflight
from app.services.job_recovery_service import (
    list_interrupted_jobs as list_interrupted_jobs_response,
)
from app.services.process_registry_service import terminate_process_for_job
from app.services.project_service import (
    _build_project_configs,
    _ensure_video_asset_file_available,
    _get_project_or_raise,
    _get_video_asset_or_raise,
)
from app.services.realesrgan_service import (
    get_realesrgan_job_summary as get_realesrgan_job_summary_response,
)
from app.services.realesrgan_service import (
    validate_realesrgan_job_requirements,
)
from app.workers.queue import job_queue

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _serialize_config(data: dict[str, Any]) -> str:
    return json.dumps(data)


def _get_job_or_raise(db: Session, job_id: str) -> ProcessingJob:
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        logger.warning("Job not found: %s", job_id)
        raise JobNotFoundError()
    return job


def _resolve_model_for_job(db: Session, model_id_or_slug: str) -> AIModel:
    model = ai_model_repository.get_ai_model_by_id(db, model_id_or_slug)
    if not model:
        model = ai_model_repository.get_ai_model_by_slug(db, model_id_or_slug)
    if not model:
        raise AIModelNotFoundError()
    if not model.is_enabled:
        raise AIModelDisabledError()
    return model


def _build_job_configs(
    db: Session,
    project: Project,
    model_id: str | None,
    enhancement_override: dict[str, Any] | None,
    export_override: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], AIModel]:
    enhancement_input = dict(enhancement_override or {})
    if model_id:
        model = _resolve_model_for_job(db, model_id)
        enhancement_input["model_id"] = model.slug
    enhancement_config, export_config, _ = _build_project_configs(
        db=db,
        enhancement_config=enhancement_input or None,
        export_config=export_override,
        workspace_state=None,
        existing_project=project,
    )
    model = _resolve_model_for_job(db, enhancement_config["model_id"])
    return enhancement_config, export_config, model


def _to_job_detail_response(
    db: Session,
    job: ProcessingJob,
    project: Project | None = None,
    video: VideoAsset | None = None,
    model: AIModel | None = None,
) -> JobDetailResponse:
    project = project or _get_project_or_raise(db, job.project_id)
    video = video or _get_video_asset_or_raise(db, job.video_asset_id)
    if model is None and job.ai_model_id:
        model = ai_model_repository.get_ai_model_by_id(db, job.ai_model_id)
    model_response: AIModelResponse | None = None
    if model is not None:
        model_response = ai_model_repository.to_ai_model_response(model)
    return JobDetailResponse(
        job=job_repository.to_job_response(job),
        project=project_repository.to_project_response(project),
        video=video_repository.to_video_asset_response(video),
        model=model_response,
    )


def create_processing_job(
    db: Session,
    request: JobCreateRequest,
    settings: Settings | None = None,
) -> JobDetailResponse:
    logger.info("Job create requested")
    active_settings = _get_active_settings(settings)
    project = _get_project_or_raise(db, request.project_id)
    video = _get_video_asset_or_raise(db, project.video_asset_id)
    _ensure_video_asset_file_available(video)

    enhancement_config, export_config, model = _build_job_configs(
        db=db,
        project=project,
        model_id=request.model_id,
        enhancement_override=request.enhancement_config,
        export_override=request.export_config,
    )

    job_data = {
        "id": str(uuid.uuid4()),
        "project_id": project.id,
        "video_asset_id": video.id,
        "ai_model_id": model.id,
        "ai_model_slug": model.slug,
        "status": "pending",
        "current_stage": "idle",
        "progress_percent": 0.0,
        "frames_total": None,
        "frames_processed": 0,
        "estimated_time_seconds": None,
        "elapsed_time_seconds": None,
        "enhancement_config_json": _serialize_config(enhancement_config),
        "export_config_json": _serialize_config(export_config),
        "output_path": None,
        "error_code": None,
        "error_message": None,
        "frame_format": "png",
        "extracted_frames": 0,
        "enhancer_engine": None,
        "enhanced_frames": 0,
        "enhancement_started_at": None,
        "enhancement_completed_at": None,
        "enhancement_error_code": None,
        "enhancement_error_message": None,
        "encoded_dir": None,
        "encoded_video_path": None,
        "encoded_video_file_name": None,
        "encoded_video_size_bytes": None,
        "encoding_fps": None,
        "encoding_codec": None,
        "encoding_format": None,
        "encoding_started_at": None,
        "encoding_completed_at": None,
        "encoding_error_code": None,
        "encoding_error_message": None,
        "muxed_video_path": None,
        "muxed_video_file_name": None,
        "muxed_video_size_bytes": None,
        "audio_strategy": None,
        "audio_codec": None,
        "audio_mux_started_at": None,
        "audio_mux_completed_at": None,
        "audio_mux_error_code": None,
        "audio_mux_error_message": None,
        "export_id": None,
        "final_export_path": None,
        "final_export_file_name": None,
        "final_export_size_bytes": None,
        "export_started_at": None,
        "export_completed_at": None,
        "export_error_code": None,
        "export_error_message": None,
        "retry_count": 0,
        "max_retries": active_settings.max_job_retries,
        "last_retry_at": None,
        "interrupted_at": None,
        "recovered_at": None,
        "cleanup_started_at": None,
        "cleanup_completed_at": None,
        "cleanup_error_code": None,
        "cleanup_error_message": None,
        "preflight_started_at": None,
        "preflight_completed_at": None,
        "preflight_error_code": None,
        "preflight_error_message": None,
        "last_known_stage": None,
        "last_known_progress_percent": None,
        "worker_id": None,
        "process_id": None,
        "process_kind": None,
        "process_started_at": None,
        "process_ended_at": None,
        "temp_size_bytes": None,
        "original_frames_size_bytes": None,
        "enhanced_frames_size_bytes": None,
        "encoded_size_bytes": None,
        "muxed_size_bytes": None,
        "exports_size_bytes": None,
        "realesrgan_model_slug": None,
        "realesrgan_model_path": None,
        "realesrgan_device": None,
        "realesrgan_scale": None,
        "realesrgan_tile_size": None,
        "realesrgan_tile_pad": None,
        "realesrgan_pre_pad": None,
        "realesrgan_half_precision": None,
        "realesrgan_frames_total": None,
        "realesrgan_frames_processed": 0,
        "realesrgan_failed_frames": 0,
        "realesrgan_average_frame_time_ms": None,
        "realesrgan_started_at": None,
        "realesrgan_completed_at": None,
        "realesrgan_error_code": None,
        "realesrgan_error_message": None,
        "pause_requested": False,
        "cancel_requested": False,
    }

    try:
        job = job_repository.create_job(db, job_data)
        job_repository.create_job_log(db, job.id, "info", "Job created.", stage="idle")
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Job creation failed")
        raise JobCreateFailedError() from exc

    logger.info("Job created: %s", job.id)
    return _to_job_detail_response(db, job, project=project, video=video, model=model)


def list_processing_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    project_id: str | None = None,
) -> JobListResponse:
    logger.info("Job list requested")
    items = job_repository.list_jobs(
        db=db,
        limit=limit,
        offset=offset,
        status=status,
        project_id=project_id,
    )
    total = job_repository.count_jobs(db=db, status=status, project_id=project_id)
    return JobListResponse(
        items=[job_repository.to_job_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_processing_job_detail(db: Session, job_id: str) -> JobDetailResponse:
    job = _get_job_or_raise(db, job_id)
    logger.info("Job detail requested: %s", job.id)
    return _to_job_detail_response(db, job)


async def start_processing_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> JobControlResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.status not in {"pending", "paused"}:
        logger.warning("Job invalid state transition on start: %s", job.status)
        raise JobInvalidStateError()

    # El preflight lanza subprocesos (ffmpeg, GPU) e importa torch: fuera del event loop.
    await asyncio.to_thread(ensure_job_preflight_ready, db, job.id, active_settings)

    try:
        job = job_repository.update_job(
            db,
            job,
            {
                "status": "queued",
                "current_stage": "queued",
                "pause_requested": False,
                "cancel_requested": False,
                "error_code": None,
                "error_message": None,
                "worker_id": "local-worker",
            },
        )
        job_repository.create_job_log(db, job.id, "info", "Job queued.", stage="queued")
        db.commit()
        db.refresh(job)
        await job_queue.enqueue(job.id)
        record_audit_event(
            "job_started",
            "job",
            job.id,
            "Job queued for processing.",
            settings=settings,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Job start failed")
        raise JobStartFailedError() from exc

    logger.info("Job queued: %s", job.id)
    return JobControlResponse(job=job_repository.to_job_response(job), message="Job queued.")


def pause_processing_job(db: Session, job_id: str) -> JobControlResponse:
    job = _get_job_or_raise(db, job_id)
    if job.status == "running" and job.current_stage == "enhancing_frames":
        try:
            job = job_repository.update_job(db, job, {"pause_requested": True})
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                "Job pause requested.",
                stage=job.current_stage,
            )
            db.commit()
            db.refresh(job)
        except SQLAlchemyError as exc:
            db.rollback()
            raise JobStartFailedError() from exc

        logger.info("Job pause requested: %s", job.id)
        return JobControlResponse(
            job=job_repository.to_job_response(job),
            message="Job pause requested.",
        )
    if job.status == "running" and job.current_stage in {
        "extracting_frames",
        "restoring_faces",
        "encoding_video",
        "muxing_audio",
        "exporting",
    }:
        raise JobPauseNotSupportedError()
    if job.status not in {"queued", "running"}:
        raise JobInvalidStateError()

    try:
        job = job_repository.update_job(
            db,
            job,
            {"status": "paused", "pause_requested": True},
        )
        job_repository.create_job_log(db, job.id, "info", "Job paused.", stage=job.current_stage)
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobStartFailedError() from exc

    logger.info("Job paused: %s", job.id)
    return JobControlResponse(job=job_repository.to_job_response(job), message="Job paused.")


async def resume_processing_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> JobControlResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.status != "paused":
        raise JobInvalidStateError()

    # El preflight lanza subprocesos (ffmpeg, GPU) e importa torch: fuera del event loop.
    await asyncio.to_thread(ensure_job_preflight_ready, db, job.id, active_settings)
    try:
        job = job_repository.update_job(
            db,
            job,
            {
                "status": "queued",
                "current_stage": "queued",
                "pause_requested": False,
                "cancel_requested": False,
                "worker_id": "local-worker",
            },
        )
        job_repository.create_job_log(db, job.id, "info", "Job resumed.", stage="queued")
        db.commit()
        db.refresh(job)
        await job_queue.enqueue(job.id)
        record_audit_event(
            "job_started",
            "job",
            job.id,
            "Job resumed and queued.",
            settings=settings,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobStartFailedError() from exc

    logger.info("Job resumed: %s", job.id)
    return JobControlResponse(job=job_repository.to_job_response(job), message="Job resumed.")


def cancel_processing_job(db: Session, job_id: str) -> JobControlResponse:
    job = _get_job_or_raise(db, job_id)
    if job.status not in {"pending", "queued", "running", "paused", "retrying"}:
        raise JobInvalidStateError()

    try:
        terminated = terminate_process_for_job(job.id)
        job = job_repository.update_job(
            db,
            job,
            {
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancel_requested": True,
                "cancelled_at": _utcnow(),
                "process_ended_at": _utcnow(),
            },
        )
        job_repository.create_job_log(db, job.id, "warning", "Job cancelled.", stage="cancelled")
        db.commit()
        db.refresh(job)
        record_audit_event(
            "job_cancelled",
            "job",
            job.id,
            "Job cancelled.",
            {"process_terminated": terminated},
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobCancelFailedError() from exc
    except Exception as exc:
        raise ProcessTerminationFailedError() from exc

    logger.info("Job cancelled: %s", job.id)
    return JobControlResponse(job=job_repository.to_job_response(job), message="Job cancelled.")


def delete_processing_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> dict[str, object]:
    job = _get_job_or_raise(db, job_id)
    if job.status == "running":
        raise JobInvalidStateError()

    project_id = job.project_id
    try:
        job_repository.delete_job(db, job)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobDeleteFailedError() from exc

    job_workspace_service.delete_job_files(job_id, project_id, _get_active_settings(settings))

    logger.info("Job deleted: %s", job_id)
    return {"deleted": True, "job_id": job_id}


def list_interrupted_processing_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> JobListResponse:
    return list_interrupted_jobs_response(db, limit=limit, offset=offset)


def get_job_preflight(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> JobPreflightResponse:
    return run_job_preflight(db, job_id, settings)


def retry_processing_job(
    db: Session,
    job_id: str,
    request: JobRetryRequest,
    settings: Settings | None = None,
) -> JobControlResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.status not in {"failed", "interrupted", "cancelled"}:
        raise JobRetryNotAllowedError(
            details={"status": job.status, "reason": "Job is not retryable."}
        )
    if job.retry_count >= job.max_retries:
        raise JobRetryNotAllowedError(
            details={"retry_count": job.retry_count, "max_retries": job.max_retries}
        )

    if request.cleanup_before_retry:
        cleanup_job_temp_files(db, job.id, settings=active_settings)

    reset_values: dict[str, object] = {
        "status": "pending",
        "current_stage": "idle",
        "retry_count": job.retry_count + 1,
        "last_retry_at": _utcnow(),
        "recovered_at": _utcnow(),
        "error_code": None,
        "error_message": None,
        "preflight_error_code": None,
        "preflight_error_message": None,
        "cleanup_error_code": None,
        "cleanup_error_message": None,
        "process_id": None,
        "process_kind": None,
        "process_started_at": None,
        "process_ended_at": None,
        "pause_requested": False,
        "cancel_requested": False,
    }
    if request.reset_progress:
        reset_values.update(
            {
                "progress_percent": 0.0,
                "frames_processed": 0,
                "estimated_time_seconds": None,
                "elapsed_time_seconds": None,
                "last_known_stage": job.current_stage,
                "last_known_progress_percent": job.progress_percent,
                "enhancement_error_code": None,
                "enhancement_error_message": None,
                "encoding_error_code": None,
                "encoding_error_message": None,
                "audio_mux_error_code": None,
                "audio_mux_error_message": None,
                "export_error_code": None,
                "export_error_message": None,
                "realesrgan_error_code": None,
                "realesrgan_error_message": None,
            }
        )

    try:
        job = job_repository.update_job(db, job, reset_values)
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Job prepared for retry.",
            stage="retrying",
        )
        db.commit()
        db.refresh(job)
        record_audit_event(
            "job_retried",
            "job",
            job.id,
            "Job prepared for retry.",
            {
                "retry_count": job.retry_count,
                "cleanup_before_retry": request.cleanup_before_retry,
                "reset_progress": request.reset_progress,
            },
            active_settings,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobStartFailedError() from exc

    return JobControlResponse(
        job=job_repository.to_job_response(job),
        message="Job prepared for retry.",
    )


def get_job_progress(db: Session, job_id: str) -> JobProgressResponse:
    job = _get_job_or_raise(db, job_id)
    logger.info("Job progress requested: %s", job.id)
    actions = build_job_actions(job)
    return JobProgressResponse(
        job_id=job.id,
        project_id=job.project_id,
        status=job.status,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        stage_progress_percent=build_stage_progress_percent(job),
        stage_label=build_stage_label(job.current_stage),
        frames_total=job.frames_total,
        frames_processed=job.frames_processed,
        extracted_frames=job.extracted_frames,
        enhanced_frames=job.enhanced_frames,
        estimated_time_seconds=estimate_remaining_seconds(job),
        elapsed_time_seconds=job.elapsed_time_seconds,
        can_start=actions["can_start"],
        can_cancel=actions["can_cancel"],
        can_pause=actions["can_pause"],
        can_retry=actions["can_retry"],
        can_cleanup=actions["can_cleanup"],
        preview_available=is_preview_available(job),
        export_available=is_export_available(job),
        updated_at=job.updated_at,
        enhancer_engine=job.enhancer_engine,
        working_dir=job.working_dir,
        original_frames_dir=job.original_frames_dir,
        enhanced_frames_dir=job.enhanced_frames_dir,
        enhancement_started_at=job.enhancement_started_at,
        enhancement_completed_at=job.enhancement_completed_at,
        encoded_dir=job.encoded_dir,
        encoded_video_path=job.encoded_video_path,
        encoded_video_size_bytes=job.encoded_video_size_bytes,
        encoding_fps=job.encoding_fps,
        encoding_codec=job.encoding_codec,
        encoding_format=job.encoding_format,
        encoding_started_at=job.encoding_started_at,
        encoding_completed_at=job.encoding_completed_at,
        muxed_video_path=job.muxed_video_path,
        muxed_video_file_name=job.muxed_video_file_name,
        muxed_video_size_bytes=job.muxed_video_size_bytes,
        audio_strategy=job.audio_strategy,
        audio_codec=job.audio_codec,
        audio_mux_started_at=job.audio_mux_started_at,
        audio_mux_completed_at=job.audio_mux_completed_at,
        audio_mux_error_code=job.audio_mux_error_code,
        audio_mux_error_message=job.audio_mux_error_message,
        export_id=job.export_id,
        final_export_path=job.final_export_path,
        final_export_file_name=job.final_export_file_name,
        final_export_size_bytes=job.final_export_size_bytes,
        export_started_at=job.export_started_at,
        export_completed_at=job.export_completed_at,
        export_error_code=job.export_error_code,
        export_error_message=job.export_error_message,
        realesrgan_model_slug=job.realesrgan_model_slug,
        realesrgan_device=job.realesrgan_device,
        realesrgan_frames_total=job.realesrgan_frames_total,
        realesrgan_frames_processed=job.realesrgan_frames_processed,
        realesrgan_failed_frames=job.realesrgan_failed_frames,
        realesrgan_average_frame_time_ms=job.realesrgan_average_frame_time_ms,
        realesrgan_error_code=job.realesrgan_error_code,
        realesrgan_error_message=job.realesrgan_error_message,
        error_code=job.error_code,
        error_message=job.error_message,
    )


def get_job_logs(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> JobLogsResponse:
    _get_job_or_raise(db, job_id)
    logger.info("Job logs requested: %s", job_id)
    items = job_repository.list_job_logs(db, job_id=job_id, limit=limit, offset=offset)
    total = job_repository.count_job_logs(db, job_id)
    return JobLogsResponse(
        items=[job_repository.to_job_log_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_job_frames(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> JobFramesResponse:
    job = _get_job_or_raise(db, job_id)
    frames_dir_value = job.original_frames_dir
    if not frames_dir_value:
        raise JobFramesNotFoundError()

    frames_dir = Path(frames_dir_value)
    if not frames_dir.exists():
        raise JobFramesNotFoundError()

    frame_files = sorted(frame for frame in frames_dir.glob("*.png") if frame.is_file())
    if not frame_files:
        raise JobFramesNotFoundError()

    paged_files = frame_files[offset : offset + limit]
    items = [
        JobFrameItem(index=offset + index, file_name=frame.name, path=str(frame))
        for index, frame in enumerate(paged_files)
    ]
    logger.info("Job frames listed: %s", job.id)
    return JobFramesResponse(
        job_id=job.id,
        frames_dir=str(frames_dir),
        items=items,
        total=len(frame_files),
        limit=limit,
        offset=offset,
    )


def get_frame_extraction_summary(
    db: Session,
    job_id: str,
) -> FrameExtractionSummaryResponse:
    job = _get_job_or_raise(db, job_id)
    return FrameExtractionSummaryResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        working_dir=job.working_dir,
        original_frames_dir=job.original_frames_dir,
        enhanced_frames_dir=job.enhanced_frames_dir,
        frame_file_pattern=job.frame_file_pattern,
        frame_format=job.frame_format,
        frames_total=job.frames_total,
        frames_processed=job.frames_processed,
        extracted_frames=job.extracted_frames,
        extraction_started_at=job.extraction_started_at,
        extraction_completed_at=job.extraction_completed_at,
    )


def get_frame_enhancement_summary(
    db: Session,
    job_id: str,
) -> FrameEnhancementSummaryResponse:
    job = _get_job_or_raise(db, job_id)
    return FrameEnhancementSummaryResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        enhancer_engine=job.enhancer_engine,
        original_frames_dir=job.original_frames_dir,
        enhanced_frames_dir=job.enhanced_frames_dir,
        extracted_frames=job.extracted_frames,
        enhanced_frames=job.enhanced_frames,
        enhancement_started_at=job.enhancement_started_at,
        enhancement_completed_at=job.enhancement_completed_at,
        enhancement_error_code=job.enhancement_error_code,
        enhancement_error_message=job.enhancement_error_message,
    )


def get_realesrgan_job_summary(
    db: Session,
    job_id: str,
) -> RealESRGANJobSummaryResponse:
    return get_realesrgan_job_summary_response(db, job_id)


def validate_realesrgan_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> RealESRGANJobValidationResponse:
    job = _get_job_or_raise(db, job_id)
    return validate_realesrgan_job_requirements(db, job, settings)


def get_job_pipeline(
    db: Session,
    job_id: str,
) -> JobPipelineResponse:
    job = _get_job_or_raise(db, job_id)
    stages = [
        JobPipelineStage(
            name="preflight",
            status="completed" if job.preflight_completed_at else "pending",
            started_at=job.preflight_started_at,
            completed_at=job.preflight_completed_at,
            error_code=job.preflight_error_code,
        ),
        JobPipelineStage(
            name="extracting_frames",
            status="completed" if job.extraction_completed_at else "pending",
            started_at=job.extraction_started_at,
            completed_at=job.extraction_completed_at,
            error_code=job.error_code if job.current_stage == "extracting_frames" else None,
        ),
        JobPipelineStage(
            name="enhancing_frames",
            status="completed" if job.enhancement_completed_at else "pending",
            started_at=job.enhancement_started_at,
            completed_at=job.enhancement_completed_at,
            error_code=job.enhancement_error_code or job.realesrgan_error_code,
        ),
        JobPipelineStage(
            name="encoding_video",
            status="completed" if job.encoding_completed_at else "pending",
            started_at=job.encoding_started_at,
            completed_at=job.encoding_completed_at,
            error_code=job.encoding_error_code,
        ),
        JobPipelineStage(
            name="muxing_audio",
            status="completed" if job.audio_mux_completed_at else "pending",
            started_at=job.audio_mux_started_at,
            completed_at=job.audio_mux_completed_at,
            error_code=job.audio_mux_error_code,
        ),
        JobPipelineStage(
            name="exporting",
            status="completed" if job.export_completed_at else "pending",
            started_at=job.export_started_at,
            completed_at=job.export_completed_at,
            error_code=job.export_error_code,
        ),
    ]
    return JobPipelineResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        stages=stages,
        output={
            "export_id": job.export_id,
            "final_export_path": job.final_export_path,
        },
    )


def get_job_diagnostics(
    db: Session,
    job_id: str,
) -> JobDiagnosticsResponse:
    job = _get_job_or_raise(db, job_id)
    error_info = resolve_error_code_info(job.error_code)
    likely_causes = [error_info.message]
    if job.error_code == "cuda_out_of_memory":
        likely_causes = [
            "The selected model requires more VRAM than available.",
            "Tile size may be too large.",
            "Another application may be using GPU memory.",
        ]
    elif job.error_code == "ffmpeg_not_available":
        likely_causes = [
            "FFmpeg is not installed or not available in PATH.",
            "The backend process may not inherit the expected PATH environment.",
        ]
    return JobDiagnosticsResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        error_code=job.error_code,
        error_message=job.error_message,
        likely_causes=likely_causes,
        suggested_actions=error_info.suggested_actions,
        can_retry=build_job_actions(job)["can_retry"],
        can_cleanup=build_job_actions(job)["can_cleanup"],
        related_logs_url=f"/api/v1/jobs/{job.id}/logs",
    )


def get_job_enhanced_frames(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> JobEnhancedFramesResponse:
    job = _get_job_or_raise(db, job_id)
    return frame_enhancement_service.list_enhanced_frames(job, limit=limit, offset=offset)


def get_video_encoding_summary(
    db: Session,
    job_id: str,
) -> VideoEncodingSummaryResponse:
    job = _get_job_or_raise(db, job_id)
    return video_encoding_service.get_encoded_video_summary(job)


def get_encoded_video(
    db: Session,
    job_id: str,
) -> EncodedVideoResponse:
    job = _get_job_or_raise(db, job_id)
    return video_encoding_service.get_encoded_video_metadata(job)


def get_audio_mux_summary(
    db: Session,
    job_id: str,
) -> AudioMuxSummaryResponse:
    return audio_mux_service.get_muxed_video_summary(db, job_id)


def get_muxed_video(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> MuxedVideoResponse:
    return audio_mux_service.get_muxed_video_metadata(db, job_id, settings)


def get_final_export_summary(
    db: Session,
    job_id: str,
) -> FinalExportSummaryResponse:
    return export_service.get_final_export_summary(db, job_id)


def cleanup_job_temp(
    db: Session,
    job_id: str,
    *,
    include_original_frames: bool = True,
    include_enhanced_frames: bool = True,
    include_encoded: bool = True,
    include_muxed: bool = True,
    settings: Settings | None = None,
) -> CleanupResponse:
    return cleanup_job_temp_files(
        db,
        job_id,
        include_original_frames=include_original_frames,
        include_enhanced_frames=include_enhanced_frames,
        include_encoded=include_encoded,
        include_muxed=include_muxed,
        settings=settings,
    )


def delete_job_frames(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> DeleteFramesResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.status == "running":
        raise JobInvalidStateError()

    delete_job_frames_directories(job.id, active_settings)
    try:
        job = job_repository.update_job(
            db,
            job,
            {
                "original_frames_dir": None,
                "enhanced_frames_dir": None,
                "extracted_frames": 0,
                "enhanced_frames": 0,
                "frames_processed": 0,
                "progress_percent": 0.0,
                "frame_file_pattern": None,
                "extraction_started_at": None,
                "extraction_completed_at": None,
                "enhancer_engine": None,
                "enhancement_started_at": None,
                "enhancement_completed_at": None,
                "enhancement_error_code": None,
                "enhancement_error_message": None,
                "realesrgan_model_slug": None,
                "realesrgan_model_path": None,
                "realesrgan_device": None,
                "realesrgan_scale": None,
                "realesrgan_tile_size": None,
                "realesrgan_tile_pad": None,
                "realesrgan_pre_pad": None,
                "realesrgan_half_precision": None,
                "realesrgan_frames_total": None,
                "realesrgan_frames_processed": 0,
                "realesrgan_failed_frames": 0,
                "realesrgan_average_frame_time_ms": None,
                "realesrgan_started_at": None,
                "realesrgan_completed_at": None,
                "realesrgan_error_code": None,
                "realesrgan_error_message": None,
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Job frames deleted.",
            stage=job.current_stage,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobDeleteFailedError() from exc

    logger.info("Job frames deleted: %s", job.id)
    return DeleteFramesResponse(deleted=True, job_id=job.id)


def delete_job_enhanced_frames(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> DeleteEnhancedFramesResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.status == "running":
        raise JobInvalidStateError()

    enhanced_dir = frame_enhancement_service.clean_enhanced_frames(job.id, active_settings)
    try:
        job = job_repository.update_job(
            db,
            job,
            {
                "enhanced_frames_dir": str(enhanced_dir),
                "enhanced_frames": 0,
                "frames_processed": 0,
                "progress_percent": 0.0,
                "enhancement_started_at": None,
                "enhancement_completed_at": None,
                "enhancement_error_code": None,
                "enhancement_error_message": None,
                "realesrgan_model_slug": None,
                "realesrgan_model_path": None,
                "realesrgan_device": None,
                "realesrgan_scale": None,
                "realesrgan_tile_size": None,
                "realesrgan_tile_pad": None,
                "realesrgan_pre_pad": None,
                "realesrgan_half_precision": None,
                "realesrgan_frames_total": None,
                "realesrgan_frames_processed": 0,
                "realesrgan_failed_frames": 0,
                "realesrgan_average_frame_time_ms": None,
                "realesrgan_started_at": None,
                "realesrgan_completed_at": None,
                "realesrgan_error_code": None,
                "realesrgan_error_message": None,
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Enhanced frames deleted.",
            stage=job.current_stage,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobDeleteFailedError() from exc

    return DeleteEnhancedFramesResponse(deleted=True, job_id=job.id)


def delete_encoded_video(
    db: Session,
    job_id: str,
) -> DeleteEncodedVideoResponse:
    job = _get_job_or_raise(db, job_id)
    if job.status == "running":
        raise JobInvalidStateError()

    encoded_path = Path(job.encoded_video_path) if job.encoded_video_path else None
    if encoded_path and encoded_path.exists() and encoded_path.is_file():
        encoded_path.unlink()

    try:
        job = job_repository.update_job(
            db,
            job,
            {
                "encoded_dir": None,
                "encoded_video_path": None,
                "encoded_video_file_name": None,
                "encoded_video_size_bytes": None,
                "encoding_fps": None,
                "encoding_codec": None,
                "encoding_format": None,
                "encoding_started_at": None,
                "encoding_completed_at": None,
                "encoding_error_code": None,
                "encoding_error_message": None,
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Encoded video deleted.",
            stage=job.current_stage,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise JobDeleteFailedError() from exc

    return DeleteEncodedVideoResponse(deleted=True, job_id=job.id)


def delete_muxed_video(
    db: Session,
    job_id: str,
) -> DeleteMuxedVideoResponse:
    job = _get_job_or_raise(db, job_id)
    if job.status == "running":
        raise JobInvalidStateError()
    return audio_mux_service.delete_muxed_video(db, job_id)
