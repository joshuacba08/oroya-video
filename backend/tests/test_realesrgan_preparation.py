from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.db.repositories import job_repository
from app.enhancers.mock_enhancer import MockFrameEnhancer
from app.enhancers.realesrgan_enhancer import RealESRGANFrameEnhancer
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


class FakeCuda:
    def __init__(self, *, available: bool, devices: list[dict[str, object]] | None = None) -> None:
        self._available = available
        self._devices = devices or []

    def is_available(self) -> bool:
        return self._available

    def device_count(self) -> int:
        return len(self._devices) if self._available else 0

    def get_device_name(self, index: int) -> str:
        return str(self._devices[index]["name"])

    def get_device_properties(self, index: int) -> SimpleNamespace:
        return SimpleNamespace(total_memory=self._devices[index]["total_memory"])

    def empty_cache(self) -> None:
        return None


class FakeTorch:
    def __init__(
        self,
        *,
        cuda_available: bool,
        devices: list[dict[str, object]] | None = None,
    ) -> None:
        self.__version__ = "2.6.0"
        self.cuda = FakeCuda(available=cuda_available, devices=devices)


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
def prep_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "realesrgan-prep.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
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
        json={"name": "Preparation Project", "video_asset_id": video_asset_id},
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


def test_runtime_endpoint_reports_torch_missing_without_failing(prep_client) -> None:
    client, _, _ = prep_client

    with patch("app.services.ai_runtime_service.get_torch_module", return_value=None):
        response = client.get("/api/ai/runtime")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["torch_available"] is False
    assert response.json()["selected_device"] is None


def test_runtime_endpoint_selects_cpu_when_cuda_is_unavailable(prep_client) -> None:
    client, _, _ = prep_client
    fake_torch = FakeTorch(cuda_available=False)

    with patch("app.services.ai_runtime_service.get_torch_module", return_value=fake_torch):
        response = client.get("/api/ai/runtime")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["selected_device"] == "cpu"
    assert "CPU fallback selected" in response.json()["warnings"][0]


def test_runtime_endpoint_selects_cuda_when_available(prep_client) -> None:
    client, _, _ = prep_client
    fake_torch = FakeTorch(
        cuda_available=True,
        devices=[{"name": "RTX 4070", "total_memory": 12 * 1024**3}],
    )

    with patch("app.services.ai_runtime_service.get_torch_module", return_value=fake_torch):
        response = client.get("/api/ai/runtime")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["selected_device"] == "cuda"
    assert response.json()["cuda_device_count"] == 1
    assert response.json()["cuda_devices"][0]["name"] == "RTX 4070"


def test_runtime_endpoint_warns_when_cuda_is_required_but_missing(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    storage_path = tmp_path / "storage"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{(tmp_path / 'cuda-required.sqlite').as_posix()}",
        ai_device="cuda",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client, patch(
        "app.services.ai_runtime_service.get_torch_module",
        return_value=FakeTorch(cuda_available=False),
    ):
        response = client.get("/api/ai/runtime")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert "CUDA requested but not available." in response.json()["warnings"]


def test_model_validate_endpoint_reports_model_ready(prep_client) -> None:
    client, _, settings = prep_client
    _seed_model_file(settings, "realesrgan-x2")

    with patch(
        "app.services.ai_runtime_service.get_torch_module",
        return_value=FakeTorch(cuda_available=False),
    ):
        response = client.get("/api/ai/models/realesrgan-x2/validate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_run"] is True
    assert payload["is_installed"] is True
    assert payload["device"] == "cpu"


def test_model_validate_reports_missing_realesrgan_packages(prep_client) -> None:
    client, _, settings = prep_client
    _seed_model_file(settings, "realesrgan-x2")

    with (
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch(
            "app.services.realesrgan_service.get_missing_realesrgan_modules",
            return_value=["basicsr"],
        ),
    ):
        response = client.get("/api/ai/models/realesrgan-x2/validate")

    payload = response.json()
    assert payload["runtime_available"] is False
    assert payload["can_run"] is False
    assert any("basicsr" in warning for warning in payload["warnings"])


def test_model_validate_endpoint_returns_404_for_unknown_model(prep_client) -> None:
    client, _, _ = prep_client

    response = client.get("/api/ai/models/unknown-model/validate")

    assert response.status_code == 404
    assert response.json()["error"] == "ai_model_not_found"


def test_registry_supports_mock_and_realesrgan_engines() -> None:
    assert isinstance(get_frame_enhancer("mock"), MockFrameEnhancer)
    assert isinstance(get_frame_enhancer("realesrgan"), RealESRGANFrameEnhancer)


def test_dry_run_accepts_input_frame_path_and_writes_output(prep_client, tmp_path: Path) -> None:
    client, _, settings = prep_client
    _seed_model_file(settings, "realesrgan-x2")
    input_frame = tmp_path / "input.png"
    input_frame.write_bytes(b"png-bytes")

    def fake_enhance(self, source: Path, destination: Path):
        destination.write_bytes(source.read_bytes() + b"-enhanced")
        return destination, 21

    with (
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch.object(RealESRGANFrameEnhancer, "enhance_single_frame", fake_enhance),
    ):
        response = client.post(
            "/api/ai/realesrgan/dry-run",
            json={"model_slug": "realesrgan-x2", "input_frame_path": str(input_frame)},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["device"] == "cpu"
    assert payload["elapsed_time_ms"] == 21
    assert "ai-dry-runs" in payload["output_frame_path"]
    assert Path(payload["output_frame_path"]).exists()
    assert input_frame.read_bytes() == b"png-bytes"


def test_dry_run_accepts_job_and_frame_index(prep_client, tmp_path: Path) -> None:
    client, source_file, settings = prep_client
    _seed_model_file(settings, "realesrgan-x2")
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    original_frames_dir = (
        Path(settings.storage_path) / "temp" / "jobs" / job["id"] / "frames" / "original"
    )
    original_frames_dir.mkdir(parents=True, exist_ok=True)
    frame_path = original_frames_dir / "frame_00000000.png"
    frame_path.write_bytes(b"frame-bytes")
    _update_job(job["id"], original_frames_dir=str(original_frames_dir))

    def fake_enhance(self, source: Path, destination: Path):
        destination.write_bytes(source.read_bytes() + b"-enhanced")
        return destination, 34

    with (
        patch(
            "app.services.ai_runtime_service.get_torch_module",
            return_value=FakeTorch(cuda_available=False),
        ),
        patch.object(RealESRGANFrameEnhancer, "enhance_single_frame", fake_enhance),
    ):
        response = client.post(
            "/api/ai/realesrgan/dry-run",
            json={
                "model_slug": "realesrgan-x2",
                "job_id": job["id"],
                "frame_index": 0,
            },
        )

    assert response.status_code == 200
    assert response.json()["input_frame_path"] == str(frame_path)
    assert response.json()["elapsed_time_ms"] == 34


def test_dry_run_rejects_missing_or_invalid_input(prep_client, tmp_path: Path) -> None:
    client, _, settings = prep_client
    _seed_model_file(settings, "realesrgan-x2")
    invalid_frame = tmp_path / "input.txt"
    invalid_frame.write_text("not an image", encoding="utf-8")

    with patch(
        "app.services.ai_runtime_service.get_torch_module",
        return_value=FakeTorch(cuda_available=False),
    ):
        response = client.post(
            "/api/ai/realesrgan/dry-run",
            json={"model_slug": "realesrgan-x2", "input_frame_path": str(invalid_frame)},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "preview_frame_access_denied"
