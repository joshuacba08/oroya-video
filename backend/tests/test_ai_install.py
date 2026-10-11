from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import ai_install_service, ai_wheel_builder


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):
        yield from self._lines


class FakePopen:
    def __init__(self, returncode: int, lines: list[str]) -> None:
        self.returncode = returncode
        self.stdout = FakeStdout(lines)

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


@pytest.fixture(autouse=True)
def _reset_state():
    ai_install_service.reset_ai_install_state()
    yield
    ai_install_service.reset_ai_install_state()


def _settings(tmp_path: Path, **overrides) -> Settings:
    # storage_path propio: el install exitoso persiste el motor en settings.json.
    return Settings(
        ai_extra_site_dir=str(tmp_path / "ai-env"),
        storage_path=str(tmp_path / "storage"),
        **overrides,
    )


def _run(settings: Settings, returncodes: list[int], installed_after: bool = True):
    calls: list[tuple[list[str], dict[str, str]]] = []

    def popen(command, **kwargs):
        calls.append((command, kwargs["env"]))
        return FakePopen(returncodes[len(calls) - 1], [f"step {len(calls)} output\n"])

    with (
        patch.object(ai_install_service.subprocess, "Popen", side_effect=popen),
        patch.object(
            ai_install_service,
            "resolve_torch_index_url",
            return_value=ai_install_service.TORCH_INDEX_CUDA,
        ),
        patch.object(ai_install_service, "is_ai_stack_installed", return_value=installed_after),
        patch.object(ai_install_service.ai_runtime_service, "ensure_ai_extra_site_dir"),
    ):
        ai_install_service._run_install(settings, lambda: Path("C:/wheels/basicsr.whl"))
    return calls, ai_install_service.get_ai_install_progress()


def test_install_runs_three_pip_steps_into_the_ai_target(tmp_path: Path) -> None:
    target = tmp_path / "ai-env"
    calls, progress = _run(_settings(tmp_path), [0, 0, 0])

    assert progress.status == "completed"
    assert progress.percent == 100.0
    assert len(calls) == 3
    torch_cmd, deps_env = calls[0][0], calls[0][1]
    assert ["--target", str(target)] == torch_cmd[torch_cmd.index("--target") :][:2]
    assert torch_cmd[-2:] == ["--index-url", ai_install_service.TORCH_INDEX_CUDA]
    assert {"torch", "torchvision"} <= set(torch_cmd)
    ai_cmd = calls[1][0]
    assert "--no-deps" in ai_cmd
    assert str(Path("C:/wheels/basicsr.whl")) in ai_cmd
    assert "realesrgan==0.3.0" in ai_cmd
    assert "tb-nightly" not in calls[2][0]
    # pip sees packages already in the target as installed.
    assert deps_env["PYTHONPATH"].split(ai_install_service.os.pathsep)[0] == str(target)
    assert target.is_dir()


def test_successful_install_switches_mock_engine_to_realesrgan(tmp_path: Path) -> None:
    settings = _settings(tmp_path, frame_enhancer_engine="mock")

    _, progress = _run(settings, [0, 0, 0])

    assert progress.status == "completed"
    assert settings.frame_enhancer_engine == "realesrgan"
    persisted = (tmp_path / "storage" / "settings.json").read_text(encoding="utf-8")
    assert '"frame_enhancer_engine": "realesrgan"' in persisted


def test_install_reports_the_failing_step(tmp_path: Path) -> None:
    calls, progress = _run(_settings(tmp_path), [0, 1, 0])

    assert len(calls) == 2
    assert progress.status == "failed"
    assert progress.error_code == "ai_install_failed"
    assert progress.error_message.startswith("Real-ESRGAN install failed")
    assert progress.output_tail == ["step 2 output"]


def test_install_fails_when_runtime_cannot_be_imported_afterwards(tmp_path: Path) -> None:
    with patch.object(
        ai_install_service.ai_runtime_service,
        "get_missing_realesrgan_modules",
        return_value=["basicsr"],
    ):
        _, progress = _run(_settings(tmp_path), [0, 0, 0], False)

    assert progress.status == "failed"
    assert progress.error_code == "ai_install_verification_failed"
    assert "basicsr" in progress.error_message


def test_install_without_target_uses_backend_environment() -> None:
    steps = ai_install_service.build_install_steps(
        None, ai_install_service.TORCH_INDEX_CPU, Path("basicsr.whl")
    )
    assert all("--target" not in command for _, command in steps)
    env = ai_install_service._pip_env(None)
    assert env.get("PYTHONPATH") == ai_install_service.os.environ.get("PYTHONPATH")


def test_ai_install_endpoints_report_already_installed(tmp_path: Path) -> None:
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'ai.sqlite').as_posix()}",
    )
    with (
        TestClient(create_app(settings)) as client,
        patch.object(ai_install_service, "is_ai_stack_installed", return_value=True),
    ):
        start = client.post("/api/v1/system/ai/install")
        progress = client.get("/api/v1/system/ai/install/progress")

    assert start.status_code == 202
    assert start.json() == {"status": "completed", "already_installed": True}
    assert progress.json()["status"] == "completed"


def _fake_basicsr_tree(root: Path) -> Path:
    source = root / "basicsr-1.4.2"
    (source / "basicsr" / "data").mkdir(parents=True)
    (source / "setup.py").write_text(
        "import os\n\n"
        + ai_wheel_builder._ORIGINAL_GET_VERSION
        + "\nsetup(\n"
        + ai_wheel_builder._ORIGINAL_SETUP_REQUIRES
        + ")\n",
        encoding="utf-8",
    )
    (source / "basicsr" / "data" / "degradations.py").write_text(
        ai_wheel_builder._ORIGINAL_TV_IMPORT + "\n", encoding="utf-8"
    )
    (source / "requirements.txt").write_text("numpy\ntb-nightly\ntorch>=1.7\n", encoding="utf-8")
    return source


def test_patch_basicsr_source_fixes_build_and_import_issues(tmp_path: Path) -> None:
    source = _fake_basicsr_tree(tmp_path)

    ai_wheel_builder.patch_basicsr_source(source)

    setup_py = (source / "setup.py").read_text(encoding="utf-8")
    assert "exec(" not in setup_py
    assert "setup_requires" not in setup_py
    assert "functional_tensor" not in (source / "basicsr" / "data" / "degradations.py").read_text(
        encoding="utf-8"
    )
    assert "tb-nightly" not in (source / "requirements.txt").read_text(encoding="utf-8")


def test_patch_basicsr_source_rejects_unexpected_layout(tmp_path: Path) -> None:
    source = _fake_basicsr_tree(tmp_path)
    (source / "setup.py").write_text("setup()\n", encoding="utf-8")

    with pytest.raises(ai_wheel_builder.BasicsrWheelBuildError):
        ai_wheel_builder.patch_basicsr_source(source)
