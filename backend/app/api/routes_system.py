import secrets
import threading
import time
from collections import deque
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.core.errors import ShutdownForbiddenError, ShutdownNotAvailableError
from app.core.logging import get_logger
from app.core.parent_watchdog import request_shutdown_in_background
from app.core.paths import get_exports_path, get_logs_path, get_models_path, get_temp_path
from app.db.database import get_db
from app.schemas.hardening_schema import (
    CleanupBatchRequest,
    CleanupBatchResponse,
    StorageUsageResponse,
)
from app.schemas.system_schema import (
    AIInstallProgressResponse,
    AIInstallStartResponse,
    ClientLogRequest,
    DiagnosticsResponse,
    FFmpegDownloadProgressResponse,
    FFmpegDownloadStartResponse,
    GPUResponse,
    RequirementsResponse,
    ShutdownResponse,
    StorageOpenResponse,
    StorageResponse,
    SystemInfoResponse,
    ToolsResponse,
)
from app.services import desktop_open_service
from app.services.ai_install_service import get_ai_install_progress, start_ai_install
from app.services.cleanup_service import cleanup_old_temp_files, get_storage_usage
from app.services.diagnostics_service import create_diagnostics_bundle
from app.services.gpu_detection_service import get_gpu_status
from app.services.system_service import get_requirements_status, get_storage_info, get_system_info
from app.services.system_setup_service import (
    get_ffmpeg_download_progress,
    start_ffmpeg_download,
)
from app.services.tool_detection_service import get_tools_status

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
logger = get_logger(__name__)
frontend_logger = get_logger("frontend")

# Un bucle de errores en la UI no debe llenar el log: como mucho 30 por minuto.
CLIENT_LOG_LIMIT = 30
CLIENT_LOG_WINDOW_SECONDS = 60
_client_log_times: deque[float] = deque()
_client_log_lock = threading.Lock()


def _client_log_allowed() -> bool:
    now = time.monotonic()
    with _client_log_lock:
        while _client_log_times and now - _client_log_times[0] > CLIENT_LOG_WINDOW_SECONDS:
            _client_log_times.popleft()
        if len(_client_log_times) >= CLIENT_LOG_LIMIT:
            return False
        _client_log_times.append(now)
        return True


@router.post(
    "/shutdown",
    response_model=ShutdownResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Graceful shutdown requested by the desktop app",
)
def shutdown_route(
    request: Request,
    x_oroya_instance: Annotated[str | None, Header()] = None,
) -> ShutdownResponse:
    expected = request.app.state.settings.oroya_instance_id
    if not expected:
        raise ShutdownNotAvailableError()
    if not secrets.compare_digest(x_oroya_instance or "", expected):
        raise ShutdownForbiddenError()
    # Apagado ordenado: el worker pausa la mejora en curso y termina ffmpeg antes de salir.
    request_shutdown_in_background()
    return ShutdownResponse(accepted=True)


@router.post(
    "/diagnostics",
    response_model=DiagnosticsResponse,
    summary="Create a diagnostic zip (logs, system state, recent jobs) and reveal it",
)
def diagnostics_route(request: Request, db: DbSession) -> DiagnosticsResponse:
    bundle = create_diagnostics_bundle(db, request.app.state.settings)
    opened = desktop_open_service.reveal_in_folder(bundle)
    return DiagnosticsResponse(
        file_name=bundle.name,
        path=str(bundle),
        size_bytes=bundle.stat().st_size,
        opened=opened,
    )


@router.post(
    "/client-log",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record an error reported by the UI in backend.log",
)
def client_log_route(payload: ClientLogRequest) -> None:
    if not _client_log_allowed():
        return
    log = frontend_logger.error if payload.level == "error" else frontend_logger.warning
    log(
        "UI %s: %s%s%s",
        payload.level,
        payload.message,
        f" (at {payload.url})" if payload.url else "",
        f"\n{payload.stack}" if payload.stack else "",
    )


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


@router.post(
    "/storage/open",
    response_model=StorageOpenResponse,
    summary="Open a storage folder (temp, models, exports or logs) in the file explorer",
)
def storage_open_route(
    request: Request,
    target: Literal["temp", "models", "exports", "logs"] = Query(...),
) -> StorageOpenResponse:
    settings = request.app.state.settings
    resolvers = {
        "temp": get_temp_path,
        "models": get_models_path,
        "exports": get_exports_path,
        "logs": get_logs_path,
    }
    folder = resolvers[target](settings)
    folder.mkdir(parents=True, exist_ok=True)
    opened = desktop_open_service.reveal_in_folder(folder)
    return StorageOpenResponse(target=target, path=str(folder), opened=opened)


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
