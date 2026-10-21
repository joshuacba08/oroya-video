from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings
from app.services import ai_runtime_service


def _prepare(tmp_path: Path) -> Settings:
    (tmp_path / "ai-env" / "numpy").mkdir(parents=True)
    (tmp_path / "ai-env" / "numpy" / "old.pyd").write_text("old", encoding="utf-8")
    (tmp_path / "ai-env.staging" / "numpy").mkdir(parents=True)
    (tmp_path / "ai-env.staging" / "numpy" / "new.pyd").write_text("new", encoding="utf-8")
    (tmp_path / "ai-env.pending").write_text("ready\n", encoding="utf-8")
    return Settings(ai_extra_site_dir=str(tmp_path / "ai-env"))


def test_pending_runtime_is_switched_in_at_startup(tmp_path: Path) -> None:
    settings = _prepare(tmp_path)

    assert ai_runtime_service.apply_pending_ai_env(settings) is True

    assert (tmp_path / "ai-env" / "numpy" / "new.pyd").is_file()
    assert not (tmp_path / "ai-env.staging").exists()
    assert not (tmp_path / "ai-env.pending").exists()
    # La carpeta sustituida se borra.
    assert list(tmp_path.glob("ai-env.old-*")) == []


def test_nothing_changes_without_a_pending_install(tmp_path: Path) -> None:
    settings = _prepare(tmp_path)
    (tmp_path / "ai-env.pending").unlink()

    assert ai_runtime_service.apply_pending_ai_env(settings) is False
    assert (tmp_path / "ai-env" / "numpy" / "old.pyd").is_file()


def test_first_install_has_no_previous_runtime(tmp_path: Path) -> None:
    settings = _prepare(tmp_path)
    (tmp_path / "ai-env" / "numpy" / "old.pyd").unlink()
    (tmp_path / "ai-env" / "numpy").rmdir()
    (tmp_path / "ai-env").rmdir()

    assert ai_runtime_service.apply_pending_ai_env(settings) is True
    assert (tmp_path / "ai-env" / "numpy" / "new.pyd").is_file()


def test_failed_switch_keeps_the_previous_runtime(tmp_path: Path) -> None:
    settings = _prepare(tmp_path)
    real_rename = Path.rename

    def rename(self: Path, target):
        if self.name == "ai-env.staging":
            raise PermissionError("locked by antivirus")
        return real_rename(self, target)

    with (
        patch.object(Path, "rename", rename),
        patch.object(ai_runtime_service.time, "sleep"),
    ):
        assert ai_runtime_service.apply_pending_ai_env(settings) is False

    assert (tmp_path / "ai-env" / "numpy" / "old.pyd").is_file()
    # Se reintenta en el próximo arranque.
    assert (tmp_path / "ai-env.pending").is_file()
    assert (tmp_path / "ai-env.staging").is_dir()


def test_startup_applies_the_pending_runtime(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}",
        ai_extra_site_dir=str(tmp_path / "ai-env"),
    )
    _prepare(tmp_path)
    with TestClient(create_app(settings)):
        pass
    assert (tmp_path / "ai-env" / "numpy" / "new.pyd").is_file()
