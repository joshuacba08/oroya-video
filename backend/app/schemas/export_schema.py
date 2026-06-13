from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ExportAssetResponse(BaseModel):
    id: str
    project_id: str
    job_id: str
    video_asset_id: str
    file_path: str
    file_name: str
    file_extension: str
    file_size_bytes: int
    file_size_mb: float
    format: str
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    audio_strategy: str | None
    resolution_label: str | None
    width: int | None
    height: int | None
    fps: float | None
    duration_seconds: float | None
    duration_label: str | None
    created_at: datetime
    updated_at: datetime


class ExportListResponse(BaseModel):
    items: list[ExportAssetResponse]
    total: int
    limit: int
    offset: int


class ExportDeleteResponse(BaseModel):
    deleted: bool
    export_id: str
    file_deleted: bool


class ExportOpenResponse(BaseModel):
    export_id: str
    path: str
    available: bool
    message: str
