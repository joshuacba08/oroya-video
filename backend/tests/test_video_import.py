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
def app_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "test.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file, storage_path


def test_post_import_registers_reference_video(app_client) -> None:
    client, source_file, _ = app_client

    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["already_imported"] is False
    assert payload["video"]["source_mode"] == "reference"
    assert payload["video"]["stored_path"] is None


def test_post_import_returns_existing_video_when_already_imported(app_client) -> None:
    client, source_file, _ = app_client

    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        first_response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )
        second_response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    assert first_response.status_code == 201
    assert first_response.json()["already_imported"] is False
    assert second_response.status_code == 200
    assert second_response.json()["already_imported"] is True
    assert first_response.json()["video"]["id"] == second_response.json()["video"]["id"]


def test_post_import_copy_mode_calls_copy2(app_client) -> None:
    client, source_file, _ = app_client

    with (
        patch(
            "app.services.video_probe_service.probe_video",
            return_value=_build_probe_response(source_file),
        ),
        patch(
            "app.services.video_import_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch("app.services.video_import_service.shutil.copy2") as copy2_mock,
    ):
        response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "copy"},
        )

    assert response.status_code == 201
    assert copy2_mock.called
    assert response.json()["video"]["source_mode"] == "copy"
    assert response.json()["video"]["stored_path"] is not None


def test_post_import_copy_mode_returns_controlled_error_when_copy_fails(app_client) -> None:
    client, source_file, _ = app_client

    with (
        patch(
            "app.services.video_probe_service.probe_video",
            return_value=_build_probe_response(source_file),
        ),
        patch(
            "app.services.video_import_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.video_import_service.shutil.copy2",
            side_effect=OSError("copy failed"),
        ),
    ):
        response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "copy"},
        )

    assert_error_response(
        response,
        status_code=500,
        error="video_copy_failed",
        message="Video could not be copied to internal storage.",
    )


def test_post_import_copy_mode_returns_400_when_space_is_insufficient(app_client) -> None:
    client, source_file, _ = app_client

    with (
        patch(
            "app.services.video_probe_service.probe_video",
            return_value=_build_probe_response(source_file),
        ),
        patch(
            "app.services.video_import_service.shutil.disk_usage",
            return_value=(1000, 999, 1),
        ),
    ):
        response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "copy"},
        )

    assert_error_response(
        response,
        status_code=400,
        error="insufficient_storage_space",
        message="Not enough storage space to copy the video.",
    )


def test_get_videos_returns_items_and_total(app_client) -> None:
    client, source_file, _ = app_client

    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    response = client.get("/api/videos")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1


def test_get_video_by_id_returns_existing_video(app_client) -> None:
    client, source_file, _ = app_client

    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        import_response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    video_id = import_response.json()["video"]["id"]
    response = client.get(f"/api/videos/{video_id}")

    assert response.status_code == 200
    assert response.json()["id"] == video_id


def test_get_video_by_id_returns_404_when_missing(app_client) -> None:
    client, _, _ = app_client

    response = client.get("/api/videos/missing-video-id")

    assert_error_response(
        response,
        status_code=404,
        error="video_asset_not_found",
        message="Video asset was not found.",
    )


def test_delete_video_removes_reference_record_but_not_source_file(app_client) -> None:
    client, source_file, _ = app_client

    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        import_response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    video_id = import_response.json()["video"]["id"]
    delete_response = client.delete(f"/api/videos/{video_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "video_id": video_id}
    assert source_file.exists()
    assert client.get(f"/api/videos/{video_id}").status_code == 404


def test_delete_video_in_copy_mode_removes_internal_folder_only(app_client) -> None:
    client, source_file, _ = app_client

    with (
        patch(
            "app.services.video_probe_service.probe_video",
            return_value=_build_probe_response(source_file),
        ),
        patch(
            "app.services.video_import_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch("app.services.video_import_service.shutil.copy2"),
        patch("app.services.video_import_service.shutil.rmtree") as rmtree_mock,
    ):
        import_response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "copy"},
        )
        video_id = import_response.json()["video"]["id"]
        delete_response = client.delete(f"/api/videos/{video_id}")

    assert delete_response.status_code == 200
    assert rmtree_mock.called
    assert source_file.exists()
