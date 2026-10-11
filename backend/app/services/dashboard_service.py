from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import AIModel, ExportAsset, ProcessingJob, Project, VideoAsset
from app.schemas.hardening_schema import QueueItemResponse, QueueResponse
from app.schemas.settings_schema import (
    AppStateBackendResponse,
    AppStateQueueResponse,
    AppStateResponse,
    AppStateStorageResponse,
    AppStateSystemResponse,
    BootstrapAppResponse,
    BootstrapCountsResponse,
    BootstrapResponse,
    BootstrapSystemResponse,
    DashboardModelsResponse,
    DashboardResponse,
    DashboardStorageResponse,
    DashboardSystemStatusResponse,
)
from app.services.ai_runtime_service import get_ai_runtime_status
from app.services.cleanup_service import get_storage_usage
from app.services.job_contract_service import build_job_actions
from app.services.settings_service import build_settings_response
from app.services.system_service import get_requirements_status
from app.services.tool_detection_service import get_tools_status

logger = get_logger(__name__)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def get_bootstrap_response(db: Session, settings: Settings | None = None) -> BootstrapResponse:
    active_settings = _get_active_settings(settings)
    tools = get_tools_status()
    ai_runtime = get_ai_runtime_status(active_settings)
    counts = BootstrapCountsResponse(
        projects=db.query(Project).count(),
        videos=db.query(VideoAsset).count(),
        jobs_running=db.query(ProcessingJob).filter(ProcessingJob.status == "running").count(),
        jobs_interrupted=(
            db.query(ProcessingJob).filter(ProcessingJob.status == "interrupted").count()
        ),
        exports=db.query(ExportAsset).count(),
        models_installed=db.query(AIModel).filter(AIModel.is_installed.is_(True)).count(),
    )
    return BootstrapResponse(
        app=BootstrapAppResponse(
            name=active_settings.app_name,
            version=active_settings.app_version,
            api_version=active_settings.api_version,
            environment=active_settings.environment,
        ),
        system=BootstrapSystemResponse(
            ffmpeg_available=tools.ffmpeg.available,
            ffprobe_available=tools.ffprobe.available,
            gpu_available=bool(ai_runtime.cuda_devices),
            ai_runtime_available=ai_runtime.available,
        ),
        settings={
            "frame_enhancer_engine": active_settings.frame_enhancer_engine,
            "ai_device": active_settings.ai_device,
            "storage_path": active_settings.storage_path,
        },
        counts=counts,
        warnings=get_requirements_status(active_settings).warnings,
    )


def _serialize_job_item(job: ProcessingJob) -> dict:
    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "progress_percent": job.progress_percent,
        "model_slug": job.ai_model_slug,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "actions": build_job_actions(job),
    }


def get_dashboard_response(db: Session, settings: Settings | None = None) -> DashboardResponse:
    active_settings = _get_active_settings(settings)
    requirements = get_requirements_status(active_settings)
    storage_usage = get_storage_usage(active_settings)
    recent_projects = db.query(Project).order_by(Project.updated_at.desc()).limit(5).all()
    recent_exports = db.query(ExportAsset).order_by(ExportAsset.created_at.desc()).limit(5).all()
    active_jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.status.in_(("queued", "running", "retrying")))
        .order_by(ProcessingJob.updated_at.desc())
        .limit(10)
        .all()
    )
    interrupted_jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.status == "interrupted")
        .order_by(ProcessingJob.updated_at.desc())
        .limit(10)
        .all()
    )
    return DashboardResponse(
        recent_projects=[
            {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "updated_at": project.updated_at,
            }
            for project in recent_projects
        ],
        recent_exports=[
            {
                "id": export.id,
                "job_id": export.job_id,
                "project_id": export.project_id,
                "file_name": export.file_name,
                "created_at": export.created_at,
            }
            for export in recent_exports
        ],
        active_jobs=[_serialize_job_item(job) for job in active_jobs],
        interrupted_jobs=[_serialize_job_item(job) for job in interrupted_jobs],
        system_status=DashboardSystemStatusResponse(
            ready=requirements.ready,
            warnings=requirements.warnings,
        ),
        storage=DashboardStorageResponse(
            free_bytes=int(storage_usage["free_bytes"]),
            used_by_oroya_bytes=int(storage_usage["used_by_oroya_bytes"]),
        ),
        models=DashboardModelsResponse(
            installed=db.query(AIModel).filter(AIModel.is_installed.is_(True)).count(),
            missing=db.query(AIModel).filter(AIModel.is_installed.is_(False)).count(),
            enabled=db.query(AIModel).filter(AIModel.is_enabled.is_(True)).count(),
        ),
    )


def get_app_state_response(db: Session, settings: Settings | None = None) -> AppStateResponse:
    active_settings = _get_active_settings(settings)
    storage_usage = get_storage_usage(active_settings)
    requirements = get_requirements_status(active_settings)
    ai_runtime = get_ai_runtime_status(active_settings)
    return AppStateResponse(
        backend=AppStateBackendResponse(
            online=True,
            version=active_settings.app_version,
            api_version=active_settings.api_version,
        ),
        queue=AppStateQueueResponse(
            running=db.query(ProcessingJob).filter(ProcessingJob.status == "running").count(),
            queued=db.query(ProcessingJob).filter(ProcessingJob.status == "queued").count(),
            pending=db.query(ProcessingJob).filter(ProcessingJob.status == "pending").count(),
            interrupted=(
                db.query(ProcessingJob).filter(ProcessingJob.status == "interrupted").count()
            ),
        ),
        system=AppStateSystemResponse(
            ready=requirements.ready,
            gpu_available=bool(ai_runtime.cuda_devices),
            ai_runtime_available=ai_runtime.available,
        ),
        storage=AppStateStorageResponse(
            free_bytes=int(storage_usage["free_bytes"]),
            temp_bytes=int(storage_usage["breakdown"]["temp_bytes"]),
        ),
    )


# Pausados y fallidos se muestran para poder reanudarlos o reintentarlos desde la cola.
QUEUE_VISIBLE_STATUSES = (
    "pending",
    "queued",
    "running",
    "paused",
    "retrying",
    "interrupted",
    "failed",
)


def get_queue_response(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
) -> QueueResponse:
    items = (
        db.query(ProcessingJob, Project.name)
        .outerjoin(Project, Project.id == ProcessingJob.project_id)
        .filter(ProcessingJob.status.in_(QUEUE_VISIBLE_STATUSES))
        .order_by(ProcessingJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    response_items = [
        QueueItemResponse(
            job_id=job.id,
            project_id=job.project_id,
            project_name=project_name,
            status=job.status,
            current_stage=job.current_stage,
            progress_percent=job.progress_percent,
            model_slug=job.ai_model_slug,
            created_at=job.created_at,
            started_at=job.started_at,
            frames_total=job.frames_total or 0,
            frames_processed=job.frames_processed or 0,
            elapsed_time_seconds=job.elapsed_time_seconds or 0,
            error_code=job.error_code,
            error_message=job.error_message,
            enhancer_engine=job.enhancer_engine,
            realesrgan_device=job.realesrgan_device,
            realesrgan_frames_total=job.realesrgan_frames_total,
            realesrgan_frames_processed=job.realesrgan_frames_processed,
            realesrgan_failed_frames=job.realesrgan_failed_frames,
            realesrgan_average_frame_time_ms=job.realesrgan_average_frame_time_ms,
            retry_count=job.retry_count or 0,
            max_retries=job.max_retries or 0,
            actions=build_job_actions(job),
        )
        for job, project_name in items
    ]
    total = db.query(ProcessingJob).filter(ProcessingJob.status.in_(QUEUE_VISIBLE_STATUSES)).count()
    return QueueResponse(
        items=response_items,
        total=total,
        running=db.query(ProcessingJob).filter(ProcessingJob.status == "running").count(),
        queued=db.query(ProcessingJob).filter(ProcessingJob.status == "queued").count(),
        pending=db.query(ProcessingJob).filter(ProcessingJob.status == "pending").count(),
        interrupted=db.query(ProcessingJob).filter(ProcessingJob.status == "interrupted").count(),
        paused=db.query(ProcessingJob).filter(ProcessingJob.status == "paused").count(),
        failed=db.query(ProcessingJob).filter(ProcessingJob.status == "failed").count(),
        limit=limit,
        offset=offset,
    )


def get_settings_overview(settings: Settings | None = None) -> dict:
    return build_settings_response(_get_active_settings(settings)).model_dump(mode="json")
