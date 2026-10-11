from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AIModelResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    provider: str
    category: str
    model_type: str
    scale_factor: int | None
    version: str | None
    status: str
    is_enabled: bool
    is_installed: bool
    file_name: str | None
    relative_path: str | None
    absolute_path: str | None
    file_size_bytes: int | None
    estimated_vram_mb: int | None
    supports_gpu: bool
    supports_cpu: bool
    capabilities: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AIModelListResponse(BaseModel):
    items: list[AIModelResponse]
    total: int
    limit: int
    offset: int


class AIModelDownloadStartResponse(BaseModel):
    slug: str
    status: str
    already_installed: bool


class AIModelDownloadProgressResponse(BaseModel):
    slug: str
    status: str
    bytes_done: int
    bytes_total: int | None
    percent: float
    error_code: str | None
    error_message: str | None


class AIModelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    slug: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    provider: str = "custom"
    category: str
    model_type: str
    scale_factor: int | None = None
    version: str | None = None
    file_name: str | None = None
    relative_path: str | None = None
    estimated_vram_mb: int | None = None
    supports_gpu: bool = True
    supports_cpu: bool = True
    capabilities: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIModelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: str | None = None
    is_enabled: bool | None = None
    relative_path: str | None = None
    estimated_vram_mb: int | None = None
    capabilities: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AIModelRefreshResponse(BaseModel):
    refreshed: bool
    items: list[AIModelResponse]
    total: int
    limit: int
    offset: int
