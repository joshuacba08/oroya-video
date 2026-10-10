from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.ai_runtime_schema import (
    AIModelValidationResponse,
    AIRuntimeStatusResponse,
    RealESRGANDryRunRequest,
    RealESRGANDryRunResponse,
)
from app.services.ai_runtime_service import get_ai_runtime_status
from app.services.realesrgan_service import run_realesrgan_dry_run, validate_realesrgan_model

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/runtime", response_model=AIRuntimeStatusResponse, summary="Get AI runtime status")
def get_ai_runtime_route(request: Request) -> AIRuntimeStatusResponse:
    return get_ai_runtime_status(request.app.state.settings)


@router.get(
    "/models/{model_slug}/validate",
    response_model=AIModelValidationResponse,
    summary="Validate a Real-ESRGAN model",
)
def validate_realesrgan_model_route(
    model_slug: str,
    request: Request,
    db: DbSession,
) -> AIModelValidationResponse:
    return validate_realesrgan_model(
        db=db,
        model_slug=model_slug,
        settings=request.app.state.settings,
    )


@router.post(
    "/realesrgan/dry-run",
    response_model=RealESRGANDryRunResponse,
    summary="Run a Real-ESRGAN dry-run on a single frame",
)
def run_realesrgan_dry_run_route(
    payload: RealESRGANDryRunRequest,
    request: Request,
    db: DbSession,
) -> RealESRGANDryRunResponse:
    return run_realesrgan_dry_run(db=db, request=payload, settings=request.app.state.settings)
