"""One-click install of the AI stack (PyTorch + Real-ESRGAN) from the setup wizard.

The installed app ships only the core backend. The AI stack is large and depends on the
GPU, so it is installed on demand with the backend's own interpreter (packages must match
its Python version) into `ai_extra_site_dir` (pip --target). In development, where that
directory is not configured, it installs into the backend's environment.

With a target, everything goes into a fresh `<target>.staging` folder, never into the one
in use: Windows keeps the DLLs the backend has loaded (numpy, torch...) locked, and pip left
the runtime half deleted. The new runtime is checked in a separate process and switched in
when the backend restarts (ai_runtime_service.apply_pending_ai_env). Downloads come from
pip's cache, so repairing or updating does not download everything again.

Steps (run with PYTHONPATH=<folder> so pip treats already-installed packages as present):
1. torch + torchvision from the PyTorch index (CUDA build if an NVIDIA GPU is detected).
2. basicsr/realesrgan with --no-deps (basicsr from our patched wheel, see ai_wheel_builder).
3. Every dependency, pinned (torch's too: otherwise step 1 pulled the newest numpy and
   step 3 left two versions side by side).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import get_temp_path
from app.schemas.system_schema import AIInstallProgressResponse, AIInstallStartResponse
from app.services import ai_runtime_service, ai_wheel_builder, settings_service
from app.services.gpu_detection_service import get_gpu_status

logger = get_logger(__name__)

TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu132"
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"
# Versiones fijadas: la combinación probada con GPU (RTX 50, CUDA 13.2). Sin fijarlas, cada
# usuario recibía lo último publicado y una versión nueva podía romper instalaciones de
# versiones ya distribuidas de la app. Existen ruedas cp312 win_amd64 en cu132 y cpu.
TORCH_PACKAGES = ("torch==2.12.1", "torchvision==0.27.1")
AI_PACKAGES = (
    "realesrgan==0.3.0",
    "gfpgan==1.3.8",
    "facexlib==0.3.0",
    # Modelos modernos (RealPLKSR, SPAN…), REQ-039. Sus dependencias van en AI_DEPENDENCIES.
    "spandrel==0.4.2",
)
# Dependencias de basicsr/realesrgan (sin torch ni tb-nightly).
AI_DEPENDENCIES = (
    "addict==2.4.0",
    "setuptools==70.2.0",  # basicsr importa distutils; setuptools lo provee en Python 3.12+
    "future==1.0.0",
    "lmdb==2.2.1",
    "numpy==2.4.4",
    "opencv-python==4.13.0.92",
    "Pillow==12.2.0",
    "pyyaml==6.0.3",
    "requests==2.34.2",
    "scikit-image==0.26.0",
    "scipy==1.18.0",
    "tqdm==4.68.3",
    "yapf==0.43.0",
    # facexlib (detección de caras para GFPGAN)
    "filterpy==1.4.5",
    "numba==0.65.1",
    # spandrel
    "einops==0.8.2",
    "safetensors==0.8.0",
    # torch / torchvision (se instalan con --no-deps)
    "filelock==3.32.3",
    "fsspec==2026.7.0",
    "jinja2==3.1.6",
    "markupsafe==3.0.3",
    "mpmath==1.3.0",
    "networkx==3.6.1",
    "sympy==1.14.0",
    "typing-extensions==4.16.0",
)
# Comprobación del runtime nuevo en otro proceso: el backend ya tiene cargado el anterior.
VERIFY_TIMEOUT_SECONDS = 600
_VERIFY_SCRIPT = """
import importlib, site, sys
site.addsitedir(sys.argv[1])
import torchvision.transforms.functional as functional
sys.modules.setdefault("torchvision.transforms.functional_tensor", functional)
for name in sys.argv[2:]:
    importlib.import_module(name)
"""
# Wheels empaquetados por scripts/build_installer.ps1 (resources/backend/wheels).
BUNDLED_WHEELS_DIR = BACKEND_ROOT / "wheels"
OUTPUT_TAIL_LINES = 20


@dataclass
class AIInstallState:
    status: str = "idle"  # idle | installing | completed | failed
    step: int = 0
    steps_total: int = 3
    step_label: str = ""
    message: str = ""
    error_code: str | None = None
    error_message: str | None = None
    output_tail: list[str] = field(default_factory=list)
    restart_required: bool = False


_state = AIInstallState()
_lock = threading.Lock()
# Comprobar si ya está instalado tarda unos segundos (importa torch): un doble clic no debe
# lanzar dos instalaciones ni responder con un error al segundo.
_start_lock = threading.Lock()


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _set_state(**changes: object) -> None:
    with _lock:
        for name, value in changes.items():
            setattr(_state, name, value)


def _snapshot() -> AIInstallState:
    with _lock:
        return AIInstallState(**{**_state.__dict__, "output_tail": list(_state.output_tail)})


def reset_ai_install_state() -> None:
    global _state
    with _lock:
        _state = AIInstallState()


def is_ai_stack_installed() -> bool:
    return (
        ai_runtime_service.is_torch_available()
        and not ai_runtime_service.get_missing_realesrgan_modules()
        and not ai_runtime_service.get_missing_face_restore_modules()
        # Componentes añadidos en versiones nuevas (spandrel, 0.6): si faltan, se reinstala,
        # y pip solo baja lo que falta (PYTHONPATH apunta a lo ya instalado).
        and not ai_runtime_service.get_missing_spandrel_modules()
    )


def resolve_torch_index_url() -> str:
    gpu = get_gpu_status()
    return TORCH_INDEX_CUDA if gpu.available else TORCH_INDEX_CPU


def _pip_base(target: str | None) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-input",
        "--disable-pip-version-check",
    ]
    if target:
        command += ["--target", target]
    return command


def build_install_steps(
    target: str | None,
    torch_index_url: str,
    basicsr_wheel: Path,
) -> list[tuple[str, list[str]]]:
    base = _pip_base(target)
    return [
        ("PyTorch", [*base, "--no-deps", *TORCH_PACKAGES, "--index-url", torch_index_url]),
        ("Real-ESRGAN", [*base, "--no-deps", str(basicsr_wheel), *AI_PACKAGES]),
        ("Dependencies", [*base, *AI_DEPENDENCIES]),
    ]


def _pip_env(target: str | None) -> dict[str, str]:
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PIP_NO_INPUT": "1"}
    if target:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = target if not existing else f"{target}{os.pathsep}{existing}"
    return env


def _run_step(command: list[str], env: dict[str, str]) -> tuple[int, list[str]]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    tail: list[str] = []
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        tail = [*tail, line][-OUTPUT_TAIL_LINES:]
        _set_state(message=line[:300], output_tail=tail)
    return process.wait(), tail


def _prepare_staging(target: Path) -> Path:
    staging = ai_runtime_service.get_ai_env_staging_dir(target)
    ai_runtime_service.get_ai_env_pending_marker(target).unlink(missing_ok=True)
    if staging.exists():
        shutil.rmtree(staging)  # restos de un intento anterior: nadie los tiene cargados
    staging.mkdir(parents=True)
    return staging


def _verify_runtime(site_dir: Path) -> str | None:
    """Error message when the runtime in `site_dir` cannot be imported, else None."""
    modules = (
        *ai_runtime_service.REALESRGAN_RUNTIME_MODULES,
        *ai_runtime_service.FACE_RESTORE_RUNTIME_MODULES,
        *ai_runtime_service.SPANDREL_RUNTIME_MODULES,
    )
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _VERIFY_SCRIPT, str(site_dir), *modules],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if result.returncode == 0:
        return None
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    return lines[-1] if lines else f"exit code {result.returncode}"


def _finish(settings: Settings, *, restart_required: bool) -> None:
    if settings.frame_enhancer_engine.strip().lower() == "mock":
        # Quien instala la IA quiere usarla: no seguir procesando con el motor de prueba.
        settings_service.set_frame_enhancer_engine("realesrgan", settings)
    _set_state(
        status="completed",
        message=(
            "AI runtime installed. Restarting the engine to activate it."
            if restart_required
            else "AI runtime installed."
        ),
        restart_required=restart_required,
    )
    logger.info("AI install completed")


def _run_install(
    settings: Settings,
    resolve_wheel: Callable[[], Path],
) -> None:
    target = Path(settings.ai_extra_site_dir) if settings.ai_extra_site_dir else None
    try:
        _set_state(step_label="Preparing", message="Preparing basicsr package...")
        install_dir = _prepare_staging(target) if target else None
        basicsr_wheel = resolve_wheel()
        pip_target = str(install_dir) if install_dir else None
        steps = build_install_steps(pip_target, resolve_torch_index_url(), basicsr_wheel)
        env = _pip_env(pip_target)
        for index, (label, command) in enumerate(steps, start=1):
            _set_state(step=index, steps_total=len(steps), step_label=label)
            logger.info("AI install step %s/%s: %s", index, len(steps), label)
            return_code, tail = _run_step(command, env)
            if return_code != 0:
                _set_state(
                    status="failed",
                    error_code="ai_install_failed",
                    error_message=f"{label} install failed: {' | '.join(tail[-3:])}"[:500],
                )
                logger.warning("AI install failed at step %s", label)
                return

        if install_dir is not None and target is not None:
            _set_state(step_label="Verifying", message="Checking the new AI runtime...")
            problem = _verify_runtime(install_dir)
            if problem:
                _set_state(
                    status="failed",
                    error_code="ai_install_verification_failed",
                    error_message=(
                        f"Packages installed but the AI runtime could not be imported: {problem}"
                    )[:500],
                )
                return
            # Se activa al reiniciar el backend, antes de que cargue nada del runtime anterior.
            ai_runtime_service.get_ai_env_pending_marker(target).write_text(
                "ready\n", encoding="utf-8"
            )
            _finish(settings, restart_required=True)
            return

        ai_runtime_service.ensure_ai_extra_site_dir(settings)
        if not is_ai_stack_installed():
            missing = ai_runtime_service.get_missing_realesrgan_modules()
            _set_state(
                status="failed",
                error_code="ai_install_verification_failed",
                error_message=(
                    "Packages installed but the AI runtime could not be imported"
                    + (f" ({', '.join(missing)})." if missing else ".")
                ),
            )
            return
        _finish(settings, restart_required=False)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the wizard
        logger.exception("AI install failed")
        _set_state(status="failed", error_code="ai_install_failed", error_message=str(exc)[:500])


def _default_resolve_wheel(settings: Settings) -> Callable[[], Path]:
    def resolve() -> Path:
        bundled = ai_wheel_builder.find_basicsr_wheel(BUNDLED_WHEELS_DIR)
        if bundled is not None:
            return bundled
        # Caché fuera del árbol versionado: storage/temp está en .gitignore.
        cache_dir = get_temp_path(settings) / "wheels"
        return ai_wheel_builder.build_basicsr_wheel(cache_dir)

    return resolve


def start_ai_install(settings: Settings | None = None) -> AIInstallStartResponse:
    active_settings = _get_active_settings(settings)
    installing = AIInstallStartResponse(status="installing", already_installed=False)
    # Un segundo clic mientras se comprueba o se instala se une a la instalación en curso.
    if not _start_lock.acquire(blocking=False):
        return installing
    try:
        if _snapshot().status == "installing":
            return installing
        if ai_runtime_service.is_ai_env_switch_pending(active_settings):
            # Ya instalado y comprobado: solo falta reiniciar el backend para activarlo.
            _set_state(status="completed", message="Restart to activate.", restart_required=True)
            return AIInstallStartResponse(
                status="completed", already_installed=False, restart_required=True
            )
        ai_runtime_service.ensure_ai_extra_site_dir(active_settings)
        if is_ai_stack_installed():
            _set_state(status="completed", message="AI runtime already installed.")
            return AIInstallStartResponse(status="completed", already_installed=True)

        _set_state(
            status="installing",
            step=0,
            error_code=None,
            error_message=None,
            output_tail=[],
            restart_required=False,
        )
        thread = threading.Thread(
            target=_run_install,
            args=(active_settings, _default_resolve_wheel(active_settings)),
            daemon=True,
            name="ai-install",
        )
        thread.start()
        return installing
    finally:
        _start_lock.release()


def get_ai_install_progress() -> AIInstallProgressResponse:
    state = _snapshot()
    percent = (
        100.0
        if state.status == "completed"
        else (
            round(max(state.step - 1, 0) / state.steps_total * 100, 1) if state.steps_total else 0.0
        )
    )
    return AIInstallProgressResponse(
        status=state.status,
        step=state.step,
        steps_total=state.steps_total,
        step_label=state.step_label,
        percent=percent,
        message=state.message,
        error_code=state.error_code,
        error_message=state.error_message,
        output_tail=state.output_tail,
        restart_required=state.restart_required,
    )
