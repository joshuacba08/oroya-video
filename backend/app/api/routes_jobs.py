import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import JobNotFoundError
from app.db import database
from app.db.database import get_db
from app.schemas.hardening_schema import (
    CleanupResponse,
    JobDiagnosticsResponse,
    JobPipelineResponse,
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
    JobDeleteResponse,
    JobDetailResponse,
    JobEnhancedFramesResponse,
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
from app.services.job_service import (
    cancel_processing_job,
    cleanup_job_temp,
    create_processing_job,
    delete_encoded_video,
    delete_job_enhanced_frames,
    delete_job_frames,
    delete_muxed_video,
    delete_processing_job,
    get_audio_mux_summary,
    get_encoded_video,
    get_final_export_summary,
    get_frame_enhancement_summary,
    get_frame_extraction_summary,
    get_job_diagnostics,
    get_job_enhanced_frames,
    get_job_frames,
    get_job_logs,
    get_job_pipeline,
    get_job_preflight,
    get_job_progress,
    get_muxed_video,
    get_processing_job_detail,
    get_realesrgan_job_summary,
    get_video_encoding_summary,
    list_interrupted_processing_jobs,
    list_processing_jobs,
    pause_processing_job,
    resume_processing_job,
    retry_processing_job,
    start_processing_job,
    validate_realesrgan_job,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=JobDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a processing job",
)
def create_job_route(
    payload: JobCreateRequest,
    request: Request,
    db: DbSession,
) -> JobDetailResponse:
    return create_processing_job(
        db=db,
        request=payload,
        settings=request.app.state.settings,
    )


@router.get("", response_model=JobListResponse, summary="List processing jobs")
def list_jobs_route(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    project_id: str | None = None,
) -> JobListResponse:
    return list_processing_jobs(
        db=db,
        limit=limit,
        offset=offset,
        status=status,
        project_id=project_id,
    )


@router.get(
    "/interrupted",
    response_model=JobListResponse,
    summary="List interrupted jobs",
)
def list_interrupted_jobs_route(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    return list_interrupted_processing_jobs(db=db, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobDetailResponse, summary="Get job detail")
def get_job_route(job_id: str, db: DbSession) -> JobDetailResponse:
    return get_processing_job_detail(db=db, job_id=job_id)


@router.post("/{job_id}/start", response_model=JobControlResponse, summary="Queue a job")
async def start_job_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> JobControlResponse:
    return await start_processing_job(db=db, job_id=job_id, settings=request.app.state.settings)


@router.post("/{job_id}/pause", response_model=JobControlResponse, summary="Pause a job")
def pause_job_route(job_id: str, db: DbSession) -> JobControlResponse:
    return pause_processing_job(db=db, job_id=job_id)


@router.post("/{job_id}/resume", response_model=JobControlResponse, summary="Resume a job")
async def resume_job_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> JobControlResponse:
    return await resume_processing_job(db=db, job_id=job_id, settings=request.app.state.settings)


@router.post("/{job_id}/cancel", response_model=JobControlResponse, summary="Cancel a job")
def cancel_job_route(job_id: str, db: DbSession) -> JobControlResponse:
    return cancel_processing_job(db=db, job_id=job_id)


@router.delete("/{job_id}", response_model=JobDeleteResponse, summary="Delete a job")
def delete_job_route(job_id: str, request: Request, db: DbSession) -> JobDeleteResponse:
    return delete_processing_job(db=db, job_id=job_id, settings=request.app.state.settings)


@router.get("/{job_id}/progress", response_model=JobProgressResponse, summary="Get job progress")
def get_job_progress_route(job_id: str, db: DbSession) -> JobProgressResponse:
    return get_job_progress(db=db, job_id=job_id)


SSE_POLL_INTERVAL_SECONDS = 0.5
SSE_KEEPALIVE_SECONDS = 15.0
SSE_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted", "paused"}


def _read_progress_json(job_id: str) -> str | None:
    if database.SessionLocal is None:
        return None
    db = database.SessionLocal()
    try:
        return get_job_progress(db=db, job_id=job_id).model_dump_json()
    except JobNotFoundError:
        return None
    finally:
        db.close()


@router.get(
    "/{job_id}/events",
    summary="Stream job progress as Server-Sent Events",
    response_class=StreamingResponse,
)
async def job_events_route(job_id: str, request: Request) -> StreamingResponse:
    """Pushes the same payload as GET /progress whenever it changes; closes when the job
    reaches a terminal or paused state. Clients fall back to polling if this fails."""
    if await asyncio.to_thread(_read_progress_json, job_id) is None:
        raise JobNotFoundError()

    async def stream():
        last_payload: str | None = None
        last_sent = time.monotonic()
        while not await request.is_disconnected():
            payload = await asyncio.to_thread(_read_progress_json, job_id)
            if payload is None:
                return
            if payload != last_payload:
                last_payload = payload
                last_sent = time.monotonic()
                yield f"data: {payload}\n\n"
                if json.loads(payload)["status"] in SSE_TERMINAL_STATUSES:
                    return
            elif time.monotonic() - last_sent >= SSE_KEEPALIVE_SECONDS:
                last_sent = time.monotonic()
                yield ": keepalive\n\n"
            await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{job_id}/preflight",
    response_model=JobPreflightResponse,
    summary="Run job preflight checks",
)
def get_job_preflight_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> JobPreflightResponse:
    return get_job_preflight(db=db, job_id=job_id, settings=request.app.state.settings)


@router.get("/{job_id}/logs", response_model=JobLogsResponse, summary="Get job logs")
def get_job_logs_route(
    job_id: str,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JobLogsResponse:
    return get_job_logs(db=db, job_id=job_id, limit=limit, offset=offset)


@router.post(
    "/{job_id}/retry",
    response_model=JobControlResponse,
    summary="Prepare a job retry (and optionally queue it)",
)
async def retry_job_route(
    job_id: str,
    payload: JobRetryRequest,
    request: Request,
    db: DbSession,
) -> JobControlResponse:
    response = await asyncio.to_thread(
        retry_processing_job,
        db=db,
        job_id=job_id,
        request=payload,
        settings=request.app.state.settings,
    )
    if not payload.start:
        return response
    return await start_processing_job(
        db=db,
        job_id=job_id,
        settings=request.app.state.settings,
    )


@router.get("/{job_id}/frames", response_model=JobFramesResponse, summary="List extracted frames")
def get_job_frames_route(
    job_id: str,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JobFramesResponse:
    return get_job_frames(db=db, job_id=job_id, limit=limit, offset=offset)


@router.get(
    "/{job_id}/enhanced-frames",
    response_model=JobEnhancedFramesResponse,
    summary="List enhanced frames",
)
def get_job_enhanced_frames_route(
    job_id: str,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JobEnhancedFramesResponse:
    return get_job_enhanced_frames(db=db, job_id=job_id, limit=limit, offset=offset)


@router.get(
    "/{job_id}/frame-extraction",
    response_model=FrameExtractionSummaryResponse,
    summary="Get frame extraction summary",
)
def get_job_frame_extraction_summary_route(
    job_id: str,
    db: DbSession,
) -> FrameExtractionSummaryResponse:
    return get_frame_extraction_summary(db=db, job_id=job_id)


@router.get(
    "/{job_id}/frame-enhancement",
    response_model=FrameEnhancementSummaryResponse,
    summary="Get frame enhancement summary",
)
def get_job_frame_enhancement_summary_route(
    job_id: str,
    db: DbSession,
) -> FrameEnhancementSummaryResponse:
    return get_frame_enhancement_summary(db=db, job_id=job_id)


@router.get(
    "/{job_id}/pipeline",
    response_model=JobPipelineResponse,
    summary="Get job pipeline summary",
)
def get_job_pipeline_route(
    job_id: str,
    db: DbSession,
) -> JobPipelineResponse:
    return get_job_pipeline(db=db, job_id=job_id)


@router.get(
    "/{job_id}/diagnostics",
    response_model=JobDiagnosticsResponse,
    summary="Get job diagnostics",
)
def get_job_diagnostics_route(
    job_id: str,
    db: DbSession,
) -> JobDiagnosticsResponse:
    return get_job_diagnostics(db=db, job_id=job_id)


@router.get(
    "/{job_id}/realesrgan",
    response_model=RealESRGANJobSummaryResponse,
    summary="Get Real-ESRGAN job summary",
)
def get_job_realesrgan_summary_route(
    job_id: str,
    db: DbSession,
) -> RealESRGANJobSummaryResponse:
    return get_realesrgan_job_summary(db=db, job_id=job_id)


@router.post(
    "/{job_id}/realesrgan/validate",
    response_model=RealESRGANJobValidationResponse,
    summary="Validate Real-ESRGAN job requirements",
)
def validate_job_realesrgan_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> RealESRGANJobValidationResponse:
    return validate_realesrgan_job(
        db=db,
        job_id=job_id,
        settings=request.app.state.settings,
    )


@router.get(
    "/{job_id}/video-encoding",
    response_model=VideoEncodingSummaryResponse,
    summary="Get video encoding summary",
)
def get_job_video_encoding_summary_route(
    job_id: str,
    db: DbSession,
) -> VideoEncodingSummaryResponse:
    return get_video_encoding_summary(db=db, job_id=job_id)


@router.get(
    "/{job_id}/encoded-video",
    response_model=EncodedVideoResponse,
    summary="Get encoded video metadata",
)
def get_job_encoded_video_route(
    job_id: str,
    db: DbSession,
) -> EncodedVideoResponse:
    return get_encoded_video(db=db, job_id=job_id)


@router.get(
    "/{job_id}/audio-mux",
    response_model=AudioMuxSummaryResponse,
    summary="Get audio mux summary",
)
def get_job_audio_mux_summary_route(
    job_id: str,
    db: DbSession,
) -> AudioMuxSummaryResponse:
    return get_audio_mux_summary(db=db, job_id=job_id)


@router.get(
    "/{job_id}/muxed-video",
    response_model=MuxedVideoResponse,
    summary="Get muxed video metadata",
)
def get_job_muxed_video_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> MuxedVideoResponse:
    return get_muxed_video(db=db, job_id=job_id, settings=request.app.state.settings)


@router.get(
    "/{job_id}/final-export",
    response_model=FinalExportSummaryResponse,
    summary="Get final export summary",
)
def get_job_final_export_summary_route(
    job_id: str,
    db: DbSession,
) -> FinalExportSummaryResponse:
    return get_final_export_summary(db=db, job_id=job_id)


@router.delete(
    "/{job_id}/frames",
    response_model=DeleteFramesResponse,
    summary="Delete extracted frames",
)
def delete_job_frames_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> DeleteFramesResponse:
    return delete_job_frames(db=db, job_id=job_id, settings=request.app.state.settings)


@router.delete(
    "/{job_id}/enhanced-frames",
    response_model=DeleteEnhancedFramesResponse,
    summary="Delete enhanced frames",
)
def delete_job_enhanced_frames_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> DeleteEnhancedFramesResponse:
    return delete_job_enhanced_frames(
        db=db,
        job_id=job_id,
        settings=request.app.state.settings,
    )


@router.delete(
    "/{job_id}/temp",
    response_model=CleanupResponse,
    summary="Delete safe temporary files for a job",
)
def cleanup_job_temp_route(
    job_id: str,
    request: Request,
    db: DbSession,
    include_original_frames: bool = Query(default=True),
    include_enhanced_frames: bool = Query(default=True),
    include_encoded: bool = Query(default=True),
    include_muxed: bool = Query(default=True),
) -> CleanupResponse:
    return cleanup_job_temp(
        db=db,
        job_id=job_id,
        include_original_frames=include_original_frames,
        include_enhanced_frames=include_enhanced_frames,
        include_encoded=include_encoded,
        include_muxed=include_muxed,
        settings=request.app.state.settings,
    )


@router.delete(
    "/{job_id}/encoded-video",
    response_model=DeleteEncodedVideoResponse,
    summary="Delete encoded video",
)
def delete_job_encoded_video_route(
    job_id: str,
    db: DbSession,
) -> DeleteEncodedVideoResponse:
    return delete_encoded_video(db=db, job_id=job_id)


@router.delete(
    "/{job_id}/muxed-video",
    response_model=DeleteMuxedVideoResponse,
    summary="Delete muxed video",
)
def delete_job_muxed_video_route(
    job_id: str,
    db: DbSession,
) -> DeleteMuxedVideoResponse:
    return delete_muxed_video(db=db, job_id=job_id)
