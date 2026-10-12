from __future__ import annotations

from pydantic import BaseModel


class GeneralSettingsResponse(BaseModel):
    language: str
    theme: str


class ProcessingSettingsResponse(BaseModel):
    frame_enhancer_engine: str
    ai_device: str
    ai_allow_cpu: bool
    ai_half_precision: bool
    realesrgan_tile_size: int
    realesrgan_tile_pad: int
    realesrgan_pre_pad: int


class StorageSettingsResponse(BaseModel):
    storage_path: str
    temp_path: str
    exports_path: str
    models_path: str


class CleanupSettingsResponse(BaseModel):
    cleanup_temp_on_success: bool
    cleanup_keep_preview_frames: int
    cleanup_temp_older_than_hours: int


class SettingsResponse(BaseModel):
    general: GeneralSettingsResponse
    processing: ProcessingSettingsResponse
    storage: StorageSettingsResponse
    cleanup: CleanupSettingsResponse


class GeneralSettingsPatch(BaseModel):
    language: str | None = None
    theme: str | None = None


class ProcessingSettingsPatch(BaseModel):
    frame_enhancer_engine: str | None = None
    ai_device: str | None = None
    ai_allow_cpu: bool | None = None
    ai_half_precision: bool | None = None
    realesrgan_tile_size: int | None = None
    realesrgan_tile_pad: int | None = None
    realesrgan_pre_pad: int | None = None


class CleanupSettingsPatch(BaseModel):
    cleanup_temp_on_success: bool | None = None
    cleanup_keep_preview_frames: int | None = None
    cleanup_temp_older_than_hours: int | None = None


class StorageSettingsPatch(BaseModel):
    exports_dir: str | None = None


class SettingsUpdateRequest(BaseModel):
    general: GeneralSettingsPatch | None = None
    processing: ProcessingSettingsPatch | None = None
    cleanup: CleanupSettingsPatch | None = None
    storage: StorageSettingsPatch | None = None


class SettingsUpdateResponse(BaseModel):
    updated: bool
    settings: SettingsResponse


class BootstrapAppResponse(BaseModel):
    name: str
    version: str
    api_version: str
    environment: str


class BootstrapSystemResponse(BaseModel):
    ffmpeg_available: bool
    ffprobe_available: bool
    gpu_available: bool
    ai_runtime_available: bool


class BootstrapCountsResponse(BaseModel):
    projects: int
    videos: int
    jobs_running: int
    jobs_interrupted: int
    exports: int
    models_installed: int


class BootstrapResponse(BaseModel):
    app: BootstrapAppResponse
    system: BootstrapSystemResponse
    settings: dict[str, str | bool | int]
    counts: BootstrapCountsResponse
    warnings: list[str]


class DashboardSystemStatusResponse(BaseModel):
    ready: bool
    warnings: list[str]


class DashboardStorageResponse(BaseModel):
    free_bytes: int
    used_by_oroya_bytes: int


class DashboardModelsResponse(BaseModel):
    installed: int
    missing: int
    enabled: int


class DashboardResponse(BaseModel):
    recent_projects: list[dict]
    recent_exports: list[dict]
    active_jobs: list[dict]
    interrupted_jobs: list[dict]
    system_status: DashboardSystemStatusResponse
    storage: DashboardStorageResponse
    models: DashboardModelsResponse


class AppStateBackendResponse(BaseModel):
    online: bool
    version: str
    api_version: str


class AppStateQueueResponse(BaseModel):
    running: int
    queued: int
    pending: int
    interrupted: int


class AppStateSystemResponse(BaseModel):
    ready: bool
    gpu_available: bool
    ai_runtime_available: bool


class AppStateStorageResponse(BaseModel):
    free_bytes: int
    temp_bytes: int


class AppStateResponse(BaseModel):
    backend: AppStateBackendResponse
    queue: AppStateQueueResponse
    system: AppStateSystemResponse
    storage: AppStateStorageResponse
