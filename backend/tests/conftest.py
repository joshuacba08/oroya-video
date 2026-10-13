import os
import tempfile

import pytest

# Antes de importar la app: ningún test puede tocar el almacenamiento real del desarrollador
# (backend/storage). Los tests que necesitan rutas propias pasan Settings(storage_path=...).
_TEST_STORAGE = tempfile.mkdtemp(prefix="oroya-tests-")
os.environ["STORAGE_PATH"] = _TEST_STORAGE
os.environ.pop("DATABASE_URL", None)


@pytest.fixture(autouse=True)
def _isolate_frame_enhancer_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite hermetic: ignore the developer's local backend/.env engine.

    Environment variables take precedence over dotenv values in pydantic-settings,
    so tests always run with the mock enhancer unless a test passes
    frame_enhancer_engine explicitly to Settings.
    """
    monkeypatch.setenv("FRAME_ENHANCER_ENGINE", "mock")
    monkeypatch.delenv("OROYA_DATA_DIR", raising=False)
    # Las pruebas de etapas (extracción, mejora, encode…) son del pipeline clásico; las del
    # streaming pasan Settings(pipeline_mode="streaming") (tests/test_streaming_pipeline.py).
    monkeypatch.setenv("PIPELINE_MODE", "legacy")


@pytest.fixture(autouse=True)
def _no_desktop_open(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Never launch real apps/explorer windows from tests; record the calls instead."""
    from app.services import desktop_open_service

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        desktop_open_service, "open_file", lambda path: calls.append(("open", str(path))) or True
    )
    monkeypatch.setattr(
        desktop_open_service,
        "reveal_in_folder",
        lambda path: calls.append(("reveal", str(path))) or True,
    )
    return calls


@pytest.fixture(autouse=True)
def _assume_realesrgan_packages_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite must not depend on the optional AI stack (torch/basicsr) being installed.

    Tests that check the missing-packages path patch this function themselves.
    """
    monkeypatch.setattr(
        "app.services.realesrgan_service.get_missing_realesrgan_modules", lambda: []
    )
    monkeypatch.setattr("app.services.realesrgan_service.get_missing_spandrel_modules", lambda: [])
    monkeypatch.setattr("app.services.ai_runtime_service.get_missing_spandrel_modules", lambda: [])


@pytest.fixture(autouse=True)
def _clear_enhancer_cache():
    """The loaded Real-ESRGAN model is cached across jobs; never across tests."""
    from app.services import realesrgan_service

    realesrgan_service._enhancer_cache.clear()
    realesrgan_service._spandrel_cache.clear()
    yield
    realesrgan_service._enhancer_cache.clear()
    realesrgan_service._spandrel_cache.clear()


@pytest.fixture(autouse=True)
def _assume_face_restore_packages_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Like the Real-ESRGAN check: tests must not depend on gfpgan/facexlib being installed."""
    monkeypatch.setattr(
        "app.services.ai_runtime_service.get_missing_face_restore_modules", lambda: []
    )


@pytest.fixture(autouse=True)
def _no_real_videos_folder(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> None:
    """With OROYA_DATA_DIR the export folder defaults to the user's Videos folder: never the
    real one in tests."""
    videos = tmp_path_factory.mktemp("videos")
    monkeypatch.setattr("app.core.config.default_videos_dir", lambda: videos)
