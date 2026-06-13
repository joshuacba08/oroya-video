from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import RealESRGANFrameProcessingFailedError
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
from app.services.frame_enhancement_service import enhance_frames_for_job
from tests.helpers import patch_job_preflight_ready


class FakeCuda:
    def __init__(self, *, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def device_count(self) -> int:
        return 0

    def empty_cache(self) -> None:
        return None


class FakeTorch:
    def __init__(self, *, cuda_available: bool) -> None:
        self.__version__ = "2.6.0"
        self.cuda = FakeCuda(available=cuda_available)


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
def realesrgan_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "realesrgan-batch.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        frame_enhancer_engine="realesrgan",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file, settings


def _seed_model_file(settings: Settings, slug: str = "realesrgan-x2") -> Path:
    model_file = Path(settings.storage_path) / "models" / "realesrgan" / f"{slug}.pth"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(b"weights")
    return model_file


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
        json={"name": "RealESRGAN Project", "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(client: TestClient, project_id: str) -> dict:
    response = client.post("/api/jobs", json={"project_id": project_id})
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


def _get_job(job_id: str):
    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        assert job is not None
        db.expunge(job)
        return job
    finally:
        db.close()


def _prepare_original_frames(settings: Settings, job_id: str, frame_count: int = 3) -> Path:
    original_frames_dir = (
        Path(settings.storage_path) / "temp" / "jobs" / job_id / "frames" / "original"
    )
    original_frames_dir.mkdir(parents=True, exist_ok=True)
    for index in range(frame_count):
        (original_frames_dir / f"frame_{index:08d}.png").write_bytes(f"frame-{index}".encode())
    _update_job(
        job_id,
        original_frames_dir=str(original_frames_dir),
        extracted_frames=frame_count,
        frames_total=frame_count,
    )
    return original_frames_dir


def test_start_job_with_realesrgan_requires_model_runtime_but_not_frames(
    realesrgan_client,
) -> None:
    client, source_file, settings = realesrgan_client
    _seed_model_file(settings)
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])

    with (
        patch_job_preflight_ready(),
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch("app.services.job_service.job_queue.enqueue", new_callable=AsyncMock) as enqueue_mock,
    ):
        response = client.post(f"/api/jobs/{job['id']}/start")

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "queued"
    enqueue_mock.assert_awaited_once_with(job["id"])


def test_realesrgan_enhancement_updates_job_metrics_and_outputs(realesrgan_client) -> None:
    client, source_file, settings = realesrgan_client
    _seed_model_file(settings)
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(settings, job["id"], frame_count=3)

    def fake_load_model(self) -> None:
        self.model_load_time_ms = 5

    def fake_enhance_frame(self, source: Path, destination: Path):
        destination.write_bytes(source.read_bytes() + b"-enhanced")
        return destination, 15

    with (
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch(
            "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.load_model",
            fake_load_model,
        ),
        patch(
            "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.enhance_single_frame",
            fake_enhance_frame,
        ),
    ):
        assert database.SessionLocal is not None
        db = database.SessionLocal()
        try:
            enhance_frames_for_job(db, job["id"], engine="realesrgan", settings=settings)
        finally:
            db.close()

    refreshed_job = _get_job(job["id"])
    assert refreshed_job.enhancer_engine == "realesrgan"
    assert refreshed_job.enhanced_frames == 3
    assert refreshed_job.realesrgan_frames_processed == 3
    assert refreshed_job.realesrgan_failed_frames == 0
    assert refreshed_job.realesrgan_average_frame_time_ms == 15
    assert refreshed_job.progress_percent == 60.0
    assert refreshed_job.realesrgan_started_at is not None
    assert refreshed_job.realesrgan_completed_at is not None

    enhanced_dir = Path(refreshed_job.enhanced_frames_dir)
    assert enhanced_dir.exists()
    assert sorted(item.name for item in enhanced_dir.glob("*.png")) == [
        "frame_00000000.png",
        "frame_00000001.png",
        "frame_00000002.png",
    ]


def test_realesrgan_cancellation_stops_between_frames(realesrgan_client) -> None:
    client, source_file, settings = realesrgan_client
    _seed_model_file(settings)
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(settings, job["id"], frame_count=3)
    processed = {"count": 0}

    def fake_load_model(self) -> None:
        self.model_load_time_ms = 5

    def fake_enhance_frame(self, source: Path, destination: Path):
        processed["count"] += 1
        destination.write_bytes(source.read_bytes() + b"-enhanced")
        if processed["count"] == 1:
            _update_job(job["id"], cancel_requested=True)
        return destination, 12

    with (
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch(
            "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.load_model",
            fake_load_model,
        ),
        patch(
            "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.enhance_single_frame",
            fake_enhance_frame,
        ),
    ):
        assert database.SessionLocal is not None
        db = database.SessionLocal()
        try:
            enhance_frames_for_job(db, job["id"], engine="realesrgan", settings=settings)
        finally:
            db.close()

    refreshed_job = _get_job(job["id"])
    assert refreshed_job.status == "cancelled"
    assert refreshed_job.enhanced_frames == 1
    assert refreshed_job.realesrgan_frames_processed == 1
    assert refreshed_job.cancelled_at is not None


def test_realesrgan_fails_job_when_a_frame_fails_and_no_tolerance(realesrgan_client) -> None:
    client, source_file, settings = realesrgan_client
    _seed_model_file(settings)
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(settings, job["id"], frame_count=2)

    def fake_load_model(self) -> None:
        self.model_load_time_ms = 5

    def failing_frame(self, source: Path, destination: Path):
        raise RealESRGANFrameProcessingFailedError()

    with (
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch(
            "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.load_model",
            fake_load_model,
        ),
        patch(
            "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.enhance_single_frame",
            failing_frame,
        ),
    ):
        assert database.SessionLocal is not None
        db = database.SessionLocal()
        try:
            with pytest.raises(RealESRGANFrameProcessingFailedError):
                enhance_frames_for_job(db, job["id"], engine="realesrgan", settings=settings)
        finally:
            db.close()

    refreshed_job = _get_job(job["id"])
    assert refreshed_job.status == "failed"
    assert refreshed_job.realesrgan_error_code == "realesrgan_frame_processing_failed"


def test_realesrgan_continues_when_failed_frames_are_within_limit(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    storage_path = tmp_path / "storage"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{(tmp_path / 'realesrgan-tolerant.sqlite').as_posix()}",
        frame_enhancer_engine="realesrgan",
        realesrgan_max_failed_frames=1,
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        _seed_model_file(settings)
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])
        _prepare_original_frames(settings, job["id"], frame_count=3)
        calls = {"count": 0}

        def fake_load_model(self) -> None:
            self.model_load_time_ms = 5

        def sometimes_failing_frame(self, source: Path, destination: Path):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RealESRGANFrameProcessingFailedError()
            destination.write_bytes(source.read_bytes() + b"-enhanced")
            return destination, 18

        with (
            patch(
                "app.services.ai_runtime_service.get_torch_module",
                return_value=FakeTorch(cuda_available=False),
            ),
            patch(
                "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.load_model",
                fake_load_model,
            ),
            patch(
                "app.enhancers.realesrgan_enhancer.RealESRGANFrameEnhancer.enhance_single_frame",
                sometimes_failing_frame,
            ),
        ):
            assert database.SessionLocal is not None
            db = database.SessionLocal()
            try:
                enhance_frames_for_job(db, job["id"], engine="realesrgan", settings=settings)
            finally:
                db.close()

        refreshed_job = _get_job(job["id"])
        assert refreshed_job.status == "running"
        assert refreshed_job.enhanced_frames == 2
        assert refreshed_job.realesrgan_failed_frames == 1
        assert refreshed_job.progress_percent == 60.0


def test_realesrgan_job_endpoints_return_summary_and_validation(realesrgan_client) -> None:
    client, source_file, settings = realesrgan_client
    _seed_model_file(settings)
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_original_frames(settings, job["id"], frame_count=2)
    _update_job(
        job["id"],
        status="completed",
        current_stage="completed",
        enhancer_engine="realesrgan",
        realesrgan_model_slug="realesrgan-x2",
        realesrgan_model_path=str(_seed_model_file(settings)),
        realesrgan_device="cpu",
        realesrgan_scale=2,
        realesrgan_tile_size=0,
        realesrgan_tile_pad=10,
        realesrgan_pre_pad=0,
        realesrgan_half_precision=False,
        realesrgan_frames_total=2,
        realesrgan_frames_processed=2,
        realesrgan_failed_frames=0,
        realesrgan_average_frame_time_ms=15,
    )

    with patch(
        "app.services.ai_runtime_service.get_torch_module",
        return_value=FakeTorch(cuda_available=False),
    ):
        validation_response = client.post(f"/api/jobs/{job['id']}/realesrgan/validate")

    summary_response = client.get(f"/api/jobs/{job['id']}/realesrgan")

    assert validation_response.status_code == 200
    assert validation_response.json()["ready"] is True
    assert validation_response.json()["device"] == "cpu"
    assert summary_response.status_code == 200
    assert summary_response.json()["model_slug"] == "realesrgan-x2"
    assert summary_response.json()["frames_processed"] == 2


def test_pause_endpoint_returns_realesrgan_specific_message(realesrgan_client) -> None:
    client, source_file, _ = realesrgan_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _update_job(
        job["id"],
        status="running",
        current_stage="enhancing_frames",
        enhancer_engine="realesrgan",
    )

    response = client.post(f"/api/jobs/{job['id']}/pause")

    assert response.status_code == 409
    assert response.json()["error"] == "job_pause_not_supported"
    assert "Real-ESRGAN enhancement" in response.json()["message"]
