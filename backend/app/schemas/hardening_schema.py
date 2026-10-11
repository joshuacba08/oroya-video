from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.job_schema import JobActions


class JobPreflightResponse(BaseModel):
    job_id: str
    ready: bool
    checks: dict[str, bool]
    warnings: list[str]
    errors: list[str]


class JobRetryRequest(BaseModel):
    cleanup_before_retry: bool = True
    reset_progress: bool = True
    # True: tras preparar el reintento, pasa el preflight y encola el job (como /start).
    start: bool = False


class CleanupResponse(BaseModel):
    deleted: bool
    job_id: str
    freed_bytes: int
    deleted_paths: list[str]
    warnings: list[str]


class CleanupBatchRequest(BaseModel):
    # None: usa `cleanup_temp_older_than_hours` de la configuración.
    older_than_hours: int | None = Field(default=None, ge=0)
    dry_run: bool = False


class CleanupBatchItem(BaseModel):
    job_id: str
    freed_bytes: int
    deleted_paths: list[str]


class CleanupBatchResponse(BaseModel):
    dry_run: bool
    deleted: bool
    jobs_scanned: int
    jobs_cleaned: int
    freed_bytes: int
    items: list[CleanupBatchItem]
    warnings: list[str]


class StorageUsageResponse(BaseModel):
    storage_path: str
    total_bytes: int
    free_bytes: int
    used_by_oroya_bytes: int
    breakdown: dict[str, int]


class JobPipelineStage(BaseModel):
    name: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None


class JobPipelineResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    progress_percent: float
    stages: list[JobPipelineStage]
    output: dict[str, Any]


class JobDiagnosticsResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    error_code: str | None
    error_message: str | None
    likely_causes: list[str]
    suggested_actions: list[str]
    can_retry: bool
    can_cleanup: bool
    related_logs_url: str


class QueueItemResponse(BaseModel):
    job_id: str
    project_id: str
    project_name: str | None
    status: str
    current_stage: str
    progress_percent: float
    model_slug: str | None
    created_at: datetime
    started_at: datetime | None
    frames_total: int = 0
    frames_processed: int = 0
    elapsed_time_seconds: int = 0
    error_code: str | None = None
    error_message: str | None = None
    enhancer_engine: str | None = None
    realesrgan_device: str | None = None
    realesrgan_frames_total: int | None = None
    realesrgan_frames_processed: int | None = None
    realesrgan_failed_frames: int | None = None
    realesrgan_average_frame_time_ms: int | None = None
    retry_count: int = 0
    max_retries: int = 0
    actions: JobActions


class QueueResponse(BaseModel):
    items: list[QueueItemResponse]
    total: int
    running: int
    queued: int
    pending: int
    interrupted: int
    paused: int = 0
    failed: int = 0
    limit: int = Field(default=50)
    offset: int = Field(default=0)
