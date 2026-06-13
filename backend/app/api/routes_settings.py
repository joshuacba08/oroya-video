from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.settings_schema import (
    SettingsResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
)
from app.services.settings_service import build_settings_response, update_settings

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=SettingsResponse, summary="Get backend settings")
async def get_settings_route(request: Request) -> SettingsResponse:
    return build_settings_response(request.app.state.settings)


@router.patch("", response_model=SettingsUpdateResponse, summary="Update backend settings")
async def patch_settings_route(
    payload: SettingsUpdateRequest,
    request: Request,
    db: DbSession,
) -> SettingsUpdateResponse:
    return update_settings(db, payload, request.app.state.settings)
