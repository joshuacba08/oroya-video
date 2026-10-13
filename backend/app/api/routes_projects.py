from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.project_schema import (
    ProjectCreateRequest,
    ProjectDeleteResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectUpdateRequest,
    ProjectWorkspaceResponse,
)
from app.services.project_service import (
    create_project,
    delete_project,
    get_project_detail,
    get_project_workspace,
    list_projects,
    update_project,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=ProjectDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project from an imported video",
)
def create_project_route(
    payload: ProjectCreateRequest,
    request: Request,
    db: DbSession,
) -> ProjectDetailResponse:
    return create_project(db, payload, request.app.state.settings)


@router.get("", response_model=ProjectListResponse, summary="List projects")
def list_projects_route(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    search: str | None = None,
) -> ProjectListResponse:
    return list_projects(db=db, limit=limit, offset=offset, status=status, search=search)


@router.get(
    "/{project_id}/workspace",
    response_model=ProjectWorkspaceResponse,
    summary="Get project workspace bootstrap data",
)
def get_project_workspace_route(
    project_id: str,
    request: Request,
    db: DbSession,
) -> ProjectWorkspaceResponse:
    return get_project_workspace(
        db=db,
        project_id=project_id,
        settings=request.app.state.settings,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Get a project with video details",
)
def get_project_route(project_id: str, db: DbSession) -> ProjectDetailResponse:
    return get_project_detail(db=db, project_id=project_id)


@router.patch(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Update project metadata and workspace state",
)
def update_project_route(
    project_id: str,
    payload: ProjectUpdateRequest,
    db: DbSession,
) -> ProjectDetailResponse:
    return update_project(db=db, project_id=project_id, request=payload)


@router.delete(
    "/{project_id}",
    response_model=ProjectDeleteResponse,
    summary="Delete a project",
)
def delete_project_route(
    project_id: str,
    request: Request,
    db: DbSession,
) -> ProjectDeleteResponse:
    return delete_project(db=db, project_id=project_id, settings=request.app.state.settings)
