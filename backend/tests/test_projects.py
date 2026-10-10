from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.video_schema import (
    AudioStreamInfo,
    StreamSummary,
    VideoFileInfo,
    VideoFormatInfo,
    VideoProbeResponse,
    VideoStreamInfo,
)
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
            duration_seconds=128.45,
            duration_label="00:02:08",
            bit_rate=8000000,
        ),
        video=VideoStreamInfo(
            codec="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            width=1920,
            height=1080,
            resolution_label="1920x1080",
            fps=23.976,
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
def project_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "projects.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file


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
    return response.json()


def test_create_project_applies_default_configs(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)

    response = client.post(
        "/api/projects",
        json={"name": "Anime Episode 01 - 4K Upscale", "video_asset_id": video["id"]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project"]["status"] == "draft"
    assert payload["project"]["enhancement_config"]["model_id"] == "realesrgan-x2"
    assert payload["project"]["export_config"]["format"] == "mp4"
    assert payload["project"]["workspace_state"]["compare_mode"] == "split"
    assert payload["video"]["id"] == video["id"]


def test_create_project_returns_404_when_video_asset_does_not_exist(project_client) -> None:
    client, _ = project_client

    response = client.post(
        "/api/projects",
        json={"name": "Invalid Project", "video_asset_id": "missing-video-id"},
    )

    assert_error_response(
        response,
        status_code=404,
        error="video_asset_not_found",
        message="Video asset was not found.",
    )


def test_create_project_returns_409_when_video_file_is_missing(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    source_file.unlink()

    response = client.post(
        "/api/projects",
        json={"name": "Broken Project", "video_asset_id": video["id"]},
    )

    assert_error_response(
        response,
        status_code=409,
        error="video_asset_file_missing",
        message="The video file associated with this asset is missing.",
    )


def test_list_projects_supports_limit_offset_status_and_search(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)

    first = _create_project(client, video["id"], "Anime Episode 01")
    second = _create_project(client, video["id"], "Old Family Video")
    third = _create_project(client, video["id"], "Clip Enhancement Test")

    archive_response = client.patch(
        f"/api/projects/{second['project']['id']}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200

    list_response = client.get("/api/projects", params={"limit": 1, "offset": 1})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 3
    assert len(list_response.json()["items"]) == 1

    archived_response = client.get("/api/projects", params={"status": "archived"})
    assert archived_response.status_code == 200
    assert archived_response.json()["total"] == 1
    assert archived_response.json()["items"][0]["id"] == second["project"]["id"]

    search_response = client.get("/api/projects", params={"search": "Clip"})
    assert search_response.status_code == 200
    assert search_response.json()["total"] == 1
    assert search_response.json()["items"][0]["id"] == third["project"]["id"]

    assert first["project"]["id"] != second["project"]["id"]


def test_get_project_detail_returns_video_and_updates_last_opened(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    created = _create_project(client, video["id"])
    project_id = created["project"]["id"]

    response = client.get(f"/api/projects/{project_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["id"] == project_id
    assert payload["video"]["id"] == video["id"]
    assert payload["project"]["last_opened_at"] is not None


def test_get_project_detail_returns_404_when_missing(project_client) -> None:
    client, _ = project_client

    response = client.get("/api/projects/missing-project-id")

    assert_error_response(
        response,
        status_code=404,
        error="project_not_found",
        message="Project was not found.",
    )


def test_patch_project_updates_name_and_merges_configs(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    created = _create_project(client, video["id"])
    project_id = created["project"]["id"]

    response = client.patch(
        f"/api/projects/{project_id}",
        json={
            "name": "Anime Episode 01 - Final Upscale",
            "enhancement_config": {"denoise": 20},
            "export_config": {"output_resolution": "4x"},
            "workspace_state": {"zoom": "100%", "selected_frame": 42},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["name"] == "Anime Episode 01 - Final Upscale"
    assert payload["project"]["enhancement_config"]["model_id"] == "realesrgan-x2"
    assert payload["project"]["enhancement_config"]["denoise"] == 20
    assert payload["project"]["export_config"]["format"] == "mp4"
    assert payload["project"]["export_config"]["output_resolution"] == "4x"
    assert payload["project"]["workspace_state"]["zoom"] == "100%"
    assert payload["project"]["workspace_state"]["selected_frame"] == 42
    assert payload["project"]["workspace_state"]["compare_mode"] == "split"


def test_patch_project_accepts_model_uuid_and_normalizes_to_slug(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    created = _create_project(client, video["id"])
    project_id = created["project"]["id"]
    model_response = client.get("/api/models/realesrgan-x4")
    assert model_response.status_code == 200

    response = client.patch(
        f"/api/projects/{project_id}",
        json={
            "enhancement_config": {
                "model_id": model_response.json()["id"],
                "scale": "4x",
            },
            "export_config": {"output_resolution": "4x"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["enhancement_config"]["model_id"] == "realesrgan-x4"
    assert payload["project"]["enhancement_config"]["scale"] == "4x"
    assert payload["project"]["export_config"]["output_resolution"] == "4x"


def test_patch_project_validates_configuration_values(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    created = _create_project(client, video["id"])
    project_id = created["project"]["id"]

    response = client.patch(
        f"/api/projects/{project_id}",
        json={"workspace_state": {"zoom": "300%"}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_project_configuration"


def test_delete_project_removes_project_but_keeps_video_asset(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    created = _create_project(client, video["id"])
    project_id = created["project"]["id"]

    delete_response = client.delete(f"/api/projects/{project_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "project_id": project_id}
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get(f"/api/videos/{video['id']}").status_code == 200


def test_delete_project_with_jobs_cascades_to_jobs(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    project_id = _create_project(client, video["id"])["project"]["id"]
    job_response = client.post("/api/jobs", json={"project_id": project_id})
    assert job_response.status_code == 201
    job_id = job_response.json()["job"]["id"]

    delete_response = client.delete(f"/api/projects/{project_id}")

    assert delete_response.status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_delete_project_is_blocked_while_a_job_is_running(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    project_id = _create_project(client, video["id"])["project"]["id"]
    job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]
    _set_job_status(job_id, "running")

    response = client.delete(f"/api/projects/{project_id}")

    assert response.status_code == 409
    assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_delete_video_with_projects_and_jobs_cascades(project_client) -> None:
    client, source_file = project_client
    video = _import_video(client, source_file)
    project_id = _create_project(client, video["id"])["project"]["id"]
    job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]

    response = client.delete(f"/api/videos/{video['id']}")

    assert response.status_code == 200
    assert client.get(f"/api/videos/{video['id']}").status_code == 404
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert source_file.exists()


def _set_job_status(job_id: str, status: str) -> None:
    from app.db import database
    from app.db.repositories import job_repository

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        job_repository.update_job(db, job, {"status": status})
        db.commit()
    finally:
        db.close()


def test_delete_project_returns_404_when_missing(project_client) -> None:
    client, _ = project_client

    response = client.delete("/api/projects/missing-project-id")

    assert_error_response(
        response,
        status_code=404,
        error="project_not_found",
        message="Project was not found.",
    )
