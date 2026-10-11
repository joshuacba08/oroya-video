from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.video_schema import VideoAssetResponse


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = None
    video_asset_id: str
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None
    workspace_state: dict[str, Any] | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: (
        Literal[
            "draft",
            "ready",
            "processing",
            "completed",
            "failed",
            "archived",
        ]
        | None
    ) = None
    enhancement_config: dict[str, Any] | None = None
    export_config: dict[str, Any] | None = None
    workspace_state: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    video_asset_id: str
    status: str
    enhancement_config: dict[str, Any]
    export_config: dict[str, Any]
    workspace_state: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None
    # Para las tarjetas de proyecto, sin pedir el video aparte.
    video_duration_seconds: float | None = None


class ProjectDetailResponse(BaseModel):
    project: ProjectResponse
    video: VideoAssetResponse


class ProjectWorkspaceResponse(BaseModel):
    project: ProjectResponse
    video: VideoAssetResponse
    latest_job: dict[str, Any] | None
    latest_export: dict[str, Any] | None
    models: dict[str, Any]
    preview: dict[str, Any]
    actions: dict[str, bool]


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


class ProjectDeleteResponse(BaseModel):
    deleted: bool
    project_id: str
