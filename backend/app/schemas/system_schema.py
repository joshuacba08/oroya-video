from pydantic import BaseModel


class OSInfo(BaseModel):
    system: str
    release: str
    version: str
    machine: str


class PythonInfo(BaseModel):
    version: str
    implementation: str


class MemoryInfo(BaseModel):
    total_gb: float
    available_gb: float
    used_percent: float


class SystemInfoResponse(BaseModel):
    app_name: str
    app_version: str
    environment: str
    os: OSInfo
    python: PythonInfo
    memory: MemoryInfo


class ToolInfo(BaseModel):
    available: bool
    path: str | None = None
    version: str | None = None


class ToolsResponse(BaseModel):
    ffmpeg: ToolInfo
    ffprobe: ToolInfo
    nvidia_smi: ToolInfo


class GPUInfo(BaseModel):
    name: str
    driver_version: str | None = None
    memory_total_mb: int | None = None
    memory_used_mb: int | None = None
    memory_free_mb: int | None = None
    utilization_percent: int | None = None
    temperature_celsius: int | None = None


class GPUResponse(BaseModel):
    available: bool
    provider: str | None = None
    gpus: list[GPUInfo]


class FFmpegDownloadStartResponse(BaseModel):
    status: str
    already_installed: bool


class FFmpegDownloadProgressResponse(BaseModel):
    status: str
    bytes_done: int
    bytes_total: int | None
    percent: float
    error_code: str | None
    error_message: str | None


class AIInstallStartResponse(BaseModel):
    status: str
    already_installed: bool


class AIInstallProgressResponse(BaseModel):
    status: str
    step: int
    steps_total: int
    step_label: str
    percent: float
    message: str
    error_code: str | None
    error_message: str | None
    output_tail: list[str]


class StoragePaths(BaseModel):
    db: str
    temp: str
    exports: str
    models: str
    logs: str


class DiskInfo(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    used_percent: float


class StorageResponse(BaseModel):
    storage_path: str
    paths: StoragePaths
    disk: DiskInfo


class RequirementsMinimum(BaseModel):
    ffmpeg: bool
    ffprobe: bool
    storage_writable: bool


class RequirementsRecommended(BaseModel):
    nvidia_gpu: bool
    free_disk_space: bool


class RequirementsResponse(BaseModel):
    ready: bool
    minimum: RequirementsMinimum
    recommended: RequirementsRecommended
    warnings: list[str]
