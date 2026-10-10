from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.preview_schema import (
    CompareFrameResponse,
    PreviewFrameListResponse,
    PreviewInfoResponse,
)
from app.services.preview_service import (
    get_compare_frame_info,
    get_enhanced_frame_path,
    get_filtered_frame_path,
    get_original_frame_path,
    get_preview_info,
    get_recommended_preview_frame_index,
    list_preview_frames,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/jobs/{job_id}/preview",
    response_model=PreviewInfoResponse,
    summary="Get preview metadata",
)
def get_preview_info_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> PreviewInfoResponse:
    return get_preview_info(db=db, job_id=job_id, settings=request.app.state.settings)


@router.get(
    "/jobs/{job_id}/preview/original/{frame_index}",
    summary="Get original preview frame",
)
def get_original_preview_frame_route(
    job_id: str,
    frame_index: int,
    db: DbSession,
) -> FileResponse:
    path = get_original_frame_path(db=db, job_id=job_id, frame_index=frame_index)
    return FileResponse(path, media_type="image/png")


@router.get(
    "/jobs/{job_id}/preview/enhanced/{frame_index}",
    summary="Get enhanced preview frame",
)
def get_enhanced_preview_frame_route(
    job_id: str,
    frame_index: int,
    db: DbSession,
) -> FileResponse:
    path = get_enhanced_frame_path(db=db, job_id=job_id, frame_index=frame_index)
    return FileResponse(path, media_type="image/png")


@router.get(
    "/jobs/{job_id}/preview/filtered/{frame_index}",
    summary="Get enhanced preview frame with export filters applied",
)
def get_filtered_preview_frame_route(
    job_id: str,
    frame_index: int,
    request: Request,
    db: DbSession,
    denoise: int | None = Query(default=None, ge=0, le=100),
    sharpen: int | None = Query(default=None, ge=0, le=100),
    compression_cleanup: bool | None = Query(default=None),
) -> FileResponse:
    path = get_filtered_frame_path(
        db=db,
        job_id=job_id,
        frame_index=frame_index,
        denoise=denoise,
        sharpen=sharpen,
        compression_cleanup=compression_cleanup,
        settings=request.app.state.settings,
    )
    return FileResponse(path, media_type="image/png")


@router.get(
    "/jobs/{job_id}/preview/compare/{frame_index}",
    response_model=CompareFrameResponse,
    summary="Get compare preview metadata",
)
def get_compare_preview_route(
    job_id: str,
    frame_index: int,
    request: Request,
    db: DbSession,
) -> CompareFrameResponse:
    return get_compare_frame_info(
        db=db,
        job_id=job_id,
        frame_index=frame_index,
        settings=request.app.state.settings,
    )


@router.get(
    "/jobs/{job_id}/preview/recommended",
    response_model=CompareFrameResponse,
    summary="Get recommended compare preview metadata",
)
def get_recommended_preview_route(
    job_id: str,
    request: Request,
    db: DbSession,
) -> CompareFrameResponse:
    frame_index = get_recommended_preview_frame_index(db=db, job_id=job_id)
    return get_compare_frame_info(
        db=db,
        job_id=job_id,
        frame_index=frame_index,
        settings=request.app.state.settings,
    )


@router.get(
    "/jobs/{job_id}/preview/frames",
    response_model=PreviewFrameListResponse,
    summary="List preview frames",
)
def list_preview_frames_route(
    job_id: str,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PreviewFrameListResponse:
    return list_preview_frames(db=db, job_id=job_id, limit=limit, offset=offset)
