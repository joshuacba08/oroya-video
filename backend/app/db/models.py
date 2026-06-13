from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size_mb: Mapped[float] = mapped_column(Float, nullable=False)
    format_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bit_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_codec_long_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    pix_fmt: Mapped[str | None] = mapped_column(String(50), nullable=True)
    video_profile: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_bit_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audio_codec: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_codec_long_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_channel_layout: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_bit_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    streams_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
    projects: Mapped[list[Project]] = relationship(
        "Project",
        back_populates="video_asset",
    )
    exports: Mapped[list[ExportAsset]] = relationship(
        "ExportAsset",
        back_populates="video_asset",
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_asset_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("video_assets.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    enhancement_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    export_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    video_asset: Mapped[VideoAsset] = relationship(
        "VideoAsset",
        back_populates="projects",
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        "ProcessingJob",
        back_populates="project",
    )
    exports: Mapped[list[ExportAsset]] = relationship(
        "ExportAsset",
        back_populates="project",
    )


class AIModel(Base):
    __tablename__ = "ai_models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    model_type: Mapped[str] = mapped_column(String(120), nullable=False)
    scale_factor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relative_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    absolute_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_vram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_gpu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_cpu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        "ProcessingJob",
        back_populates="ai_model",
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    video_asset_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("video_assets.id"),
        nullable=False,
        index=True,
    )
    ai_model_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("ai_models.id"),
        nullable=True,
    )
    ai_model_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    frames_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frames_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enhancement_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    export_config_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    working_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_frames_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    enhanced_frames_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_file_pattern: Mapped[str | None] = mapped_column(String(120), nullable=True)
    frame_format: Mapped[str | None] = mapped_column(String(20), nullable=True, default="png")
    extracted_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enhancer_engine: Mapped[str | None] = mapped_column(String(60), nullable=True, default="mock")
    enhanced_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extraction_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enhancement_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enhancement_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enhancement_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enhancement_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    encoded_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    encoded_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    encoded_video_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encoded_video_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoding_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    encoding_codec: Mapped[str | None] = mapped_column(String(60), nullable=True, default="h264")
    encoding_format: Mapped[str | None] = mapped_column(String(20), nullable=True, default="mp4")
    encoding_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    encoding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    encoding_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encoding_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    muxed_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    muxed_video_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    muxed_video_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_strategy: Mapped[str | None] = mapped_column(String(60), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(60), nullable=True)
    audio_mux_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    audio_mux_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    audio_mux_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    audio_mux_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_id: Mapped[str | None] = mapped_column(String, nullable=True)
    final_export_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_export_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    final_export_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    export_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    export_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    export_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    export_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interrupted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleanup_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleanup_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleanup_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cleanup_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    preflight_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    preflight_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    preflight_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preflight_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_known_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_known_progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    process_kind: Mapped[str | None] = mapped_column(String(60), nullable=True)
    process_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    process_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    temp_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_frames_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enhanced_frames_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoded_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    muxed_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exports_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_model_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    realesrgan_model_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    realesrgan_device: Mapped[str | None] = mapped_column(String(20), nullable=True)
    realesrgan_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_tile_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_tile_pad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_pre_pad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_half_precision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    realesrgan_frames_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_frames_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    realesrgan_failed_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    realesrgan_average_frame_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    realesrgan_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    realesrgan_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    realesrgan_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    realesrgan_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pause_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship("Project", back_populates="processing_jobs")
    video_asset: Mapped[VideoAsset] = relationship("VideoAsset")
    ai_model: Mapped[AIModel | None] = relationship("AIModel", back_populates="processing_jobs")
    exports: Mapped[list[ExportAsset]] = relationship(
        "ExportAsset",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list[JobLog]] = relationship(
        "JobLog",
        back_populates="job",
        cascade="all, delete-orphan",
    )


class ExportAsset(Base):
    __tablename__ = "export_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("processing_jobs.id"),
        nullable=False,
        index=True,
    )
    video_asset_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("video_assets.id"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size_mb: Mapped[float] = mapped_column(Float, nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    video_codec: Mapped[str | None] = mapped_column(String(60), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(60), nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audio_strategy: Mapped[str | None] = mapped_column(String(60), nullable=True)
    resolution_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    project: Mapped[Project] = relationship("Project", back_populates="exports")
    job: Mapped[ProcessingJob] = relationship("ProcessingJob", back_populates="exports")
    video_asset: Mapped[VideoAsset] = relationship("VideoAsset", back_populates="exports")


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("processing_jobs.id"),
        nullable=False,
        index=True,
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    job: Mapped[ProcessingJob] = relationship("ProcessingJob", back_populates="logs")
