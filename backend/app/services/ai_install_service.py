"""One-click install of the AI stack (PyTorch + Real-ESRGAN) from the setup wizard.

The installed app ships only the core backend. The AI stack is large and depends on the
GPU, so it is installed on demand with the backend's own interpreter (packages must match
its Python version) into `ai_extra_site_dir` (pip --target). In development, where that
directory is not configured, it installs into the backend's environment.

Steps (run with PYTHONPATH=<target> so pip treats already-installed packages as present):
1. torch + torchvision from the PyTorch index (CUDA build if an NVIDIA GPU is detected).
2. basicsr/realesrgan with --no-deps (basicsr from our patched wheel, see ai_wheel_builder).
3. Their pure-Python/numpy dependencies from PyPI.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.core.errors import DownloadAlreadyRunningError
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
)
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


_state = AIInstallState()
_lock = threading.Lock()


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
        ("PyTorch", [*base, *TORCH_PACKAGES, "--index-url", torch_index_url]),
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


def _run_install(
    settings: Settings,
    resolve_wheel: Callable[[], Path],
) -> None:
    target = settings.ai_extra_site_dir
    try:
        if target:
            Path(target).mkdir(parents=True, exist_ok=True)
        _set_state(step_label="Preparing", message="Preparing basicsr package...")
        basicsr_wheel = resolve_wheel()
        steps = build_install_steps(target, resolve_torch_index_url(), basicsr_wheel)
        env = _pip_env(target)
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
        if settings.frame_enhancer_engine.strip().lower() == "mock":
            # Quien instala la IA quiere usarla: no seguir procesando con el motor de prueba.
            settings_service.set_frame_enhancer_engine("realesrgan", settings)
        _set_state(status="completed", message="AI runtime installed.")
        logger.info("AI install completed")
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
    ai_runtime_service.ensure_ai_extra_site_dir(active_settings)
    if is_ai_stack_installed():
        _set_state(status="completed", message="AI runtime already installed.")
        return AIInstallStartResponse(status="completed", already_installed=True)

    with _lock:
        if _state.status == "installing":
            raise DownloadAlreadyRunningError()
        _state.status = "installing"
        _state.step = 0
        _state.error_code = None
        _state.error_message = None
        _state.output_tail = []

    thread = threading.Thread(
        target=_run_install,
        args=(active_settings, _default_resolve_wheel(active_settings)),
        daemon=True,
        name="ai-install",
    )
    thread.start()
    return AIInstallStartResponse(status="installing", already_installed=False)


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
    )
