from __future__ import annotations

from pydantic import BaseModel


class AICudaDeviceInfo(BaseModel):
    index: int
    name: str | None
    memory_total_mb: int | None = None


class AIRuntimeStatusResponse(BaseModel):
    available: bool
    torch_available: bool
    torch_version: str | None
    cuda_available: bool
    cuda_device_count: int
    cuda_devices: list[AICudaDeviceInfo]
    selected_device: str | None
    allow_cpu: bool
    half_precision: bool
    warnings: list[str]
    # Para que la UI genere el comando de instalación con el intérprete correcto.
    python_executable: str = ""
    python_version: str = ""
    ai_extra_site_dir: str | None = None


class AIModelValidationResponse(BaseModel):
    model_slug: str
    exists_in_registry: bool
    is_enabled: bool
    is_installed: bool
    file_path: str | None
    file_exists: bool
    file_size_bytes: int | None
    estimated_vram_mb: int | None
    runtime_available: bool
    can_run: bool
    device: str | None
    warnings: list[str]


class RealESRGANDryRunRequest(BaseModel):
    model_slug: str
    input_frame_path: str | None = None
    job_id: str | None = None
    frame_index: int | None = None


class RealESRGANDryRunResponse(BaseModel):
    success: bool
    model_slug: str
    engine: str
    device: str | None
    input_frame_path: str
    output_frame_path: str | None
    elapsed_time_ms: int | None
    message: str
    warnings: list[str]
