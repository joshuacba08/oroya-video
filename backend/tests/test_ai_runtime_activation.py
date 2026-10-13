import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.services import settings_service
from app.services.ai_runtime_service import ensure_ai_extra_site_dir


@pytest.fixture
def clean_sys_path():
    saved = list(sys.path)
    yield
    sys.path[:] = saved
    sys.modules.pop("late_ai_module", None)


def test_pth_files_added_after_registration_are_processed(tmp_path, clean_sys_path) -> None:
    """The AI install adds setuptools' .pth (it provides `distutils`, gone in Python 3.12) to a
    folder that may already be registered from an earlier attempt: it must still take effect."""
    site_dir = tmp_path / "ai-env"
    site_dir.mkdir()
    settings = Settings(storage_path=str(tmp_path / "storage"), ai_extra_site_dir=str(site_dir))
    ensure_ai_extra_site_dir(settings)

    extra = tmp_path / "provided-by-pth"
    extra.mkdir()
    (extra / "late_ai_module.py").write_text("VALUE = 42\n", encoding="utf-8")
    (site_dir / "late.pth").write_text(f"{extra}\n", encoding="utf-8")
    ensure_ai_extra_site_dir(settings)

    assert importlib.import_module("late_ai_module").VALUE == 42


def _desktop_settings(tmp_path: Path) -> Settings:
    (tmp_path / "data" / "ai-env").mkdir(parents=True)
    return Settings(oroya_data_dir=str(tmp_path / "data"), frame_enhancer_engine="mock")


def test_a_working_ai_runtime_replaces_the_mock_engine(tmp_path, clean_sys_path) -> None:
    settings = _desktop_settings(tmp_path)

    with patch("app.services.ai_runtime_service.get_missing_realesrgan_modules", return_value=[]):
        assert settings_service.activate_installed_ai_runtime(settings)

    assert settings.frame_enhancer_engine == "realesrgan"
    saved = json.loads(settings_service._get_settings_file(settings).read_text(encoding="utf-8"))
    assert saved["processing"]["frame_enhancer_engine"] == "realesrgan"


def test_the_engine_is_kept_when_the_runtime_is_broken_or_mock_was_chosen(
    tmp_path, clean_sys_path
) -> None:
    settings = _desktop_settings(tmp_path)
    with patch(
        "app.services.ai_runtime_service.get_missing_realesrgan_modules", return_value=["basicsr"]
    ):
        assert not settings_service.activate_installed_ai_runtime(settings)
    assert settings.frame_enhancer_engine == "mock"

    settings_service.set_frame_enhancer_engine("mock", settings)
    with patch("app.services.ai_runtime_service.get_missing_realesrgan_modules", return_value=[]):
        assert not settings_service.activate_installed_ai_runtime(settings)
    assert settings.frame_enhancer_engine == "mock"
