from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.main import create_app
from app.schemas.video_schema import (
    AudioStreamInfo,
    StreamSummary,
    VideoFileInfo,
    VideoFormatInfo,
    VideoProbeResponse,
    VideoStreamInfo,
)
from app.services.ai_model_service import DEFAULT_MODELS, seed_default_models


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
def model_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "models.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file, storage_path


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


def test_seed_creates_default_models_without_duplicates(model_client) -> None:
    client, _, _ = model_client

    list_response = client.get("/api/models")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == len(DEFAULT_MODELS)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        seed_default_models(db)
    finally:
        db.close()

    second_list_response = client.get("/api/models")
    assert second_list_response.status_code == 200
    assert second_list_response.json()["total"] == len(DEFAULT_MODELS)


def test_get_models_and_get_model_by_slug(model_client) -> None:
    client, _, _ = model_client

    list_response = client.get("/api/models")
    detail_response = client.get("/api/models/realesrgan-x2")
    missing_response = client.get("/api/models/unknown-model")

    assert list_response.status_code == 200
    assert list_response.json()["total"] == len(DEFAULT_MODELS)
    assert detail_response.status_code == 200
    assert detail_response.json()["slug"] == "realesrgan-x2"
    assert missing_response.status_code == 404
    assert missing_response.json()["error"] == "ai_model_not_found"


def test_post_models_creates_custom_model_and_rejects_duplicate_slug(model_client) -> None:
    client, _, _ = model_client
    payload = {
        "name": "Custom Real-ESRGAN Anime",
        "slug": "custom-realesrgan-anime",
        "description": "Custom anime upscaling model.",
        "provider": "custom",
        "category": "upscaling",
        "model_type": "realesrgan",
        "scale_factor": 4,
        "file_name": "custom-anime-x4.pth",
        "relative_path": "custom/custom-anime-x4.pth",
        "estimated_vram_mb": 8192,
        "supports_gpu": True,
        "supports_cpu": True,
        "capabilities": {"upscale": True, "restore": False},
        "metadata": {"notes": "Manual model registration."},
    }

    create_response = client.post("/api/models", json=payload)
    duplicate_response = client.post("/api/models", json=payload)

    assert create_response.status_code == 201
    assert create_response.json()["slug"] == "custom-realesrgan-anime"
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"] == "ai_model_already_exists"


def test_patch_model_updates_description(model_client) -> None:
    client, _, _ = model_client

    response = client.patch(
        "/api/models/realesrgan-x2",
        json={"description": "Updated model description."},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Updated model description."


def test_refresh_marks_model_installed_when_file_exists(model_client) -> None:
    client, _, storage_path = model_client
    model_file = storage_path / "models" / "realesrgan" / "realesrgan-x2.pth"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(b"weights")

    response = client.post("/api/models/refresh")
    detail_response = client.get("/api/models/realesrgan-x2")

    assert response.status_code == 200
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "installed"
    assert detail_response.json()["is_installed"] is True
    assert detail_response.json()["file_size_bytes"] == len(b"weights")


def test_refresh_marks_model_missing_when_file_does_not_exist(model_client) -> None:
    client, _, storage_path = model_client
    model_file = storage_path / "models" / "realesrgan" / "realesrgan-x4.pth"
    if model_file.exists():
        model_file.unlink()

    response = client.post("/api/models/refresh")
    detail_response = client.get("/api/models/realesrgan-x4")

    assert response.status_code == 200
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "missing"
    assert detail_response.json()["is_installed"] is False


def test_disable_and_enable_model(model_client) -> None:
    client, _, _ = model_client

    disable_response = client.post("/api/models/realesrgan-x2/disable")
    enable_response = client.post("/api/models/realesrgan-x2/enable")

    assert disable_response.status_code == 200
    assert disable_response.json()["is_enabled"] is False
    assert disable_response.json()["status"] == "disabled"
    assert enable_response.status_code == 200
    assert enable_response.json()["is_enabled"] is True


def test_delete_default_model_is_blocked_and_custom_model_can_be_deleted(model_client) -> None:
    client, _, _ = model_client
    create_response = client.post(
        "/api/models",
        json={
            "name": "Custom Model",
            "slug": "custom-model",
            "category": "upscaling",
            "model_type": "realesrgan",
        },
    )
    assert create_response.status_code == 201

    default_delete = client.delete("/api/models/realesrgan-x2")
    custom_delete = client.delete("/api/models/custom-model")

    assert default_delete.status_code == 400
    assert default_delete.json()["error"] == "default_model_cannot_be_deleted"
    assert custom_delete.status_code == 200
    assert custom_delete.json()["deleted"] is True


def test_create_project_with_unknown_or_disabled_model_and_enabled_model(model_client) -> None:
    client, source_file, _ = model_client
    video = _import_video(client, source_file)

    unknown_response = client.post(
        "/api/projects",
        json={
            "name": "Unknown Model Project",
            "video_asset_id": video["id"],
            "enhancement_config": {"model_id": "unknown-model"},
        },
    )
    assert unknown_response.status_code == 404
    assert unknown_response.json()["error"] == "ai_model_not_found"

    disable_response = client.post("/api/models/realesrgan-x2/disable")
    assert disable_response.status_code == 200

    disabled_response = client.post(
        "/api/projects",
        json={"name": "Disabled Model Project", "video_asset_id": video["id"]},
    )
    assert disabled_response.status_code == 409
    assert disabled_response.json()["error"] == "ai_model_disabled"

    enable_response = client.post("/api/models/realesrgan-x2/enable")
    assert enable_response.status_code == 200

    enabled_response = client.post(
        "/api/projects",
        json={"name": "Enabled Model Project", "video_asset_id": video["id"]},
    )
    assert enabled_response.status_code == 201
    assert enabled_response.json()["project"]["enhancement_config"]["model_id"] == "realesrgan-x2"
