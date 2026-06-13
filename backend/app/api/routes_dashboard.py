from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.hardening_schema import QueueResponse
from app.schemas.settings_schema import AppStateResponse, BootstrapResponse, DashboardResponse
from app.services.dashboard_service import (
    get_app_state_response,
    get_bootstrap_response,
    get_dashboard_response,
    get_queue_response,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/bootstrap", response_model=BootstrapResponse, summary="Get frontend bootstrap data")
async def get_bootstrap_route(request: Request, db: DbSession) -> BootstrapResponse:
    return get_bootstrap_response(db=db, settings=request.app.state.settings)


@router.get("/dashboard", response_model=DashboardResponse, summary="Get dashboard summary")
async def get_dashboard_route(request: Request, db: DbSession) -> DashboardResponse:
    return get_dashboard_response(db=db, settings=request.app.state.settings)


@router.get("/app-state", response_model=AppStateResponse, summary="Get global app state")
async def get_app_state_route(request: Request, db: DbSession) -> AppStateResponse:
    return get_app_state_response(db=db, settings=request.app.state.settings)


@router.get("/queue", response_model=QueueResponse, summary="Get processing queue overview")
async def get_queue_route(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> QueueResponse:
    return get_queue_response(db=db, limit=limit, offset=offset)
