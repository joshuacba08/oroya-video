from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.ai_model_schema import (
    AIModelCreateRequest,
    AIModelListResponse,
    AIModelRefreshResponse,
    AIModelResponse,
    AIModelUpdateRequest,
)
from app.services.ai_model_service import (
    create_model,
    delete_model,
    get_model,
    list_models,
    refresh_models,
    set_model_enabled_state,
    update_model,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=AIModelListResponse, summary="List AI models")
async def list_models_route(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    category: str | None = None,
    status: str | None = None,
    installed: bool | None = None,
    enabled: bool | None = None,
) -> AIModelListResponse:
    return list_models(
        db=db,
        limit=limit,
        offset=offset,
        category=category,
        status=status,
        installed=installed,
        enabled=enabled,
    )


@router.post(
    "",
    response_model=AIModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a custom AI model",
)
async def create_model_route(
    payload: AIModelCreateRequest,
    request: Request,
    db: DbSession,
) -> AIModelResponse:
    return create_model(db=db, request=payload, settings=request.app.state.settings)


@router.post("/refresh", response_model=AIModelRefreshResponse, summary="Refresh AI model states")
async def refresh_models_route(request: Request, db: DbSession) -> AIModelRefreshResponse:
    return refresh_models(db=db, settings=request.app.state.settings)


@router.get(
    "/{model_id_or_slug}",
    response_model=AIModelResponse,
    summary="Get an AI model by id or slug",
)
async def get_model_route(model_id_or_slug: str, db: DbSession) -> AIModelResponse:
    return get_model(db=db, model_id_or_slug=model_id_or_slug)


@router.patch(
    "/{model_id_or_slug}",
    response_model=AIModelResponse,
    summary="Update AI model metadata",
)
async def update_model_route(
    model_id_or_slug: str,
    payload: AIModelUpdateRequest,
    request: Request,
    db: DbSession,
) -> AIModelResponse:
    return update_model(
        db=db,
        model_id_or_slug=model_id_or_slug,
        request=payload,
        settings=request.app.state.settings,
    )


@router.post(
    "/{model_id_or_slug}/enable",
    response_model=AIModelResponse,
    summary="Enable an AI model",
)
async def enable_model_route(
    model_id_or_slug: str,
    request: Request,
    db: DbSession,
) -> AIModelResponse:
    return set_model_enabled_state(
        db=db,
        model_id_or_slug=model_id_or_slug,
        enabled=True,
        settings=request.app.state.settings,
    )


@router.post(
    "/{model_id_or_slug}/disable",
    response_model=AIModelResponse,
    summary="Disable an AI model",
)
async def disable_model_route(
    model_id_or_slug: str,
    request: Request,
    db: DbSession,
) -> AIModelResponse:
    return set_model_enabled_state(
        db=db,
        model_id_or_slug=model_id_or_slug,
        enabled=False,
        settings=request.app.state.settings,
    )


@router.delete("/{model_id_or_slug}", summary="Delete a custom AI model")
async def delete_model_route(model_id_or_slug: str, db: DbSession) -> dict[str, object]:
    return delete_model(db=db, model_id_or_slug=model_id_or_slug)
