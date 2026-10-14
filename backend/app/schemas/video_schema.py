from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VideoProbeRequest(BaseModel):
    file_path: str = Field(..., min_length=1)


class VideoImportRequest(BaseModel):
    file_path: str = Field(..., min_length=1)
    source_mode: Literal["reference", "copy"] = "reference"


class VideoFileInfo(BaseModel):
    path: str
    name: str
    extension: str
    size_bytes: int
    size_mb: float


class VideoFormatInfo(BaseModel):
    format_name: str | None = None
    duration_seconds: float | None = None
    duration_label: str | None = None
    bit_rate: int | None = None


class VideoStreamInfo(BaseModel):
    codec: str | None = None
    codec_long_name: str | None = None
    width: int | None = None
    height: int | None = None
    resolution_label: str | None = None
    fps: float | None = None
    pix_fmt: str | None = None
    profile: str | None = None
    bit_rate: int | None = None
    color_space: str | None = None
    color_range: str | None = None


class AudioStreamInfo(BaseModel):
    available: bool
    codec: str | None = None
    codec_long_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    bit_rate: int | None = None


class StreamSummary(BaseModel):
    index: int
    type: str
    codec: str | None = None
    width: int | None = None
    height: int | None = None


class VideoProbeResponse(BaseModel):
    valid: bool
    file: VideoFileInfo
    format: VideoFormatInfo
    video: VideoStreamInfo
    audio: AudioStreamInfo
    streams: list[StreamSummary]
    warnings: list[str]


class VideoAssetResponse(BaseModel):
    id: str
    source_path: str
    stored_path: str | None
    source_mode: str
    file_name: str
    file_extension: str
    file_size_bytes: int
    file_size_mb: float
    format_name: str | None
    duration_seconds: float | None
    duration_label: str | None
    bit_rate: int | None
    video_codec: str | None
    video_codec_long_name: str | None
    width: int | None
    height: int | None
    resolution_label: str | None
    fps: float | None
    pix_fmt: str | None
    video_profile: str | None
    video_bit_rate: int | None
    has_audio: bool
    audio_codec: str | None
    audio_codec_long_name: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_channel_layout: str | None
    audio_bit_rate: int | None
    warnings: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoImportResponse(BaseModel):
    video: VideoAssetResponse
    already_imported: bool


class VideoListResponse(BaseModel):
    items: list[VideoAssetResponse]
    total: int
    limit: int
    offset: int


class VideoDeleteResponse(BaseModel):
    deleted: bool
    video_id: str
