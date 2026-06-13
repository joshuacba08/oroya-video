from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.export_schema import (
    ExportAssetResponse,
    ExportDeleteResponse,
    ExportListResponse,
    ExportOpenResponse,
)
from app.services.export_service import (
    build_export_open_response,
    delete_export,
    get_export_by_id,
    list_exports,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=ExportListResponse, summary="List exports")
async def list_exports_route(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project_id: str | None = None,
    job_id: str | None = None,
) -> ExportListResponse:
    return list_exports(
        db=db,
        limit=limit,
        offset=offset,
        project_id=project_id,
        job_id=job_id,
    )


@router.get(
    "/{export_id}",
    response_model=ExportAssetResponse,
    summary="Get export detail",
)
async def get_export_route(export_id: str, db: DbSession) -> ExportAssetResponse:
    return get_export_by_id(db=db, export_id=export_id)


@router.delete(
    "/{export_id}",
    response_model=ExportDeleteResponse,
    summary="Delete export",
)
async def delete_export_route(
    export_id: str,
    db: DbSession,
    delete_file: bool = Query(default=False),
) -> ExportDeleteResponse:
    return delete_export(db=db, export_id=export_id, delete_file=delete_file)


@router.post(
    "/{export_id}/open",
    response_model=ExportOpenResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate export file for desktop open",
)
async def open_export_route(
    export_id: str,
    request: Request,
    db: DbSession,
) -> ExportOpenResponse:
    return build_export_open_response(
        db=db,
        export_id=export_id,
        open_folder=False,
        settings=request.app.state.settings,
    )


@router.post(
    "/{export_id}/open-folder",
    response_model=ExportOpenResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate export folder for desktop open",
)
async def open_export_folder_route(
    export_id: str,
    request: Request,
    db: DbSession,
) -> ExportOpenResponse:
    return build_export_open_response(
        db=db,
        export_id=export_id,
        open_folder=True,
        settings=request.app.state.settings,
    )
