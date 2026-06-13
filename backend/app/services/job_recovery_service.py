from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import JobRecoveryFailedError, JobRetryNotAllowedError
from app.core.logging import get_logger
from app.db.models import ProcessingJob
from app.db.repositories import job_repository
from app.schemas.job_schema import JobControlResponse, JobListResponse
from app.services.audit_log_service import record_audit_event

logger = get_logger(__name__)
RECOVERABLE_STATUSES = {"queued", "running", "retrying", "cleaning"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def mark_job_as_interrupted(db: Session, job: ProcessingJob) -> ProcessingJob:
    interrupted_at = _utcnow()
    updated_job = job_repository.update_job(
        db,
        job,
        {
            "status": "interrupted",
            "current_stage": "interrupted",
            "interrupted_at": interrupted_at,
            "last_known_stage": job.current_stage,
            "last_known_progress_percent": job.progress_percent,
            "error_code": "job_interrupted",
            "error_message": "Job was interrupted during backend shutdown or restart.",
            "process_id": None,
            "process_kind": None,
            "process_ended_at": interrupted_at,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "warning",
        "Job marked as interrupted during backend startup recovery.",
        stage="interrupted",
    )
    record_audit_event(
        "job_interrupted",
        "job",
        job.id,
        "Job marked as interrupted during backend startup recovery.",
    )
    return updated_job


def recover_interrupted_jobs_on_startup(
    db: Session,
    settings: Settings | None = None,
) -> int:
    active_settings = _get_active_settings(settings)
    if not active_settings.job_recovery_enabled:
        return 0
    if not active_settings.mark_running_jobs_interrupted_on_startup:
        return 0

    affected_jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.status.in_(tuple(RECOVERABLE_STATUSES)))
        .order_by(ProcessingJob.created_at.asc())
        .all()
    )
    recovered_count = 0
    try:
        for job in affected_jobs:
            mark_job_as_interrupted(db, job)
            recovered_count += 1
        db.commit()
    except SQLAlchemyError as exc:  # pragma: no cover - defensive recovery wrapper
        db.rollback()
        logger.exception("Job recovery failed")
        raise JobRecoveryFailedError() from exc
    logger.info("Startup job recovery completed: %s", recovered_count)
    return recovered_count


def list_interrupted_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> JobListResponse:
    items = job_repository.list_jobs(db, limit=limit, offset=offset, status="interrupted")
    total = job_repository.count_jobs(db, status="interrupted")
    return JobListResponse(
        items=[job_repository.to_job_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def recover_job_for_retry(db: Session, job: ProcessingJob) -> JobControlResponse:
    if job.status not in {"interrupted", "failed", "cancelled"}:
        raise JobRetryNotAllowedError(
            details={"status": job.status, "reason": "Job is not in a retryable state."}
        )

    updated_job = job_repository.update_job(
        db,
        job,
        {
            "status": "pending",
            "current_stage": "idle",
            "recovered_at": _utcnow(),
            "error_code": None,
            "error_message": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Interrupted job recovered and prepared for retry.",
        stage="retrying",
    )
    db.commit()
    db.refresh(updated_job)
    return JobControlResponse(
        job=job_repository.to_job_response(updated_job),
        message="Interrupted job prepared for retry.",
    )
