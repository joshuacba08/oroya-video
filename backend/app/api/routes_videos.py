from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.video_schema import (
    VideoAssetResponse,
    VideoDeleteResponse,
    VideoImportRequest,
    VideoImportResponse,
    VideoListResponse,
    VideoProbeRequest,
    VideoProbeResponse,
)
from app.services.video_import_service import (
    delete_video_asset,
    get_video_asset,
    import_video_asset,
    list_video_assets,
)
from app.services.video_probe_service import probe_video

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/probe", response_model=VideoProbeResponse, summary="Analyze local video metadata")
def probe_video_file(payload: VideoProbeRequest) -> VideoProbeResponse:
    return probe_video(payload)


@router.post(
    "/import",
    response_model=VideoImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import or register a local video asset",
)
def import_video_file(
    payload: VideoImportRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> VideoImportResponse:
    result = import_video_asset(
        db=db,
        file_path=payload.file_path,
        source_mode=payload.source_mode,
        settings=request.app.state.settings,
    )
    if result.already_imported:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("", response_model=VideoListResponse, summary="List imported video assets")
def get_videos(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> VideoListResponse:
    return list_video_assets(db=db, limit=limit, offset=offset)


@router.get("/{video_id}", response_model=VideoAssetResponse, summary="Get imported video asset")
def get_video(video_id: str, db: DbSession) -> VideoAssetResponse:
    return get_video_asset(db=db, video_id=video_id)


@router.delete(
    "/{video_id}",
    response_model=VideoDeleteResponse,
    summary="Delete imported video asset",
)
def delete_video(
    video_id: str,
    request: Request,
    db: DbSession,
) -> VideoDeleteResponse:
    return delete_video_asset(db=db, video_id=video_id, settings=request.app.state.settings)
