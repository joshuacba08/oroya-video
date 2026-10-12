from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import video_thumbnail_service
from tests.test_projects import _import_video

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def thumb_env(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'thumb.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        yield client, source_file, settings


def _fake_ffmpeg(command, **kwargs):
    Path(command[-1]).write_bytes(PNG_BYTES)
    return SimpleNamespace(returncode=0, stderr="")


def test_thumbnail_is_generated_once_and_cached(thumb_env) -> None:
    client, source_file, _ = thumb_env
    video_id = _import_video(client, source_file)["id"]

    with (
        patch.object(video_thumbnail_service, "resolve_tool_path", return_value="ffmpeg"),
        patch.object(video_thumbnail_service.subprocess, "run", side_effect=_fake_ffmpeg) as run,
    ):
        first = client.get(f"/api/v1/videos/{video_id}/thumbnail")
        second = client.get(f"/api/v1/videos/{video_id}/thumbnail")

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert first.content == PNG_BYTES
    assert second.content == PNG_BYTES
    assert run.call_count == 1
    command = run.call_args.args[0]
    assert command[command.index("-i") + 1] == str(source_file.resolve())


def test_thumbnail_requires_ffmpeg(thumb_env) -> None:
    client, source_file, _ = thumb_env
    video_id = _import_video(client, source_file)["id"]

    with patch.object(video_thumbnail_service, "resolve_tool_path", return_value=None):
        response = client.get(f"/api/v1/videos/{video_id}/thumbnail")

    assert response.status_code == 503
    assert client.get("/api/v1/videos/missing/thumbnail").status_code == 404


def test_deleting_video_removes_its_thumbnail(thumb_env) -> None:
    client, source_file, settings = thumb_env
    video_id = _import_video(client, source_file)["id"]
    with (
        patch.object(video_thumbnail_service, "resolve_tool_path", return_value="ffmpeg"),
        patch.object(video_thumbnail_service.subprocess, "run", side_effect=_fake_ffmpeg),
    ):
        client.get(f"/api/v1/videos/{video_id}/thumbnail")
    thumbnail = video_thumbnail_service.get_thumbnail_path(video_id, settings)
    assert thumbnail.is_file()

    assert client.delete(f"/api/v1/videos/{video_id}").status_code == 200
    assert not thumbnail.exists()


def test_concurrent_requests_generate_the_thumbnail_once(thumb_env) -> None:
    import threading
    import time

    client, source_file, _ = thumb_env
    video_id = _import_video(client, source_file)["id"]

    def slow_ffmpeg(command, **kwargs):
        time.sleep(0.2)
        return _fake_ffmpeg(command, **kwargs)

    results: list[int] = []
    with (
        patch.object(video_thumbnail_service, "resolve_tool_path", return_value="ffmpeg"),
        patch.object(video_thumbnail_service.subprocess, "run", side_effect=slow_ffmpeg) as run,
    ):
        threads = [
            threading.Thread(
                target=lambda: results.append(
                    client.get(f"/api/v1/videos/{video_id}/thumbnail").status_code
                )
            )
            for _ in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert results == [200, 200, 200]
    assert run.call_count == 1
