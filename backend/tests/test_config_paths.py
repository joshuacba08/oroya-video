import hashlib
import io
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.paths import get_data_bin_path
from app.main import create_app
from app.services import download_service
from app.services.tool_detection_service import resolve_tool_path


class InlineThread(threading.Thread):
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


def test_oroya_data_dir_redirects_storage_and_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # conftest fija STORAGE_PATH para aislar la suite; aquí se prueban los valores por defecto.
    monkeypatch.delenv("STORAGE_PATH", raising=False)
    data_dir = tmp_path / "oroya-data"
    settings = Settings(oroya_data_dir=str(data_dir))

    assert settings.storage_path == str(data_dir / "storage")
    assert settings.database_url == (
        f"sqlite:///{(data_dir / 'storage' / 'db' / 'oroya-video.sqlite').as_posix()}"
    )
    assert settings.ai_extra_site_dir == str(data_dir / "ai-env")
    assert get_data_bin_path(settings) == data_dir / "bin"


def test_oroya_data_dir_respects_explicit_overrides(tmp_path: Path) -> None:
    data_dir = tmp_path / "oroya-data"
    custom_storage = tmp_path / "custom-storage"
    settings = Settings(
        oroya_data_dir=str(data_dir),
        storage_path=str(custom_storage),
        database_url="sqlite:///C:/custom/oroya.sqlite",
    )

    assert settings.storage_path == str(custom_storage)
    assert settings.database_url == "sqlite:///C:/custom/oroya.sqlite"


def test_defaults_unchanged_without_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STORAGE_PATH", raising=False)
    settings = Settings()

    assert settings.oroya_data_dir is None
    assert settings.storage_path == "storage"
    assert settings.database_url == "sqlite:///storage/db/oroya-video.sqlite"
    assert settings.ai_extra_site_dir is None


def test_resolve_tool_path_prefers_data_bin(tmp_path: Path) -> None:
    data_dir = tmp_path / "oroya-data"
    bin_dir = data_dir / "bin"
    bin_dir.mkdir(parents=True)
    fake_ffmpeg = bin_dir / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"exe")
    settings = Settings(oroya_data_dir=str(data_dir))

    with patch("app.services.tool_detection_service.shutil.which", return_value="C:/path/ffmpeg"):
        assert resolve_tool_path("ffmpeg", settings) == str(fake_ffmpeg)
        assert resolve_tool_path("ffprobe", settings) == "C:/path/ffmpeg"


def _build_ffmpeg_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe", b"ffmpeg-bin")
        archive.writestr("ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe", b"ffprobe-bin")
        archive.writestr("ffmpeg-master-latest-win64-gpl/LICENSE.txt", b"gpl")
    return buffer.getvalue()


@pytest.fixture
def setup_client(tmp_path: Path):
    data_dir = tmp_path / "oroya-data"
    settings = Settings(
        oroya_data_dir=str(data_dir),
        database_url=f"sqlite:///{(tmp_path / 'setup.sqlite').as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, data_dir

    download_service.reset_download_state("tool:ffmpeg")


def test_ffmpeg_download_extracts_binaries_to_data_bin(setup_client) -> None:
    client, data_dir = setup_client
    archive = _build_ffmpeg_zip()

    with (
        patch.object(download_service.threading, "Thread", InlineThread),
        patch.object(
            download_service.urllib.request,
            "urlopen",
            return_value=FakeHttpResponse(archive),
        ),
        patch("app.services.system_setup_service.resolve_tool_path", return_value=None),
        patch(
            "app.services.system_setup_service.FFMPEG_SHA256",
            hashlib.sha256(archive).hexdigest(),
        ),
    ):
        start_response = client.post("/api/system/ffmpeg/download")

    progress_response = client.get("/api/system/ffmpeg/download/progress")

    assert start_response.status_code == 202
    assert progress_response.json()["status"] == "completed"
    assert (data_dir / "bin" / "ffmpeg.exe").read_bytes() == b"ffmpeg-bin"
    assert (data_dir / "bin" / "ffprobe.exe").read_bytes() == b"ffprobe-bin"
    assert not (data_dir / "bin" / "ffmpeg-download.zip").exists()


def test_ffmpeg_download_reports_already_installed(setup_client) -> None:
    client, data_dir = setup_client
    bin_dir = data_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "ffmpeg.exe").write_bytes(b"exe")
    (bin_dir / "ffprobe.exe").write_bytes(b"exe")

    response = client.post("/api/system/ffmpeg/download")

    assert response.status_code == 202
    assert response.json()["already_installed"] is True
    assert response.json()["status"] == "completed"


def test_ffmpeg_download_rejects_an_archive_with_another_checksum(setup_client) -> None:
    client, data_dir = setup_client

    with (
        patch.object(download_service.threading, "Thread", InlineThread),
        patch.object(
            download_service.urllib.request,
            "urlopen",
            return_value=FakeHttpResponse(_build_ffmpeg_zip()),
        ),
        patch("app.services.system_setup_service.resolve_tool_path", return_value=None),
    ):
        client.post("/api/system/ffmpeg/download")

    progress = client.get("/api/system/ffmpeg/download/progress").json()
    assert progress["status"] == "failed"
    assert not (data_dir / "bin" / "ffmpeg.exe").exists()


def test_custom_storage_path_moves_the_default_database(tmp_path, monkeypatch) -> None:
    # Aunque el .env repita DATABASE_URL con su valor por defecto.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///storage/db/oroya-video.sqlite")
    settings = Settings(storage_path=str(tmp_path / "e2e-storage"))

    assert settings.database_url == (
        f"sqlite:///{(tmp_path / 'e2e-storage' / 'db' / 'oroya-video.sqlite').as_posix()}"
    )
