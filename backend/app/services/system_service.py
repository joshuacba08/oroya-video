import platform
import shutil

import psutil
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import (
    ensure_storage_directories,
    get_storage_path,
    get_storage_path_strings,
    is_storage_writable,
)
from app.db import database
from app.schemas.health_schema import (
    HealthFullAIResponse,
    HealthFullDatabaseResponse,
    HealthFullQueueResponse,
    HealthFullResponse,
    HealthFullStorageResponse,
    HealthFullToolsResponse,
    HealthResponse,
    VersionResponse,
)
from app.schemas.system_schema import (
    DiskInfo,
    MemoryInfo,
    OSInfo,
    PythonInfo,
    RequirementsMinimum,
    RequirementsRecommended,
    RequirementsResponse,
    StoragePaths,
    StorageResponse,
    SystemInfoResponse,
)
from app.services.ai_runtime_service import get_ai_runtime_status
from app.services.cleanup_service import get_storage_usage
from app.services.gpu_detection_service import get_gpu_status
from app.services.tool_detection_service import get_tools_status
from app.workers.job_runner import is_job_worker_running

logger = get_logger(__name__)
BYTES_IN_GB = 1024**3
RECOMMENDED_FREE_DISK_GB = 10.0


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _bytes_to_gb(value: int) -> float:
    return round(value / BYTES_IN_GB, 1)


def get_health_response(settings: Settings | None = None) -> HealthResponse:
    active_settings = _get_active_settings(settings)
    return HealthResponse(
        status="ok",
        service=active_settings.app_name,
        version=active_settings.app_version,
        instance_id=active_settings.oroya_instance_id,
    )


def get_version_response(settings: Settings | None = None) -> VersionResponse:
    active_settings = _get_active_settings(settings)
    return VersionResponse(
        name=active_settings.app_name,
        version=active_settings.app_version,
        environment=active_settings.environment,
    )


def get_system_info(settings: Settings | None = None) -> SystemInfoResponse:
    active_settings = _get_active_settings(settings)
    os_info = platform.uname()
    memory = psutil.virtual_memory()

    response = SystemInfoResponse(
        app_name=active_settings.app_name,
        app_version=active_settings.app_version,
        environment=active_settings.environment,
        os=OSInfo(
            system=os_info.system,
            release=os_info.release,
            version=os_info.version,
            machine=os_info.machine,
        ),
        python=PythonInfo(
            version=platform.python_version(),
            implementation=platform.python_implementation(),
        ),
        memory=MemoryInfo(
            total_gb=_bytes_to_gb(memory.total),
            available_gb=_bytes_to_gb(memory.available),
            used_percent=round(memory.percent, 1),
        ),
    )
    logger.info("System info requested")
    return response


def get_storage_info(settings: Settings | None = None) -> StorageResponse:
    active_settings = _get_active_settings(settings)
    ensure_storage_directories(active_settings)
    storage_path = get_storage_path(active_settings)
    storage_strings = get_storage_path_strings(active_settings)
    total_bytes, used_bytes, free_bytes = shutil.disk_usage(storage_path)

    response = StorageResponse(
        storage_path=storage_strings["storage"],
        paths=StoragePaths(
            db=storage_strings["db"],
            temp=storage_strings["temp"],
            exports=storage_strings["exports"],
            models=storage_strings["models"],
            logs=storage_strings["logs"],
        ),
        disk=DiskInfo(
            total_gb=_bytes_to_gb(total_bytes),
            used_gb=_bytes_to_gb(used_bytes),
            free_gb=_bytes_to_gb(free_bytes),
            used_percent=round((used_bytes / total_bytes) * 100, 1) if total_bytes else 0.0,
        ),
    )
    logger.info("Storage info requested")
    return response


def get_requirements_status(settings: Settings | None = None) -> RequirementsResponse:
    active_settings = _get_active_settings(settings)
    tools_status = get_tools_status()
    gpu_status = get_gpu_status()
    storage_status = get_storage_info(active_settings)
    storage_writable = is_storage_writable(active_settings)
    free_disk_space_ok = storage_status.disk.free_gb > RECOMMENDED_FREE_DISK_GB

    minimum = RequirementsMinimum(
        ffmpeg=tools_status.ffmpeg.available,
        ffprobe=tools_status.ffprobe.available,
        storage_writable=storage_writable,
    )
    recommended = RequirementsRecommended(
        nvidia_gpu=gpu_status.available,
        free_disk_space=free_disk_space_ok,
    )

    warnings: list[str] = []
    if not minimum.ffmpeg:
        logger.warning("FFmpeg not detected")
        warnings.append("FFmpeg was not detected. Video processing will not be available.")
    if not minimum.ffprobe:
        logger.warning("FFprobe not detected")
        warnings.append("FFprobe was not detected. Video metadata analysis will not be available.")
    if not minimum.storage_writable:
        logger.warning("Storage path is not writable")
        warnings.append("Storage path is not writable. Oroya Video cannot persist data safely.")
    if not recommended.nvidia_gpu:
        logger.warning("NVIDIA GPU not detected")
        warnings.append(
            "NVIDIA GPU was not detected. Processing may be very slow in future AI tasks."
        )
    if not recommended.free_disk_space:
        logger.warning("Free disk space is below recommended threshold")
        warnings.append("Free disk space is below recommended threshold for future jobs.")
    from app.services import settings_service

    if settings_service.corrupt_settings_backup is not None:
        warnings.append(
            "Saved settings were unreadable and were reset to defaults "
            f"(copy kept at {settings_service.corrupt_settings_backup.name})."
        )

    response = RequirementsResponse(
        ready=all(minimum.model_dump().values()),
        minimum=minimum,
        recommended=recommended,
        warnings=warnings,
    )
    logger.debug("Requirements status calculated")
    return response


def _is_database_connected() -> bool:
    if database.engine is None:
        return False
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Database health check failed.")
        return False
    return True


def get_health_full_response(settings: Settings | None = None) -> HealthFullResponse:
    active_settings = _get_active_settings(settings)
    tools_status = get_tools_status()
    ai_runtime = get_ai_runtime_status(active_settings)
    storage_usage = get_storage_usage(active_settings)
    warnings = get_requirements_status(active_settings).warnings
    return HealthFullResponse(
        status="ok",
        service=active_settings.app_name,
        version=active_settings.app_version,
        database=HealthFullDatabaseResponse(connected=_is_database_connected()),
        storage=HealthFullStorageResponse(
            writable=is_storage_writable(active_settings),
            free_bytes=int(storage_usage["free_bytes"]),
        ),
        tools=HealthFullToolsResponse(
            ffmpeg=tools_status.ffmpeg.available,
            ffprobe=tools_status.ffprobe.available,
        ),
        ai=HealthFullAIResponse(
            runtime_available=ai_runtime.available,
            engine=active_settings.frame_enhancer_engine,
        ),
        queue=HealthFullQueueResponse(worker_running=is_job_worker_running()),
        warnings=warnings,
    )
