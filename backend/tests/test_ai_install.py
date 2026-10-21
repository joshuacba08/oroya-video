import subprocess
import sys
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


def _run(
    settings: Settings,
    returncodes: list[int],
    installed_after: bool = True,
    verify_error: str | None = None,
):
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
        patch.object(ai_install_service, "_verify_runtime", return_value=verify_error),
        patch.object(ai_install_service.ai_runtime_service, "ensure_ai_extra_site_dir"),
    ):
        ai_install_service._run_install(settings, lambda: Path("C:/wheels/basicsr.whl"))
    return calls, ai_install_service.get_ai_install_progress()


def test_install_goes_to_a_staging_folder_and_waits_for_a_restart(tmp_path: Path) -> None:
    target = tmp_path / "ai-env"
    staging = tmp_path / "ai-env.staging"
    # Runtime en uso (con sus DLL bloqueadas en Windows): la instalación no lo toca.
    (target / "numpy").mkdir(parents=True)
    (staging / "leftover").mkdir(parents=True)
    calls, progress = _run(_settings(tmp_path), [0, 0, 0])

    assert progress.status == "completed"
    assert progress.restart_required is True
    assert progress.percent == 100.0
    assert len(calls) == 3
    torch_cmd, deps_env = calls[0][0], calls[0][1]
    assert ["--target", str(staging)] == torch_cmd[torch_cmd.index("--target") :][:2]
    assert all(str(target) != part for command, _ in calls for part in command)
    assert torch_cmd[-2:] == ["--index-url", ai_install_service.TORCH_INDEX_CUDA]
    assert set(ai_install_service.TORCH_PACKAGES) <= set(torch_cmd)
    # Versiones fijadas: una publicación nueva de PyTorch no cambia lo que se instala.
    assert all("==" in package for package in ai_install_service.TORCH_PACKAGES)
    ai_cmd = calls[1][0]
    assert "--no-deps" in ai_cmd
    assert str(Path("C:/wheels/basicsr.whl")) in ai_cmd
    assert "realesrgan==0.3.0" in ai_cmd
    assert "tb-nightly" not in calls[2][0]
    # pip sees packages already in the staging folder as installed.
    assert deps_env["PYTHONPATH"].split(ai_install_service.os.pathsep)[0] == str(staging)
    assert not (staging / "leftover").exists()
    assert (target / "numpy").is_dir()
    assert (tmp_path / "ai-env.pending").is_file()


def test_every_package_is_pinned_once() -> None:
    # torch va con --no-deps y sus dependencias fijadas aquí: antes, el paso de PyTorch traía
    # el numpy más reciente y el de dependencias otro, y quedaban dos versiones mezcladas.
    steps = ai_install_service.build_install_steps(
        "C:/ai-env.staging", ai_install_service.TORCH_INDEX_CUDA, Path("basicsr.whl")
    )
    assert "--no-deps" in steps[0][1]
    packages = [
        *ai_install_service.TORCH_PACKAGES,
        *ai_install_service.AI_PACKAGES,
        *ai_install_service.AI_DEPENDENCIES,
    ]
    names = [package.split("==")[0].lower() for package in packages]
    assert all("==" in package for package in packages)
    assert len(names) == len(set(names))
    assert {"numpy", "filelock", "sympy", "networkx", "jinja2", "fsspec"} <= set(names)


def test_failed_verification_keeps_the_current_runtime(tmp_path: Path) -> None:
    _, progress = _run(_settings(tmp_path), [0, 0, 0], verify_error="No module named 'cv2'")

    assert progress.status == "failed"
    assert progress.error_code == "ai_install_verification_failed"
    assert "cv2" in progress.error_message
    assert not (tmp_path / "ai-env.pending").exists()


def test_verify_runtime_runs_in_a_separate_process(tmp_path: Path) -> None:
    failed = subprocess.CompletedProcess([], 1, "", "Traceback\nImportError: numpy broken\n")
    with patch.object(ai_install_service.subprocess, "run", return_value=failed) as run:
        assert ai_install_service._verify_runtime(tmp_path) == "ImportError: numpy broken"
    command = run.call_args.args[0]
    assert command[:2] == [sys.executable, "-I"]
    assert str(tmp_path) in command
    assert "realesrgan" in command and "spandrel" in command


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


def test_install_fails_when_runtime_cannot_be_imported_afterwards() -> None:
    # Sin carpeta propia (desarrollo): se instala en el entorno del backend y se comprueba ahí.
    with patch.object(
        ai_install_service.ai_runtime_service,
        "get_missing_realesrgan_modules",
        return_value=["basicsr"],
    ):
        _, progress = _run(Settings(ai_extra_site_dir=None), [0, 0, 0], False)

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
    assert start.json() == {
        "status": "completed",
        "already_installed": True,
        "restart_required": False,
    }
    assert progress.json()["status"] == "completed"


def test_start_reports_a_pending_runtime_instead_of_reinstalling(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (tmp_path / "ai-env.staging").mkdir()
    (tmp_path / "ai-env.pending").write_text("ready\n", encoding="utf-8")
    with patch.object(ai_install_service, "is_ai_stack_installed") as installed:
        started = ai_install_service.start_ai_install(settings)

    assert started.restart_required is True
    assert started.status == "completed"
    installed.assert_not_called()
    assert ai_install_service.get_ai_install_progress().restart_required is True


def test_a_second_click_joins_the_running_install(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    ai_install_service._set_state(status="installing")
    with patch.object(ai_install_service.threading, "Thread") as thread:
        started = ai_install_service.start_ai_install(settings)

    assert started.status == "installing"
    thread.assert_not_called()


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
