from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.ai_model_schema import AIModelResponse
from app.schemas.project_schema import ProjectResponse
from app.schemas.video_schema import VideoAssetResponse


class JobCreateRequest(BaseModel):
    project_id: str
    model_id: str | None = None
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None


class JobBatchRequest(BaseModel):
    project_ids: list[str] = Field(min_length=1, max_length=200)
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None


class JobBatchSkipped(BaseModel):
    project_id: str
    error_code: str
    reason: str


class JobBatchResponse(BaseModel):
    queued_job_ids: list[str]
    skipped: list[JobBatchSkipped]


class JobActions(BaseModel):
    can_start: bool
    can_cancel: bool
    can_pause: bool
    can_retry: bool
    can_cleanup: bool
    can_delete: bool
    can_open_export: bool


class JobResponse(BaseModel):
    id: str
    project_id: str
    video_asset_id: str
    ai_model_id: str | None
    ai_model_slug: str
    status: str
    current_stage: str
    progress_percent: float
    frames_total: int | None
    frames_processed: int
    estimated_time_seconds: int | None
    elapsed_time_seconds: int | None
    enhancement_config: dict[str, Any]
    export_config: dict[str, Any]
    output_path: str | None
    error_code: str | None
    error_message: str | None
    working_dir: str | None
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
    frame_file_pattern: str | None
    frame_format: str | None
    extracted_frames: int
    enhancer_engine: str | None
    enhanced_frames: int
    extraction_started_at: datetime | None
    extraction_completed_at: datetime | None
    enhancement_started_at: datetime | None
    enhancement_completed_at: datetime | None
    enhancement_error_code: str | None
    enhancement_error_message: str | None
    encoded_dir: str | None
    encoded_video_path: str | None
    encoded_video_file_name: str | None
    encoded_video_size_bytes: int | None
    encoding_fps: float | None
    encoding_codec: str | None
    encoding_format: str | None
    encoding_started_at: datetime | None
    encoding_completed_at: datetime | None
    encoding_error_code: str | None
    encoding_error_message: str | None
    muxed_video_path: str | None
    muxed_video_file_name: str | None
    muxed_video_size_bytes: int | None
    audio_strategy: str | None
    audio_codec: str | None
    audio_mux_started_at: datetime | None
    audio_mux_completed_at: datetime | None
    audio_mux_error_code: str | None
    audio_mux_error_message: str | None
    export_id: str | None
    final_export_path: str | None
    final_export_file_name: str | None
    final_export_size_bytes: int | None
    export_started_at: datetime | None
    export_completed_at: datetime | None
    export_error_code: str | None
    export_error_message: str | None
    retry_count: int
    max_retries: int
    last_retry_at: datetime | None
    interrupted_at: datetime | None
    recovered_at: datetime | None
    cleanup_started_at: datetime | None
    cleanup_completed_at: datetime | None
    cleanup_error_code: str | None
    cleanup_error_message: str | None
    preflight_started_at: datetime | None
    preflight_completed_at: datetime | None
    preflight_error_code: str | None
    preflight_error_message: str | None
    last_known_stage: str | None
    last_known_progress_percent: float | None
    worker_id: str | None
    process_id: int | None
    process_kind: str | None
    process_started_at: datetime | None
    process_ended_at: datetime | None
    temp_size_bytes: int | None
    original_frames_size_bytes: int | None
    enhanced_frames_size_bytes: int | None
    encoded_size_bytes: int | None
    muxed_size_bytes: int | None
    exports_size_bytes: int | None
    realesrgan_model_slug: str | None
    realesrgan_model_path: str | None
    realesrgan_device: str | None
    realesrgan_scale: int | None
    realesrgan_tile_size: int | None
    realesrgan_tile_pad: int | None
    realesrgan_pre_pad: int | None
    realesrgan_half_precision: bool | None
    realesrgan_frames_total: int | None
    realesrgan_frames_processed: int
    realesrgan_failed_frames: int
    realesrgan_average_frame_time_ms: int | None
    realesrgan_started_at: datetime | None
    realesrgan_completed_at: datetime | None
    realesrgan_error_code: str | None
    realesrgan_error_message: str | None
    pause_requested: bool
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    actions: JobActions


class JobDetailResponse(BaseModel):
    job: JobResponse
    project: ProjectResponse
    video: VideoAssetResponse
    model: AIModelResponse | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int


class JobProgressResponse(BaseModel):
    job_id: str
    project_id: str
    status: str
    current_stage: str
    progress_percent: float
    stage_progress_percent: float
    stage_label: str
    frames_total: int | None
    frames_processed: int
    extracted_frames: int
    enhanced_frames: int
    estimated_time_seconds: int | None
    elapsed_time_seconds: int | None
    can_start: bool = False
    can_cancel: bool
    can_pause: bool
    can_retry: bool
    can_cleanup: bool
    preview_available: bool
    export_available: bool
    updated_at: datetime
    enhancer_engine: str | None
    working_dir: str | None
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
    enhancement_started_at: datetime | None
    enhancement_completed_at: datetime | None
    encoded_dir: str | None
    encoded_video_path: str | None
    encoded_video_size_bytes: int | None
    encoding_fps: float | None
    encoding_codec: str | None
    encoding_format: str | None
    encoding_started_at: datetime | None
    encoding_completed_at: datetime | None
    muxed_video_path: str | None
    muxed_video_file_name: str | None
    muxed_video_size_bytes: int | None
    audio_strategy: str | None
    audio_codec: str | None
    audio_mux_started_at: datetime | None
    audio_mux_completed_at: datetime | None
    audio_mux_error_code: str | None
    audio_mux_error_message: str | None
    export_id: str | None
    final_export_path: str | None
    final_export_file_name: str | None
    final_export_size_bytes: int | None
    export_started_at: datetime | None
    export_completed_at: datetime | None
    export_error_code: str | None
    export_error_message: str | None
    realesrgan_model_slug: str | None
    realesrgan_device: str | None
    realesrgan_frames_total: int | None
    realesrgan_frames_processed: int
    realesrgan_failed_frames: int
    realesrgan_average_frame_time_ms: int | None
    realesrgan_error_code: str | None
    realesrgan_error_message: str | None
    error_code: str | None
    error_message: str | None


class JobLogResponse(BaseModel):
    id: str
    job_id: str
    level: str
    message: str
    stage: str | None
    created_at: datetime


class JobLogsResponse(BaseModel):
    items: list[JobLogResponse]
    total: int
    limit: int
    offset: int


class JobControlResponse(BaseModel):
    job: JobResponse
    message: str


class JobDeleteResponse(BaseModel):
    deleted: bool
    job_id: str


class JobFrameItem(BaseModel):
    index: int
    file_name: str
    path: str


class JobFramesResponse(BaseModel):
    job_id: str
    frames_dir: str | None
    items: list[JobFrameItem]
    total: int
    limit: int
    offset: int


class FrameExtractionSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    working_dir: str | None
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
    frame_file_pattern: str | None
    frame_format: str | None
    frames_total: int | None
    frames_processed: int
    extracted_frames: int
    extraction_started_at: datetime | None
    extraction_completed_at: datetime | None


class DeleteFramesResponse(BaseModel):
    deleted: bool
    job_id: str


class JobEnhancedFrameItem(BaseModel):
    index: int
    file_name: str
    path: str


class JobEnhancedFramesResponse(BaseModel):
    job_id: str
    frames_dir: str | None
    items: list[JobEnhancedFrameItem]
    total: int
    limit: int
    offset: int


class FrameEnhancementSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    enhancer_engine: str | None
    original_frames_dir: str | None
    enhanced_frames_dir: str | None
    extracted_frames: int
    enhanced_frames: int
    enhancement_started_at: datetime | None
    enhancement_completed_at: datetime | None
    enhancement_error_code: str | None
    enhancement_error_message: str | None


class DeleteEnhancedFramesResponse(BaseModel):
    deleted: bool
    job_id: str


class VideoEncodingSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    encoded_dir: str | None
    encoded_video_path: str | None
    encoded_video_file_name: str | None
    encoded_video_size_bytes: int | None
    encoding_fps: float | None
    encoding_codec: str | None
    encoding_format: str | None
    encoding_started_at: datetime | None
    encoding_completed_at: datetime | None
    encoding_error_code: str | None
    encoding_error_message: str | None


class EncodedVideoResponse(BaseModel):
    job_id: str
    available: bool
    path: str | None
    file_name: str | None
    size_bytes: int | None
    format: str
    codec: str
    has_audio: bool


class DeleteEncodedVideoResponse(BaseModel):
    deleted: bool
    job_id: str


class AudioMuxSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    muxed_video_path: str | None
    muxed_video_file_name: str | None
    muxed_video_size_bytes: int | None
    audio_strategy: str | None
    audio_codec: str | None
    audio_mux_started_at: datetime | None
    audio_mux_completed_at: datetime | None
    audio_mux_error_code: str | None
    audio_mux_error_message: str | None


class FinalExportSummaryResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str
    export_id: str | None
    final_export_path: str | None
    final_export_file_name: str | None
    final_export_size_bytes: int | None
    export_started_at: datetime | None
    export_completed_at: datetime | None
    export_error_code: str | None
    export_error_message: str | None


class MuxedVideoResponse(BaseModel):
    job_id: str
    available: bool
    path: str | None
    file_name: str | None
    size_bytes: int | None
    format: str
    video_codec: str
    audio_codec: str | None
    has_audio: bool
    audio_strategy: str | None


class DeleteMuxedVideoResponse(BaseModel):
    deleted: bool
    job_id: str
