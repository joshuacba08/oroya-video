from pathlib import Path
from unittest.mock import AsyncMock, patch

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
from tests.helpers import assert_error_response, patch_job_preflight_ready


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
def jobs_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "jobs.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
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
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    assert response.status_code == 201
    return response.json()["video"]


def _create_project(client: TestClient, video_asset_id: str, name: str = "Project One") -> dict:
    response = client.post(
        "/api/projects",
        json={"name": name, "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(
    client: TestClient,
    project_id: str,
    *,
    model_id: str | None = None,
    enhancement_config: dict | None = None,
    export_config: dict | None = None,
) -> dict:
    payload: dict[str, object] = {"project_id": project_id}
    if model_id is not None:
        payload["model_id"] = model_id
    if enhancement_config is not None:
        payload["enhancement_config"] = enhancement_config
    if export_config is not None:
        payload["export_config"] = export_config

    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 201
    return response.json()


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


def test_post_jobs_creates_job_with_project_defaults(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])

    response = client.post("/api/jobs", json={"project_id": project["id"]})

    assert response.status_code == 201
    payload = response.json()
    assert payload["job"]["project_id"] == project["id"]
    assert payload["job"]["video_asset_id"] == video["id"]
    assert payload["job"]["status"] == "pending"
    assert payload["job"]["current_stage"] == "idle"
    assert payload["job"]["enhancement_config"]["model_id"] == "realesrgan-x2"
    assert payload["job"]["export_config"]["format"] == "mp4"
    assert payload["model"]["slug"] == "realesrgan-x2"


def test_post_jobs_supports_model_override(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])

    payload = _create_job(
        client,
        project["id"],
        model_id="realesrgan-x4",
        enhancement_config={"scale": "4x", "denoise": 10},
        export_config={"output_resolution": "4x"},
    )

    assert payload["job"]["ai_model_slug"] == "realesrgan-x4"
    assert payload["job"]["enhancement_config"]["model_id"] == "realesrgan-x4"
    assert payload["job"]["enhancement_config"]["scale"] == "4x"
    assert payload["job"]["export_config"]["output_resolution"] == "4x"
    assert payload["model"]["slug"] == "realesrgan-x4"


def test_post_jobs_returns_404_when_project_does_not_exist(jobs_client) -> None:
    client, _, _ = jobs_client

    response = client.post("/api/jobs", json={"project_id": "missing-project-id"})

    assert_error_response(
        response,
        status_code=404,
        error="project_not_found",
        message="Project was not found.",
    )


def test_post_jobs_returns_409_when_model_is_disabled(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])

    disable_response = client.post("/api/models/realesrgan-x2/disable")
    assert disable_response.status_code == 200

    response = client.post("/api/jobs", json={"project_id": project["id"]})

    assert_error_response(
        response,
        status_code=409,
        error="ai_model_disabled",
        message="AI model is disabled.",
    )


def test_post_jobs_returns_409_when_video_file_is_missing(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    source_file.unlink()

    response = client.post("/api/jobs", json={"project_id": project["id"]})

    assert_error_response(
        response,
        status_code=409,
        error="video_asset_file_missing",
        message="The video file associated with this asset is missing.",
    )


def test_get_jobs_supports_status_and_project_filters(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    first_project = _create_project(client, video["id"], "Project A")
    second_project = _create_project(client, video["id"], "Project B")
    first_job = _create_job(client, first_project["id"])
    second_job = _create_job(client, second_project["id"])

    cancel_response = client.post(f"/api/jobs/{second_job['job']['id']}/cancel")
    assert cancel_response.status_code == 200

    list_response = client.get("/api/jobs")
    cancelled_response = client.get("/api/jobs", params={"status": "cancelled"})
    project_response = client.get("/api/jobs", params={"project_id": first_project["id"]})

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2
    assert cancelled_response.status_code == 200
    assert cancelled_response.json()["total"] == 1
    assert cancelled_response.json()["items"][0]["id"] == second_job["job"]["id"]
    assert project_response.status_code == 200
    assert project_response.json()["total"] == 1
    assert project_response.json()["items"][0]["id"] == first_job["job"]["id"]


def test_get_job_detail_returns_404_when_missing(jobs_client) -> None:
    client, _, _ = jobs_client

    response = client.get("/api/jobs/missing-job-id")

    assert_error_response(
        response,
        status_code=404,
        error="job_not_found",
        message="Processing job was not found.",
    )


def test_start_job_queues_it_and_records_log(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    created = _create_job(client, project["id"])
    job_id = created["job"]["id"]

    with (
        patch_job_preflight_ready(),
        patch("app.services.job_service.job_queue.enqueue", new_callable=AsyncMock) as enqueue_mock,
    ):
        response = client.post(f"/api/jobs/{job_id}/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["current_stage"] == "queued"
    assert payload["message"] == "Job queued."
    enqueue_mock.assert_awaited_once_with(job_id)

    logs_response = client.get(f"/api/jobs/{job_id}/logs")
    assert logs_response.status_code == 200
    messages = [item["message"] for item in logs_response.json()["items"]]
    assert "Job created." in messages
    assert "Job queued." in messages


def test_pause_resume_cancel_and_delete_job(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    created = _create_job(client, project["id"])
    job_id = created["job"]["id"]

    with (
        patch_job_preflight_ready(),
        patch("app.services.job_service.job_queue.enqueue", new_callable=AsyncMock),
    ):
        start_response = client.post(f"/api/jobs/{job_id}/start")

    pause_response = client.post(f"/api/jobs/{job_id}/pause")

    with (
        patch_job_preflight_ready(),
        patch("app.services.job_service.job_queue.enqueue", new_callable=AsyncMock),
    ):
        resume_response = client.post(f"/api/jobs/{job_id}/resume")

    cancel_response = client.post(f"/api/jobs/{job_id}/cancel")
    delete_response = client.delete(f"/api/jobs/{job_id}")
    detail_response = client.get(f"/api/jobs/{job_id}")

    assert start_response.status_code == 200
    assert pause_response.status_code == 200
    assert pause_response.json()["job"]["status"] == "paused"
    assert pause_response.json()["job"]["pause_requested"] is True
    assert resume_response.status_code == 200
    assert resume_response.json()["job"]["status"] == "queued"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["job"]["status"] == "cancelled"
    assert cancel_response.json()["job"]["cancel_requested"] is True
    assert cancel_response.json()["job"]["cancelled_at"] is not None
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "job_id": job_id}
    assert detail_response.status_code == 404


def test_delete_job_returns_409_when_running(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    created = _create_job(client, project["id"])
    job_id = created["job"]["id"]
    _update_job(job_id, status="running", current_stage="extracting_frames")

    response = client.delete(f"/api/jobs/{job_id}")

    assert_error_response(
        response,
        status_code=409,
        error="job_invalid_state",
        message="The job cannot perform this action in its current state.",
    )


def test_progress_and_logs_endpoints_return_job_state(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    created = _create_job(client, project["id"])
    job_id = created["job"]["id"]

    progress_response = client.get(f"/api/jobs/{job_id}/progress")
    logs_response = client.get(f"/api/jobs/{job_id}/logs")

    assert progress_response.status_code == 200
    assert progress_response.json()["job_id"] == job_id
    assert progress_response.json()["status"] == "pending"
    assert progress_response.json()["original_frames_dir"] is None
    assert logs_response.status_code == 200
    assert logs_response.json()["total"] == 1
    assert logs_response.json()["items"][0]["message"] == "Job created."


def test_completed_job_cannot_start_and_pending_job_cannot_resume(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    created = _create_job(client, project["id"])
    job_id = created["job"]["id"]
    _update_job(job_id, status="completed", current_stage="completed")

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
    ):
        start_response = client.post(f"/api/jobs/{job_id}/start")

    _update_job(job_id, status="pending", current_stage="idle")
    resume_response = client.post(f"/api/jobs/{job_id}/resume")

    assert start_response.status_code == 409
    assert start_response.json()["error"] == "job_invalid_state"
    assert resume_response.status_code == 409
    assert resume_response.json()["error"] == "job_invalid_state"
