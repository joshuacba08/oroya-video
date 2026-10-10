from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.db.repositories import job_repository
from app.main import create_app
from app.schemas.video_schema import (
    AudioStreamInfo,
    StreamSummary,
    VideoFileInfo,
    VideoFormatInfo,
    VideoProbeResponse,
    VideoStreamInfo,
)
from app.services.job_workspace_service import prepare_job_workspace
from tests.helpers import assert_error_response


def _build_probe_response(source_path: Path) -> VideoProbeResponse:
    return VideoProbeResponse(
        valid=True,
        file=VideoFileInfo(
            path=str(source_path.resolve()),
            name=source_path.name,
            extension=source_path.suffix.lower(),
            size_bytes=source_path.stat().st_size,
            size_mb=round(source_path.stat().st_size / (1024**2), 1),
        ),
        format=VideoFormatInfo(
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration_seconds=5.0,
            duration_label="00:00:05",
            bit_rate=8000000,
        ),
        video=VideoStreamInfo(
            codec="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            width=1920,
            height=1080,
            resolution_label="1920x1080",
            fps=24.0,
            pix_fmt="yuv420p",
            profile="High",
            bit_rate=7500000,
        ),
        audio=AudioStreamInfo(
            available=True,
            codec="aac",
            codec_long_name="AAC (Advanced Audio Coding)",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
            bit_rate=320000,
        ),
        streams=[
            StreamSummary(index=0, type="video", codec="h264", width=1920, height=1080),
            StreamSummary(index=1, type="audio", codec="aac"),
        ],
        warnings=[],
    )


@pytest.fixture
def contract_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'contract.sqlite').as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file, settings


def _import_video(client: TestClient, source_file: Path) -> dict:
    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        response = client.post(
            "/api/v1/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )
    assert response.status_code == 201
    return response.json()["video"]


def _create_project(client: TestClient, video_asset_id: str) -> dict:
    response = client.post(
        "/api/v1/projects",
        json={"name": "Contract Project", "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(client: TestClient, project_id: str) -> dict:
    response = client.post("/api/v1/jobs", json={"project_id": project_id})
    assert response.status_code == 201
    return response.json()["job"]


def _update_job(job_id: str, **changes) -> None:
    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        assert job is not None
        for key, value in changes.items():
            setattr(job, key, value)
        db.commit()
    finally:
        db.close()


def test_v1_health_legacy_alias_and_cors_headers(contract_client) -> None:
    client, _, _ = contract_client

    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:4200", "X-Request-ID": "req_contract_health"},
    )
    legacy_response = client.get("/api/health")
    full_response = client.get("/api/v1/health/full")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "req_contract_health"
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert legacy_response.status_code == 200
    assert full_response.status_code == 200
    assert full_response.json()["queue"]["worker_running"] is True


def test_error_envelope_and_request_id_are_stable(contract_client) -> None:
    client, _, _ = contract_client

    response = client.get(
        "/api/v1/projects/missing-project-id",
        headers={"X-Request-ID": "req_contract_error"},
    )

    payload = assert_error_response(
        response,
        status_code=404,
        error="project_not_found",
        message="Project was not found.",
    )
    assert payload["request_id"] == "req_contract_error"
    assert response.headers["X-Request-ID"] == "req_contract_error"


def test_bootstrap_dashboard_app_state_queue_and_settings_contracts(contract_client) -> None:
    client, source_file, _ = contract_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    _create_job(client, project["id"])

    bootstrap_response = client.get("/api/v1/bootstrap")
    dashboard_response = client.get("/api/v1/dashboard")
    app_state_response = client.get("/api/v1/app-state")
    queue_response = client.get("/api/v1/queue")
    settings_response = client.get("/api/v1/settings")

    assert bootstrap_response.status_code == 200
    assert set(bootstrap_response.json()) == {"app", "system", "settings", "counts", "warnings"}
    assert dashboard_response.status_code == 200
    assert set(dashboard_response.json()) == {
        "recent_projects",
        "recent_exports",
        "active_jobs",
        "interrupted_jobs",
        "system_status",
        "storage",
        "models",
    }
    assert app_state_response.status_code == 200
    assert set(app_state_response.json()) == {"backend", "queue", "system", "storage"}
    assert queue_response.status_code == 200
    assert {
        "items",
        "total",
        "running",
        "queued",
        "pending",
        "interrupted",
        "limit",
        "offset",
    } <= set(queue_response.json())
    queue_items = queue_response.json()["items"]
    assert len(queue_items) >= 1
    assert queue_items[0]["actions"]["can_start"] is True
    assert queue_items[0]["actions"]["can_retry"] is False
    assert {
        "frames_total",
        "frames_processed",
        "elapsed_time_seconds",
        "error_code",
        "error_message",
        "enhancer_engine",
        "realesrgan_device",
        "realesrgan_frames_total",
        "realesrgan_frames_processed",
        "realesrgan_failed_frames",
        "realesrgan_average_frame_time_ms",
    } <= set(queue_items[0])
    assert settings_response.status_code == 200
    assert set(settings_response.json()) == {"general", "processing", "storage", "cleanup"}


def test_workspace_and_paginated_endpoints_follow_contract(contract_client) -> None:
    client, source_file, settings = contract_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])

    workspace = prepare_job_workspace(job["id"], settings)
    for frame_dir in (workspace["original_frames_dir"], workspace["enhanced_frames_dir"]):
        frame_dir.mkdir(parents=True, exist_ok=True)
        (frame_dir / "frame_00000000.png").write_bytes(b"png")
    _update_job(
        job["id"],
        original_frames_dir=str(workspace["original_frames_dir"]),
        enhanced_frames_dir=str(workspace["enhanced_frames_dir"]),
        enhanced_frames=1,
        extracted_frames=1,
    )

    workspace_response = client.get(f"/api/v1/projects/{project['id']}/workspace")
    videos_response = client.get("/api/v1/videos")
    projects_response = client.get("/api/v1/projects")
    models_response = client.get("/api/v1/models")
    jobs_response = client.get("/api/v1/jobs")
    exports_response = client.get("/api/v1/exports")
    logs_response = client.get(f"/api/v1/jobs/{job['id']}/logs")
    preview_frames_response = client.get(f"/api/v1/jobs/{job['id']}/preview/frames")

    assert workspace_response.status_code == 200
    assert set(workspace_response.json()) == {
        "project",
        "video",
        "latest_job",
        "latest_export",
        "models",
        "preview",
        "actions",
    }
    for response in (
        videos_response,
        projects_response,
        models_response,
        jobs_response,
        exports_response,
        logs_response,
        preview_frames_response,
    ):
        assert response.status_code == 200
        payload = response.json()
        assert {"items", "total", "limit", "offset"} <= set(payload)


def test_settings_patch_and_openapi_export_are_ready_for_frontend(contract_client) -> None:
    client, _, _ = contract_client
    repo_root = Path(__file__).resolve().parents[2]
    openapi_path = repo_root / "shared" / "api" / "openapi.json"

    response = client.patch(
        "/api/v1/settings",
        json={
            "general": {"language": "es"},
            "processing": {"frame_enhancer_engine": "mock", "ai_device": "cpu"},
            "cleanup": {
                "cleanup_temp_older_than_hours": 24,
                "cleanup_keep_preview_frames": 12,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["updated"] is True
    assert response.json()["settings"]["general"]["language"] == "es"
    assert response.json()["settings"]["processing"]["ai_device"] == "cpu"
    assert response.json()["settings"]["cleanup"]["cleanup_temp_older_than_hours"] == 24
    assert response.json()["settings"]["cleanup"]["cleanup_keep_preview_frames"] == 12

    subprocess.run(
        [sys.executable, "scripts/export_openapi.py"],
        cwd=repo_root,
        check=True,
    )
    assert openapi_path.exists()
    schema = json.loads(openapi_path.read_text(encoding="utf-8"))
    assert "/api/v1/bootstrap" in schema["paths"]
    assert "/api/v1/settings" in schema["paths"]
    assert {"Health", "Dashboard", "Settings", "Jobs"} <= {tag["name"] for tag in schema["tags"]}
