from fastapi import APIRouter, Request

from app.schemas.health_schema import HealthFullResponse, HealthResponse, VersionResponse
from app.services.system_service import (
    get_health_full_response,
    get_health_response,
    get_version_response,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Backend health check")
async def health_check(request: Request) -> HealthResponse:
    return get_health_response(request.app.state.settings)


@router.get(
    "/health/full",
    response_model=HealthFullResponse,
    summary="Backend health check with subsystem details",
)
async def health_full_check(request: Request) -> HealthFullResponse:
    return get_health_full_response(request.app.state.settings)


@router.get("/version", response_model=VersionResponse, summary="Backend version info")
async def version(request: Request) -> VersionResponse:
    return get_version_response(request.app.state.settings)
