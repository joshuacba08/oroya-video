from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.hardening_schema import (
    CleanupBatchRequest,
    CleanupBatchResponse,
    StorageUsageResponse,
)
from app.schemas.system_schema import (
    AIInstallProgressResponse,
    AIInstallStartResponse,
    FFmpegDownloadProgressResponse,
    FFmpegDownloadStartResponse,
    GPUResponse,
    RequirementsResponse,
    StorageResponse,
    SystemInfoResponse,
    ToolsResponse,
)
from app.services.ai_install_service import get_ai_install_progress, start_ai_install
from app.services.cleanup_service import cleanup_old_temp_files, get_storage_usage
from app.services.gpu_detection_service import get_gpu_status
from app.services.system_service import get_requirements_status, get_storage_info, get_system_info
from app.services.system_setup_service import (
    get_ffmpeg_download_progress,
    start_ffmpeg_download,
)
from app.services.tool_detection_service import get_tools_status

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/info", response_model=SystemInfoResponse, summary="System environment info")
def system_info(request: Request) -> SystemInfoResponse:
    return get_system_info(request.app.state.settings)


@router.get("/tools", response_model=ToolsResponse, summary="Detected system tools")
def system_tools() -> ToolsResponse:
    return get_tools_status()


@router.get("/gpu", response_model=GPUResponse, summary="Detected GPU status")
def system_gpu() -> GPUResponse:
    return get_gpu_status()


@router.post(
    "/ffmpeg/download",
    response_model=FFmpegDownloadStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Download FFmpeg into the app data directory",
)
def ffmpeg_download_route(request: Request) -> FFmpegDownloadStartResponse:
    return start_ffmpeg_download(request.app.state.settings)


@router.get(
    "/ffmpeg/download/progress",
    response_model=FFmpegDownloadProgressResponse,
    summary="Get FFmpeg download progress",
)
def ffmpeg_download_progress_route(request: Request) -> FFmpegDownloadProgressResponse:
    return get_ffmpeg_download_progress(request.app.state.settings)


@router.post(
    "/ai/install",
    response_model=AIInstallStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Install the AI runtime (PyTorch + Real-ESRGAN) in the background",
)
def ai_install_route(request: Request) -> AIInstallStartResponse:
    return start_ai_install(request.app.state.settings)


@router.get(
    "/ai/install/progress",
    response_model=AIInstallProgressResponse,
    summary="Get AI runtime install progress",
)
def ai_install_progress_route() -> AIInstallProgressResponse:
    return get_ai_install_progress()


@router.get("/storage", response_model=StorageResponse, summary="Storage paths and disk usage")
def system_storage(request: Request) -> StorageResponse:
    return get_storage_info(request.app.state.settings)


@router.get(
    "/requirements",
    response_model=RequirementsResponse,
    summary="Readiness summary for future processing features",
)
def system_requirements(request: Request) -> RequirementsResponse:
    return get_requirements_status(request.app.state.settings)


@router.get(
    "/storage/usage",
    response_model=StorageUsageResponse,
    summary="Detailed Oroya storage usage",
)
def system_storage_usage(request: Request) -> StorageUsageResponse:
    return StorageUsageResponse(**get_storage_usage(request.app.state.settings))


@router.post(
    "/cleanup/temp",
    response_model=CleanupBatchResponse,
    summary="Cleanup old Oroya temporary files",
)
def cleanup_temp_route(
    payload: CleanupBatchRequest,
    request: Request,
    db: DbSession,
) -> CleanupBatchResponse:
    settings = request.app.state.settings
    older_than_hours = payload.older_than_hours
    if older_than_hours is None:
        older_than_hours = settings.cleanup_temp_older_than_hours
    return cleanup_old_temp_files(
        db,
        older_than_hours=older_than_hours,
        dry_run=payload.dry_run,
        settings=request.app.state.settings,
    )
