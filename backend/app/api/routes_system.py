from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.hardening_schema import (
    CleanupBatchRequest,
    CleanupBatchResponse,
    StorageUsageResponse,
)
from app.schemas.system_schema import (
    GPUResponse,
    RequirementsResponse,
    StorageResponse,
    SystemInfoResponse,
    ToolsResponse,
)
from app.services.cleanup_service import cleanup_old_temp_files, get_storage_usage
from app.services.gpu_detection_service import get_gpu_status
from app.services.system_service import get_requirements_status, get_storage_info, get_system_info
from app.services.tool_detection_service import get_tools_status

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/info", response_model=SystemInfoResponse, summary="System environment info")
async def system_info(request: Request) -> SystemInfoResponse:
    return get_system_info(request.app.state.settings)


@router.get("/tools", response_model=ToolsResponse, summary="Detected system tools")
async def system_tools() -> ToolsResponse:
    return get_tools_status()


@router.get("/gpu", response_model=GPUResponse, summary="Detected GPU status")
async def system_gpu() -> GPUResponse:
    return get_gpu_status()


@router.get("/storage", response_model=StorageResponse, summary="Storage paths and disk usage")
async def system_storage(request: Request) -> StorageResponse:
    return get_storage_info(request.app.state.settings)


@router.get(
    "/requirements",
    response_model=RequirementsResponse,
    summary="Readiness summary for future processing features",
)
async def system_requirements(request: Request) -> RequirementsResponse:
    return get_requirements_status(request.app.state.settings)


@router.get(
    "/storage/usage",
    response_model=StorageUsageResponse,
    summary="Detailed Oroya storage usage",
)
async def system_storage_usage(request: Request) -> StorageUsageResponse:
    return StorageUsageResponse(**get_storage_usage(request.app.state.settings))


@router.post(
    "/cleanup/temp",
    response_model=CleanupBatchResponse,
    summary="Cleanup old Oroya temporary files",
)
async def cleanup_temp_route(
    payload: CleanupBatchRequest,
    request: Request,
    db: DbSession,
) -> CleanupBatchResponse:
    return cleanup_old_temp_files(
        db,
        older_than_hours=payload.older_than_hours,
        dry_run=payload.dry_run,
        settings=request.app.state.settings,
    )
