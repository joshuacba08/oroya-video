from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RealESRGANJobSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    model_slug: str | None
    model_path: str | None
    device: str | None
    scale: int | None
    tile_size: int | None
    tile_pad: int | None
    pre_pad: int | None
    half_precision: bool | None
    frames_total: int | None
    frames_processed: int
    failed_frames: int
    average_frame_time_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None


class RealESRGANJobValidationResponse(BaseModel):
    job_id: str
    ready: bool
    model_slug: str | None
    model_installed: bool
    input_frames_available: bool
    device: str | None
    estimated_vram_mb: int | None
    warnings: list[str]
