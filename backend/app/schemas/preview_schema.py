from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PreviewFrameResponse(BaseModel):
    job_id: str
    frame_index: int
    frame_type: Literal["original", "enhanced"]
    file_name: str
    path: str
    url: str
    available: bool
    size_bytes: int | None = None


class PreviewInfoResponse(BaseModel):
    job_id: str
    project_id: str
    status: str
    current_stage: str
    original_frames_available: bool
    enhanced_frames_available: bool
    original_frames_count: int
    enhanced_frames_count: int
    comparable_frames_count: int
    recommended_frame_index: int | None
    frame_pattern: str
    frame_format: str
    original_frames_dir: str | None
    enhanced_frames_dir: str | None


class CompareFrameResponse(BaseModel):
    job_id: str
    frame_index: int
    original: PreviewFrameResponse
    enhanced: PreviewFrameResponse
    compare_modes: list[str]


class PreviewFrameListItem(BaseModel):
    index: int
    file_name: str
    original_available: bool
    enhanced_available: bool
    original_url: str | None
    enhanced_url: str | None


class PreviewFrameListResponse(BaseModel):
    job_id: str
    items: list[PreviewFrameListItem]
    total: int
    limit: int
    offset: int


class PreviewClipRequest(BaseModel):
    """Motion preview (REQ-043): a few seconds processed with the project's settings."""

    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(default=3.0, gt=0, le=5)
