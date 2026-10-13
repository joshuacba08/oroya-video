from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.paths import build_frame_file_name
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
from app.services.preview_service import get_original_frame_path


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
def preview_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "preview.sqlite"
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


def _create_project(client: TestClient, video_asset_id: str) -> dict:
    response = client.post(
        "/api/projects",
        json={"name": "Preview Project", "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(client: TestClient, project_id: str) -> dict:
    response = client.post("/api/jobs", json={"project_id": project_id})
    assert response.status_code == 201
    return response.json()["job"]


def _prepare_preview_frames(
    job_id: str,
    settings: Settings,
    *,
    original: int,
    enhanced: int,
) -> dict:
    workspace = prepare_job_workspace(job_id, settings)
    for index in range(original):
        (workspace["original_frames_dir"] / build_frame_file_name(index)).write_bytes(b"png")
    for index in range(enhanced):
        (workspace["enhanced_frames_dir"] / build_frame_file_name(index)).write_bytes(b"png")

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        assert job is not None
        job.working_dir = str(workspace["working_dir"])
        job.original_frames_dir = str(workspace["original_frames_dir"])
        job.enhanced_frames_dir = str(workspace["enhanced_frames_dir"])
        job.frame_file_pattern = "frame_%08d.png"
        job.frame_format = "png"
        job.extracted_frames = original
        job.enhanced_frames = enhanced
        job.frames_total = max(original, enhanced)
        job.status = "completed"
        job.current_stage = "completed"
        db.commit()
    finally:
        db.close()
    return workspace


def test_build_frame_file_name_formats_indexes() -> None:
    assert build_frame_file_name(0) == "frame_00000000.png"
    assert build_frame_file_name(480) == "frame_00000480.png"


def test_preview_info_returns_counts_and_recommended_frame(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=4, enhanced=4)

    response = client.get(f"/api/jobs/{job['id']}/preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["original_frames_count"] == 4
    assert payload["enhanced_frames_count"] == 4
    assert payload["comparable_frames_count"] == 4
    assert payload["recommended_frame_index"] == 2


def test_preview_metadata_returns_404_when_original_frames_are_missing(preview_client) -> None:
    client, source_file, _ = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])

    response = client.get(f"/api/jobs/{job['id']}/preview")

    assert response.status_code == 404
    assert response.json()["error"] == "preview_not_available"


def test_preview_original_and_enhanced_routes_return_png(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)

    original_response = client.get(f"/api/jobs/{job['id']}/preview/original/0")
    enhanced_response = client.get(f"/api/jobs/{job['id']}/preview/enhanced/0")

    assert original_response.status_code == 200
    assert original_response.headers["content-type"] == "image/png"
    assert enhanced_response.status_code == 200
    assert enhanced_response.headers["content-type"] == "image/png"


def test_preview_routes_reject_negative_indexes(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)

    original_response = client.get(f"/api/jobs/{job['id']}/preview/original/-1")
    enhanced_response = client.get(f"/api/jobs/{job['id']}/preview/enhanced/-1")

    assert original_response.status_code == 400
    assert original_response.json()["error"] == "invalid_frame_index"
    assert enhanced_response.status_code == 400
    assert enhanced_response.json()["error"] == "invalid_frame_index"


def test_preview_routes_return_404_when_frame_is_missing(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)

    response = client.get(f"/api/jobs/{job['id']}/preview/original/999999")

    assert response.status_code == 404
    assert response.json()["error"] == "preview_frame_not_found"


def test_compare_and_recommended_preview_routes_return_urls(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=4, enhanced=4)

    compare_response = client.get(f"/api/jobs/{job['id']}/preview/compare/1")
    recommended_response = client.get(f"/api/jobs/{job['id']}/preview/recommended")

    assert compare_response.status_code == 200
    assert compare_response.json()["original"]["url"].endswith("/preview/original/1")
    assert compare_response.json()["enhanced"]["url"].endswith("/preview/enhanced/1")
    assert recommended_response.status_code == 200
    assert recommended_response.json()["frame_index"] == 2


def test_compare_route_returns_404_when_enhanced_frame_is_missing(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=2, enhanced=1)

    response = client.get(f"/api/jobs/{job['id']}/preview/compare/1")

    assert response.status_code == 404
    assert response.json()["error"] == "preview_frame_not_found"


def test_preview_frames_route_supports_pagination(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=6, enhanced=6)

    response = client.get(f"/api/jobs/{job['id']}/preview/frames?limit=2&offset=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 6
    assert payload["limit"] == 2
    assert payload["offset"] == 2
    assert [item["index"] for item in payload["items"]] == [2, 3]


def test_preview_service_blocks_non_png_and_outside_paths(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with patch(
            "app.services.preview_service.build_frame_file_name",
            return_value="../escape.jpg",
        ):
            with pytest.raises(Exception) as excinfo:
                get_original_frame_path(db, job["id"], 0)
    finally:
        db.close()

    assert getattr(excinfo.value, "error_code", None) == "preview_frame_access_denied"


def test_preview_routes_return_404_when_job_is_missing(preview_client) -> None:
    client, _, _ = preview_client

    response = client.get("/api/jobs/missing-job-id/preview")

    assert response.status_code == 404
    assert response.json()["error"] == "job_not_found"


def _create_job_with_filters(client: TestClient, project_id: str) -> dict:
    response = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "enhancement_config": {"denoise": 40, "sharpen": 30},
        },
    )
    assert response.status_code == 201
    return response.json()["job"]


def test_filtered_preview_serves_enhanced_frame_when_no_filters(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)

    response = client.get(f"/api/jobs/{job['id']}/preview/filtered/0")

    assert response.status_code == 200
    assert response.content == b"png"


def test_filtered_preview_renders_and_caches_filtered_frame(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job_with_filters(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)
    run_calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        run_calls.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"filtered-png")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    with (
        patch(
            "app.services.preview_service.validate_ffmpeg_available",
            return_value="C:/ffmpeg.exe",
        ),
        patch("app.services.preview_service.subprocess.run", side_effect=fake_run),
    ):
        first = client.get(f"/api/jobs/{job['id']}/preview/filtered/0")
        second = client.get(f"/api/jobs/{job['id']}/preview/filtered/0")

    assert first.status_code == 200
    assert first.content == b"filtered-png"
    assert second.status_code == 200
    assert len(run_calls) == 1
    command = run_calls[0]
    assert "-vf" in command
    # Solo los filtros posteriores a la IA: el ruido y la limpieza van antes (REQ-038).
    assert command[command.index("-vf") + 1] == "unsharp=5:5:0.45"


def test_filtered_preview_accepts_query_overrides(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job_with_filters(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)
    run_calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        run_calls.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"filtered-override")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    with (
        patch(
            "app.services.preview_service.validate_ffmpeg_available",
            return_value="C:/ffmpeg.exe",
        ),
        patch("app.services.preview_service.subprocess.run", side_effect=fake_run),
    ):
        response = client.get(
            f"/api/jobs/{job['id']}/preview/filtered/0?denoise=0&sharpen=50&compression_cleanup=true"
        )

    assert response.status_code == 200
    assert run_calls[0][run_calls[0].index("-vf") + 1] == "unsharp=5:5:0.75"


def test_filtered_preview_returns_500_when_render_fails(preview_client) -> None:
    client, source_file, settings = preview_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job_with_filters(client, project["id"])
    _prepare_preview_frames(job["id"], settings, original=1, enhanced=1)

    def fake_run(command, **kwargs):
        class Result:
            returncode = 1
            stderr = "filter failed"

        return Result()

    with (
        patch(
            "app.services.preview_service.validate_ffmpeg_available",
            return_value="C:/ffmpeg.exe",
        ),
        patch("app.services.preview_service.subprocess.run", side_effect=fake_run),
    ):
        response = client.get(f"/api/jobs/{job['id']}/preview/filtered/0")

    assert response.status_code == 500
    assert response.json()["error"] == "filtered_preview_failed"
