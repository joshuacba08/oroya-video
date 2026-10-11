from __future__ import annotations

from datetime import UTC, datetime
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
from tests.helpers import patch_job_preflight_ready


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
def hardening_env(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'hardening.sqlite').as_posix()}",
        debug=True,
    )
    return source_file, settings


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
        json={"name": "Hardening Project", "video_asset_id": video_asset_id},
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


def test_startup_recovery_marks_running_jobs_as_interrupted(hardening_env) -> None:
    source_file, settings = hardening_env

    with TestClient(create_app(settings)) as client:
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])

    _update_job(
        job["id"],
        status="running",
        current_stage="extracting_frames",
        progress_percent=42.5,
    )

    with TestClient(create_app(settings)) as client:
        detail_response = client.get(f"/api/v1/jobs/{job['id']}")
        interrupted_response = client.get("/api/v1/jobs/interrupted")

    assert detail_response.status_code == 200
    payload = detail_response.json()["job"]
    assert payload["status"] == "interrupted"
    assert payload["current_stage"] == "interrupted"
    assert payload["last_known_stage"] == "extracting_frames"
    assert payload["last_known_progress_percent"] == 42.5
    assert payload["interrupted_at"] is not None
    assert interrupted_response.status_code == 200
    assert interrupted_response.json()["total"] == 1
    assert interrupted_response.json()["items"][0]["id"] == job["id"]


def test_preflight_and_pipeline_endpoints_expose_pipeline_state(hardening_env) -> None:
    source_file, settings = hardening_env

    with TestClient(create_app(settings)) as client:
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])

        with patch_job_preflight_ready():
            preflight_response = client.get(f"/api/v1/jobs/{job['id']}/preflight")

        now = datetime.now(UTC).replace(tzinfo=None)
        _update_job(
            job["id"],
            status="completed",
            current_stage="completed",
            progress_percent=100.0,
            preflight_started_at=now,
            preflight_completed_at=now,
            extraction_started_at=now,
            extraction_completed_at=now,
            enhancement_started_at=now,
            enhancement_completed_at=now,
            encoding_started_at=now,
            encoding_completed_at=now,
            audio_mux_started_at=now,
            audio_mux_completed_at=now,
            export_started_at=now,
            export_completed_at=now,
        )
        pipeline_response = client.get(f"/api/v1/jobs/{job['id']}/pipeline")

    assert preflight_response.status_code == 200
    assert preflight_response.json()["ready"] is True
    assert preflight_response.json()["checks"]["ffmpeg_available"] is True
    assert pipeline_response.status_code == 200
    pipeline = pipeline_response.json()
    assert pipeline["job_id"] == job["id"]
    assert pipeline["status"] == "completed"
    assert [stage["name"] for stage in pipeline["stages"]] == [
        "preflight",
        "extracting_frames",
        "enhancing_frames",
        "encoding_video",
        "muxing_audio",
        "exporting",
    ]


def test_retry_and_diagnostics_endpoints_follow_recovery_contract(hardening_env) -> None:
    source_file, settings = hardening_env

    with TestClient(create_app(settings)) as client:
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])

        _update_job(
            job["id"],
            status="failed",
            current_stage="enhancing_frames",
            error_code="cuda_out_of_memory",
            error_message="CUDA ran out of memory while processing frames.",
        )

        diagnostics_response = client.get(f"/api/v1/jobs/{job['id']}/diagnostics")
        retry_response = client.post(
            f"/api/v1/jobs/{job['id']}/retry",
            json={"cleanup_before_retry": False, "reset_progress": True},
        )

    assert diagnostics_response.status_code == 200
    diagnostics = diagnostics_response.json()
    assert diagnostics["error_code"] == "cuda_out_of_memory"
    assert diagnostics["can_retry"] is True
    assert "VRAM" in diagnostics["likely_causes"][0]
    assert diagnostics["related_logs_url"] == f"/api/v1/jobs/{job['id']}/logs"

    assert retry_response.status_code == 200
    retry_payload = retry_response.json()
    assert retry_payload["job"]["status"] == "pending"
    assert retry_payload["job"]["retry_count"] == 1
    assert retry_payload["message"] == "Job prepared for retry."


def test_retry_with_start_queues_the_job(hardening_env) -> None:
    source_file, settings = hardening_env

    with TestClient(create_app(settings)) as client:
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])
        _update_job(job["id"], status="cancelled", current_stage="cancelled")

        with (
            patch_job_preflight_ready(),
            patch("app.services.job_service.job_queue.enqueue") as enqueue,
        ):
            response = client.post(
                f"/api/v1/jobs/{job['id']}/retry",
                json={"cleanup_before_retry": False, "start": True},
            )

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "queued"
    assert response.json()["job"]["retry_count"] == 1
    enqueue.assert_called_once_with(job["id"])


def test_cleanup_and_storage_usage_endpoints_report_deleted_bytes(hardening_env) -> None:
    source_file, settings = hardening_env

    with TestClient(create_app(settings)) as client:
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])

        workspace = prepare_job_workspace(job["id"], settings)
        original_frame = workspace["original_frames_dir"] / "frame_00000000.png"
        enhanced_frame = workspace["enhanced_frames_dir"] / "frame_00000000.png"
        encoded_dir = workspace["working_dir"] / "encoded"
        encoded_dir.mkdir(parents=True, exist_ok=True)
        encoded_file = encoded_dir / "video_silent.mp4"
        muxed_dir = workspace["working_dir"] / "muxed"
        muxed_dir.mkdir(parents=True, exist_ok=True)
        muxed_file = muxed_dir / "video_with_audio.mp4"
        original_frame.write_bytes(b"png")
        enhanced_frame.write_bytes(b"png-enhanced")
        encoded_file.write_bytes(b"encoded")
        muxed_file.write_bytes(b"muxed")

        _update_job(
            job["id"],
            status="completed",
            current_stage="completed",
            original_frames_dir=str(workspace["original_frames_dir"]),
            enhanced_frames_dir=str(workspace["enhanced_frames_dir"]),
            encoded_dir=str(encoded_dir),
            encoded_video_path=str(encoded_file),
            muxed_video_path=str(muxed_file),
        )

        cleanup_response = client.delete(f"/api/v1/jobs/{job['id']}/temp")
        usage_response = client.get("/api/v1/system/storage/usage")

    assert cleanup_response.status_code == 200
    cleanup_payload = cleanup_response.json()
    assert cleanup_payload["deleted"] is True
    assert cleanup_payload["freed_bytes"] > 0
    assert cleanup_payload["deleted_paths"]
    assert original_frame.exists() is False

    assert usage_response.status_code == 200
    usage_payload = usage_response.json()
    assert usage_payload["storage_path"].endswith("storage")
    assert set(usage_payload["breakdown"]) == {
        "db_bytes",
        "temp_bytes",
        "imports_bytes",
        "exports_bytes",
        "models_bytes",
    }
