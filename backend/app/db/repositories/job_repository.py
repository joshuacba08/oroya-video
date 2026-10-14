import json
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import JobLog, ProcessingJob
from app.schemas.job_schema import JobLogResponse, JobResponse
from app.services.job_contract_service import build_job_actions, estimate_remaining_seconds


def create_job(db: Session, data: dict) -> ProcessingJob:
    job = ProcessingJob(**data)
    db.add(job)
    db.flush()
    db.refresh(job)
    return job


def get_job_by_id(db: Session, job_id: str) -> ProcessingJob | None:
    return db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()


PREVIEW_JOB_KIND = "preview"


def export_jobs_query(db: Session):
    """Jobs the user sees (queue, history, dashboard): everything but motion previews."""
    return db.query(ProcessingJob).filter(
        or_(ProcessingJob.job_kind.is_(None), ProcessingJob.job_kind != PREVIEW_JOB_KIND)
    )


def list_jobs(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    project_id: str | None = None,
) -> list[ProcessingJob]:
    query = export_jobs_query(db)
    if status:
        query = query.filter(ProcessingJob.status == status)
    if project_id:
        query = query.filter(ProcessingJob.project_id == project_id)

    return query.order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit).all()


def count_jobs(
    db: Session,
    status: str | None = None,
    project_id: str | None = None,
) -> int:
    query = export_jobs_query(db)
    if status:
        query = query.filter(ProcessingJob.status == status)
    if project_id:
        query = query.filter(ProcessingJob.project_id == project_id)

    return query.count()


def update_job(db: Session, job: ProcessingJob, data: dict) -> ProcessingJob:
    for key, value in data.items():
        setattr(job, key, value)
    db.flush()
    db.refresh(job)
    return job


def delete_job(db: Session, job: ProcessingJob) -> None:
    db.delete(job)
    db.flush()


def create_job_log(
    db: Session,
    job_id: str,
    level: str,
    message: str,
    stage: str | None = None,
) -> JobLog:
    log = JobLog(
        id=str(uuid.uuid4()),
        job_id=job_id,
        level=level,
        message=message,
        stage=stage,
    )
    db.add(log)
    db.flush()
    db.refresh(log)
    return log


def list_job_logs(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[JobLog]:
    return (
        db.query(JobLog)
        .filter(JobLog.job_id == job_id)
        .order_by(JobLog.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_job_logs(db: Session, job_id: str) -> int:
    return db.query(JobLog).filter(JobLog.job_id == job_id).count()


def to_job_response(job: ProcessingJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        project_id=job.project_id,
        video_asset_id=job.video_asset_id,
        ai_model_id=job.ai_model_id,
        ai_model_slug=job.ai_model_slug,
        status=job.status,
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        frames_total=job.frames_total,
        frames_processed=job.frames_processed,
        estimated_time_seconds=estimate_remaining_seconds(job),
        elapsed_time_seconds=job.elapsed_time_seconds,
        enhancement_config=_deserialize_json_object(job.enhancement_config_json),
        export_config=_deserialize_json_object(job.export_config_json),
        output_path=job.output_path,
        error_code=job.error_code,
        error_message=job.error_message,
        working_dir=job.working_dir,
        original_frames_dir=job.original_frames_dir,
        enhanced_frames_dir=job.enhanced_frames_dir,
        frame_file_pattern=job.frame_file_pattern,
        frame_format=job.frame_format,
        extracted_frames=job.extracted_frames,
        enhancer_engine=job.enhancer_engine,
        enhanced_frames=job.enhanced_frames,
        pipeline_mode=job.pipeline_mode,
        segments_completed=job.segments_completed,
        segments_total=job.segments_total,
        preview_frame_index=job.preview_frame_index,
        job_kind=job.job_kind,
        extraction_started_at=job.extraction_started_at,
        extraction_completed_at=job.extraction_completed_at,
        enhancement_started_at=job.enhancement_started_at,
        enhancement_completed_at=job.enhancement_completed_at,
        enhancement_error_code=job.enhancement_error_code,
        enhancement_error_message=job.enhancement_error_message,
        encoded_dir=job.encoded_dir,
        encoded_video_path=job.encoded_video_path,
        encoded_video_file_name=job.encoded_video_file_name,
        encoded_video_size_bytes=job.encoded_video_size_bytes,
        encoding_fps=job.encoding_fps,
        encoding_codec=job.encoding_codec,
        encoding_format=job.encoding_format,
        encoding_started_at=job.encoding_started_at,
        encoding_completed_at=job.encoding_completed_at,
        encoding_error_code=job.encoding_error_code,
        encoding_error_message=job.encoding_error_message,
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
        retry_count=job.retry_count,
        max_retries=job.max_retries,
        last_retry_at=job.last_retry_at,
        interrupted_at=job.interrupted_at,
        recovered_at=job.recovered_at,
        cleanup_started_at=job.cleanup_started_at,
        cleanup_completed_at=job.cleanup_completed_at,
        cleanup_error_code=job.cleanup_error_code,
        cleanup_error_message=job.cleanup_error_message,
        preflight_started_at=job.preflight_started_at,
        preflight_completed_at=job.preflight_completed_at,
        preflight_error_code=job.preflight_error_code,
        preflight_error_message=job.preflight_error_message,
        last_known_stage=job.last_known_stage,
        last_known_progress_percent=job.last_known_progress_percent,
        worker_id=job.worker_id,
        process_id=job.process_id,
        process_kind=job.process_kind,
        process_started_at=job.process_started_at,
        process_ended_at=job.process_ended_at,
        temp_size_bytes=job.temp_size_bytes,
        original_frames_size_bytes=job.original_frames_size_bytes,
        enhanced_frames_size_bytes=job.enhanced_frames_size_bytes,
        encoded_size_bytes=job.encoded_size_bytes,
        muxed_size_bytes=job.muxed_size_bytes,
        exports_size_bytes=job.exports_size_bytes,
        realesrgan_model_slug=job.realesrgan_model_slug,
        realesrgan_model_path=job.realesrgan_model_path,
        realesrgan_device=job.realesrgan_device,
        realesrgan_scale=job.realesrgan_scale,
        realesrgan_tile_size=job.realesrgan_tile_size,
        realesrgan_tile_pad=job.realesrgan_tile_pad,
        realesrgan_pre_pad=job.realesrgan_pre_pad,
        realesrgan_half_precision=job.realesrgan_half_precision,
        realesrgan_frames_total=job.realesrgan_frames_total,
        realesrgan_frames_processed=job.realesrgan_frames_processed,
        realesrgan_failed_frames=job.realesrgan_failed_frames,
        realesrgan_average_frame_time_ms=job.realesrgan_average_frame_time_ms,
        realesrgan_started_at=job.realesrgan_started_at,
        realesrgan_completed_at=job.realesrgan_completed_at,
        realesrgan_error_code=job.realesrgan_error_code,
        realesrgan_error_message=job.realesrgan_error_message,
        pause_requested=job.pause_requested,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        cancelled_at=job.cancelled_at,
        actions=build_job_actions(job),
    )


def to_job_log_response(log: JobLog) -> JobLogResponse:
    return JobLogResponse(
        id=log.id,
        job_id=log.job_id,
        level=log.level,
        message=log.message,
        stage=log.stage,
        created_at=log.created_at,
    )


def _deserialize_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return value if isinstance(value, dict) else {}
