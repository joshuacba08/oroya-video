import hashlib
import io
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import download_service

FAKE_WEIGHTS = b"fake-model-weights-bytes"
FAKE_SHA256 = hashlib.sha256(FAKE_WEIGHTS).hexdigest()


class InlineThread(threading.Thread):
    """Ejecuta el target sincrónicamente para tests deterministas."""

    def start(self) -> None:  # type: ignore[override]
        self.run()


class FakeHttpResponse(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


@pytest.fixture
def download_client(tmp_path: Path):
    storage_path = tmp_path / "storage"
    db_path = tmp_path / "downloads.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, storage_path

    download_service.reset_download_state("model:realesrgan-x2")


def _patch_download(payload: bytes = FAKE_WEIGHTS):
    return (
        patch.object(download_service.threading, "Thread", InlineThread),
        patch.object(
            download_service.urllib.request,
            "urlopen",
            return_value=FakeHttpResponse(payload),
        ),
    )


def test_model_download_completes_and_marks_installed(download_client) -> None:
    client, storage_path = download_client
    thread_patch, urlopen_patch = _patch_download()

    with (
        thread_patch,
        urlopen_patch,
        patch.dict(
            "app.services.model_download_service.MODEL_DOWNLOAD_SOURCES",
            {"realesrgan-x2": {"url": "https://example.test/x2.pth", "sha256": FAKE_SHA256}},
            clear=True,
        ),
    ):
        start_response = client.post("/api/models/realesrgan-x2/download")
        progress_response = client.get("/api/models/realesrgan-x2/download/progress")

    assert start_response.status_code == 202
    assert start_response.json()["already_installed"] is False
    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "completed"
    assert progress_response.json()["percent"] == 100.0

    model_file = storage_path / "models" / "realesrgan" / "realesrgan-x2.pth"
    assert model_file.exists()
    assert model_file.read_bytes() == FAKE_WEIGHTS

    models_response = client.get("/api/models/realesrgan-x2")
    assert models_response.json()["is_installed"] is True


def test_model_download_fails_on_checksum_mismatch(download_client) -> None:
    client, storage_path = download_client
    thread_patch, urlopen_patch = _patch_download()

    with (
        thread_patch,
        urlopen_patch,
        patch.dict(
            "app.services.model_download_service.MODEL_DOWNLOAD_SOURCES",
            {
                "realesrgan-x2": {
                    "url": "https://example.test/x2.pth",
                    "sha256": "0" * 64,
                }
            },
            clear=True,
        ),
    ):
        start_response = client.post("/api/models/realesrgan-x2/download")
        progress_response = client.get("/api/models/realesrgan-x2/download/progress")

    assert start_response.status_code == 202
    assert progress_response.json()["status"] == "failed"
    assert progress_response.json()["error_code"] == "download_checksum_mismatch"

    model_dir = storage_path / "models" / "realesrgan"
    assert not (model_dir / "realesrgan-x2.pth").exists()
    assert not (model_dir / "realesrgan-x2.pth.part").exists()


def test_model_download_reports_failed_when_post_processing_fails(download_client) -> None:
    client, _ = download_client
    thread_patch, urlopen_patch = _patch_download()

    with (
        thread_patch,
        urlopen_patch,
        patch.dict(
            "app.services.model_download_service.MODEL_DOWNLOAD_SOURCES",
            {"realesrgan-x2": {"url": "https://example.test/x2.pth", "sha256": FAKE_SHA256}},
            clear=True,
        ),
        patch(
            "app.services.model_download_service._refresh_after_download",
            side_effect=RuntimeError("registry refresh exploded"),
        ),
    ):
        client.post("/api/models/realesrgan-x2/download")
        progress_response = client.get("/api/models/realesrgan-x2/download/progress")

    assert progress_response.json()["status"] == "failed"
    assert progress_response.json()["error_code"] == "download_post_process_failed"
    assert "registry refresh exploded" in progress_response.json()["error_message"]


def test_model_download_returns_already_installed(download_client) -> None:
    client, storage_path = download_client
    model_file = storage_path / "models" / "realesrgan" / "realesrgan-x2.pth"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(b"weights")
    refresh = client.post("/api/models/refresh")
    assert refresh.status_code == 200

    response = client.post("/api/models/realesrgan-x2/download")

    assert response.status_code == 202
    assert response.json()["already_installed"] is True
    assert response.json()["status"] == "completed"


def test_model_download_unknown_slug_returns_404(download_client) -> None:
    client, _ = download_client

    response = client.post("/api/models/unknown-model/download")

    assert response.status_code == 404
    assert response.json()["error"] == "ai_model_not_found"


def test_model_download_without_source_returns_400(download_client) -> None:
    client, _ = download_client

    with patch.dict(
        "app.services.model_download_service.MODEL_DOWNLOAD_SOURCES",
        {},
        clear=True,
    ):
        response = client.post("/api/models/realesrgan-x2/download")

    assert response.status_code == 400
    assert response.json()["error"] == "download_source_not_configured"


def test_second_download_while_running_returns_409(download_client) -> None:
    client, _ = download_client
    release = threading.Event()
    started = threading.Event()

    class BlockingResponse(FakeHttpResponse):
        def read(self, *args: object) -> bytes:
            started.set()
            release.wait(timeout=5)
            return super().read(*args)

    with (
        patch.object(
            download_service.urllib.request,
            "urlopen",
            return_value=BlockingResponse(FAKE_WEIGHTS),
        ),
        patch.dict(
            "app.services.model_download_service.MODEL_DOWNLOAD_SOURCES",
            {"realesrgan-x2": {"url": "https://example.test/x2.pth", "sha256": FAKE_SHA256}},
            clear=True,
        ),
    ):
        first = client.post("/api/models/realesrgan-x2/download")
        assert first.status_code == 202
        assert started.wait(timeout=5)

        second = client.post("/api/models/realesrgan-x2/download")
        release.set()

    assert second.status_code == 409
    assert second.json()["error"] == "download_already_running"
