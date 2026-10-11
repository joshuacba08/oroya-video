from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.db.repositories import job_repository
from app.enhancers.mock_enhancer import MockFrameEnhancer
from app.enhancers.registry import get_frame_enhancer
from app.main import create_app
from app.schemas.video_schema import (
    AudioStreamInfo,
    StreamSummary,
    VideoFileInfo,
    VideoFormatInfo,
    VideoProbeResponse,
    VideoStreamInfo,
)
from app.services.frame_enhancement_service import enhance_frames_for_job
from app.services.job_workspace_service import prepare_job_workspace


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
def enhancement_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "enhancement.sqlite"
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
        json={"name": "Enhancement Project", "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(client: TestClient, project_id: str) -> dict:
    response = client.post("/api/jobs", json={"project_id": project_id})
    assert response.status_code == 201
    return response.json()["job"]


def _prepare_original_frames(job_id: str, settings: Settings, total: int = 2) -> dict:
    workspace = prepare_job_workspace(job_id, settings)
    for index in range(total):
        (workspace["original_frames_dir"] / f"frame_{index:08d}.png").write_bytes(b"png")

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        assert job is not None
        job.original_frames_dir = str(workspace["original_frames_dir"])
        job.enhanced_frames_dir = str(workspace["enhanced_frames_dir"])
        job.working_dir = str(workspace["working_dir"])
        job.frames_total = total
        job.extracted_frames = total
        db.commit()
    finally:
        db.close()
    return workspace


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


def test_get_frame_enhancer_returns_mock_and_unknown_raises() -> None:
    enhancer = get_frame_enhancer("mock")

    assert isinstance(enhancer, MockFrameEnhancer)

    with pytest.raises(Exception) as excinfo:
        get_frame_enhancer("unknown")

    assert getattr(excinfo.value, "error_code", None) == "frame_enhancer_not_found"


def test_mock_frame_enhancer_copies_frames_and_reports_progress(tmp_path: Path) -> None:
    input_dir = tmp_path / "original"
    output_dir = tmp_path / "enhanced"
    input_dir.mkdir()
    (input_dir / "frame_00000000.png").write_bytes(b"a")
    (input_dir / "frame_00000001.png").write_bytes(b"b")
    progress_calls: list[tuple[int, int]] = []

    processed = MockFrameEnhancer().enhance_frames(
        input_dir,
        output_dir,
        progress_callback=lambda processed, total: progress_calls.append((processed, total)),
    )

    assert processed == 2
    assert progress_calls == [(1, 2), (2, 2)]
    assert (output_dir / "frame_00000000.png").read_bytes() == b"a"
    assert (output_dir / "frame_00000001.png").read_bytes() == b"b"


def test_mock_frame_enhancer_stops_when_cancel_requested(tmp_path: Path) -> None:
    input_dir = tmp_path / "original"
    output_dir = tmp_path / "enhanced"
    input_dir.mkdir()
    (input_dir / "frame_00000000.png").write_bytes(b"a")
    (input_dir / "frame_00000001.png").write_bytes(b"b")
    cancel_checks = {"count": 0}

    def cancel_callback() -> bool:
        cancel_checks["count"] += 1
        return cancel_checks["count"] > 1

    processed = MockFrameEnhancer().enhance_frames(
        input_dir,
        output_dir,
        cancel_callback=cancel_callback,
    )

    assert processed == 1
    assert (output_dir / "frame_00000000.png").exists()
    assert not (output_dir / "frame_00000001.png").exists()


def test_mock_frame_enhancer_stops_when_pause_requested(tmp_path: Path) -> None:
    input_dir = tmp_path / "original"
    output_dir = tmp_path / "enhanced"
    input_dir.mkdir()
    (input_dir / "frame_00000000.png").write_bytes(b"a")
    (input_dir / "frame_00000001.png").write_bytes(b"b")
    pause_checks = {"count": 0}

    def pause_callback() -> bool:
        pause_checks["count"] += 1
        return pause_checks["count"] > 1

    processed = MockFrameEnhancer().enhance_frames(
        input_dir,
        output_dir,
        pause_callback=pause_callback,
    )

    assert processed == 1
    assert (output_dir / "frame_00000000.png").exists()
    assert not (output_dir / "frame_00000001.png").exists()


def test_enhance_frames_for_job_fails_when_original_frames_are_missing(enhancement_client) -> None:
    client, source_file, settings = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(job["id"], settings, total=0)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with pytest.raises(Exception) as excinfo:
            enhance_frames_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert getattr(excinfo.value, "error_code", None) == "original_frames_not_found"
    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    assert progress_response.json()["status"] == "failed"


def test_enhance_frames_for_job_validates_temp_space(enhancement_client) -> None:
    client, source_file, settings = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(job["id"], settings, total=1)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            pytest.raises(Exception) as excinfo,
            patch(
                "app.services.frame_enhancement_service.shutil.disk_usage",
                return_value=(1000, 999, 1),
            ),
        ):
            enhance_frames_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert getattr(excinfo.value, "error_code", None) == "insufficient_temp_storage"
    summary_response = client.get(f"/api/jobs/{job['id']}/frame-enhancement")
    assert summary_response.json()["enhancement_error_code"] == "insufficient_temp_storage"


def test_enhance_frames_for_job_updates_progress_and_timestamps(enhancement_client) -> None:
    client, source_file, settings = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    workspace = _prepare_original_frames(job["id"], settings, total=2)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with patch(
            "app.services.frame_enhancement_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ):
            enhance_frames_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    summary_response = client.get(f"/api/jobs/{job['id']}/frame-enhancement")
    enhanced_frames_response = client.get(f"/api/jobs/{job['id']}/enhanced-frames")

    assert progress_response.status_code == 200
    assert progress_response.json()["current_stage"] == "enhancing_frames"
    assert progress_response.json()["progress_percent"] == 60.0
    assert progress_response.json()["enhancer_engine"] == "mock"
    assert progress_response.json()["enhanced_frames"] == 2
    assert progress_response.json()["enhanced_frames_dir"] == str(workspace["enhanced_frames_dir"])
    assert summary_response.status_code == 200
    assert summary_response.json()["enhancement_started_at"] is not None
    assert summary_response.json()["enhancement_completed_at"] is not None
    assert enhanced_frames_response.status_code == 200
    assert enhanced_frames_response.json()["total"] == 2


def test_cancel_during_enhancement_marks_job_cancelled(enhancement_client) -> None:
    client, source_file, settings = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(job["id"], settings, total=3)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    original_update_job = job_repository.update_job
    cancel_injected = False

    def update_job_with_cancellation(db_session, job_obj, data):
        nonlocal cancel_injected
        if "enhanced_frames" in data and not cancel_injected:
            cancel_injected = True
            data = {
                **data,
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancel_requested": True,
            }
        return original_update_job(db_session, job_obj, data)

    try:
        with (
            patch(
                "app.services.frame_enhancement_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch(
                "app.services.frame_enhancement_service.job_repository.update_job",
                side_effect=update_job_with_cancellation,
            ),
        ):
            enhance_frames_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")

    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "cancelled"
    assert any(
        item["message"] == "Frame enhancement cancelled by user."
        for item in logs_response.json()["items"]
    )


def test_pause_during_enhancement_marks_job_paused(enhancement_client) -> None:
    client, source_file, settings = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(job["id"], settings, total=3)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    original_update_job = job_repository.update_job
    pause_injected = False

    def update_job_with_pause(db_session, job_obj, data):
        nonlocal pause_injected
        if "enhanced_frames" in data and not pause_injected:
            pause_injected = True
            data = {**data, "pause_requested": True}
        return original_update_job(db_session, job_obj, data)

    try:
        with (
            patch(
                "app.services.frame_enhancement_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch(
                "app.services.frame_enhancement_service.job_repository.update_job",
                side_effect=update_job_with_pause,
            ),
        ):
            enhance_frames_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    summary_response = client.get(f"/api/jobs/{job['id']}/frame-enhancement")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")

    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "paused"
    assert progress_response.json()["current_stage"] == "enhancing_frames"
    assert progress_response.json()["enhanced_frames"] == 1
    assert summary_response.json()["enhancement_completed_at"] is None
    assert any(
        item["message"] == "Enhancement paused by user." for item in logs_response.json()["items"]
    )


def test_delete_enhanced_frames_keeps_original_frames(enhancement_client) -> None:
    client, source_file, settings = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    workspace = _prepare_original_frames(job["id"], settings, total=2)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with patch(
            "app.services.frame_enhancement_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ):
            enhance_frames_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    _update_job(job["id"], status="completed", current_stage="completed")
    delete_response = client.delete(f"/api/jobs/{job['id']}/enhanced-frames")
    enhanced_frames_response = client.get(f"/api/jobs/{job['id']}/enhanced-frames")
    summary_response = client.get(f"/api/jobs/{job['id']}/frame-enhancement")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "job_id": job["id"]}
    assert workspace["original_frames_dir"].exists()
    assert enhanced_frames_response.status_code == 404
    assert summary_response.json()["enhanced_frames"] == 0
    assert summary_response.json()["enhanced_frames_dir"] == str(workspace["enhanced_frames_dir"])


def test_pause_requests_pause_during_enhancement(enhancement_client) -> None:
    client, source_file, _ = enhancement_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _update_job(job["id"], status="running", current_stage="enhancing_frames")

    response = client.post(f"/api/jobs/{job['id']}/pause")

    assert response.status_code == 200
    assert response.json()["message"] == "Job pause requested."
    assert response.json()["job"]["status"] == "running"
    assert response.json()["job"]["pause_requested"] is True
