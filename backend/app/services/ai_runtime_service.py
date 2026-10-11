from __future__ import annotations

import importlib
import platform
import site
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIRuntimeNotAvailableError,
    CUDANotAvailableError,
    TorchNotAvailableError,
)
from app.core.logging import get_logger
from app.schemas.ai_runtime_schema import AICudaDeviceInfo, AIRuntimeStatusResponse

logger = get_logger(__name__)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def ensure_ai_extra_site_dir(settings: Settings | None = None) -> None:
    """Make the post-install AI stack (pip --target) importable, also when it was
    installed while the backend was already running."""
    site_dir_value = _get_active_settings(settings).ai_extra_site_dir
    if not site_dir_value:
        return
    site_dir = Path(site_dir_value)
    if not site_dir.is_dir() or str(site_dir) in sys.path:
        return
    site.addsitedir(str(site_dir))
    importlib.invalidate_caches()
    logger.info("AI extra site dir registered: %s", site_dir)


def get_torch_module() -> Any | None:
    try:
        return importlib.import_module("torch")
    except ImportError:
        return None


# Módulos que Real-ESRGAN importa al cargar el modelo (realesrgan_enhancer._create_backend).
REALESRGAN_RUNTIME_MODULES = ("cv2", "basicsr.archs.rrdbnet_arch", "realesrgan")


def ensure_torchvision_compat() -> None:
    """basicsr 1.4.2 imports `torchvision.transforms.functional_tensor`, removed in
    torchvision 0.17. Alias it to `functional` (same function) so a stock install works."""
    legacy_name = "torchvision.transforms.functional_tensor"
    if legacy_name in sys.modules:
        return
    try:
        importlib.import_module(legacy_name)
        return
    except ModuleNotFoundError:
        pass
    except Exception:  # noqa: BLE001 - torchvision missing/broken: nothing to alias
        return
    try:
        sys.modules[legacy_name] = importlib.import_module("torchvision.transforms.functional")
    except Exception:  # noqa: BLE001
        return


# Módulos de la restauración facial opcional (GFPGAN + facexlib).
FACE_RESTORE_RUNTIME_MODULES = ("gfpgan", "facexlib")


def _missing_modules(module_names: tuple[str, ...]) -> list[str]:
    ensure_torchvision_compat()
    missing: list[str] = []
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - any import failure means the runtime is unusable
            missing.append(module_name.split(".", maxsplit=1)[0])
    return missing


def get_missing_face_restore_modules() -> list[str]:
    return _missing_modules(FACE_RESTORE_RUNTIME_MODULES)


def get_missing_realesrgan_modules() -> list[str]:
    """Import check, not just find_spec: basicsr can be installed yet fail to import
    against a newer torchvision."""
    return _missing_modules(REALESRGAN_RUNTIME_MODULES)


def is_torch_available() -> bool:
    return get_torch_module() is not None


def get_torch_version() -> str | None:
    torch = get_torch_module()
    if torch is None:
        return None
    return getattr(torch, "__version__", None)


def is_cuda_available() -> bool:
    torch = get_torch_module()
    if torch is None:
        return False
    cuda = getattr(torch, "cuda", None)
    if cuda is None:
        return False
    try:
        return bool(cuda.is_available())
    except Exception:
        logger.warning("CUDA availability check failed", exc_info=True)
        return False


def get_cuda_device_count() -> int:
    if not is_cuda_available():
        return 0
    torch = get_torch_module()
    if torch is None or getattr(torch, "cuda", None) is None:
        return 0
    try:
        return int(torch.cuda.device_count())
    except Exception:
        logger.warning("CUDA device count check failed", exc_info=True)
        return 0


def get_cuda_devices() -> list[AICudaDeviceInfo]:
    torch = get_torch_module()
    if torch is None or not is_cuda_available():
        return []

    devices: list[AICudaDeviceInfo] = []
    for index in range(get_cuda_device_count()):
        name: str | None = None
        memory_total_mb: int | None = None
        try:
            name = torch.cuda.get_device_name(index)
        except Exception:
            logger.warning("CUDA device name lookup failed", exc_info=True)
        try:
            properties = torch.cuda.get_device_properties(index)
            memory_total = getattr(properties, "total_memory", None)
            if isinstance(memory_total, int):
                memory_total_mb = round(memory_total / (1024**2))
        except Exception:
            logger.warning("CUDA device properties lookup failed", exc_info=True)
        devices.append(
            AICudaDeviceInfo(
                index=index,
                name=name,
                memory_total_mb=memory_total_mb,
            )
        )
    return devices


def resolve_ai_device(
    preferred_device: str = "auto",
    *,
    allow_cpu: bool = True,
) -> str:
    normalized = preferred_device.strip().lower()
    if normalized not in {"auto", "cpu", "cuda"}:
        normalized = "auto"

    if not is_torch_available():
        raise TorchNotAvailableError()

    if normalized == "cpu":
        return "cpu"

    if normalized == "cuda":
        if not is_cuda_available():
            raise CUDANotAvailableError()
        return "cuda"

    if is_cuda_available():
        return "cuda"
    if allow_cpu:
        return "cpu"
    raise AIRuntimeNotAvailableError()


def get_ai_runtime_status(
    settings: Settings | None = None,
) -> AIRuntimeStatusResponse:
    active_settings = _get_active_settings(settings)
    ensure_ai_extra_site_dir(active_settings)
    warnings: list[str] = []
    torch_available = is_torch_available()
    torch_version = get_torch_version()
    cuda_available = is_cuda_available()
    cuda_devices = get_cuda_devices()
    selected_device: str | None = None

    if not torch_available:
        warnings.append("PyTorch is not installed. Real-ESRGAN cannot run yet.")
    else:
        try:
            selected_device = resolve_ai_device(
                active_settings.ai_device,
                allow_cpu=active_settings.ai_allow_cpu,
            )
            if selected_device == "cpu" and active_settings.ai_device.strip().lower() == "auto":
                warnings.append("CUDA is not available. CPU fallback selected.")
            if selected_device == "cpu" and active_settings.ai_device.strip().lower() == "cpu":
                warnings.append("CPU mode selected. Real-ESRGAN may run slowly.")
        except CUDANotAvailableError:
            warnings.append("CUDA requested but not available.")
        except AIRuntimeNotAvailableError:
            warnings.append("CPU fallback is disabled and CUDA is not available.")
        except TorchNotAvailableError:
            warnings.append("PyTorch is not installed. Real-ESRGAN cannot run yet.")

    available = torch_available and selected_device is not None
    return AIRuntimeStatusResponse(
        available=available,
        torch_available=torch_available,
        torch_version=torch_version,
        cuda_available=cuda_available,
        cuda_device_count=len(cuda_devices),
        cuda_devices=cuda_devices,
        selected_device=selected_device,
        allow_cpu=active_settings.ai_allow_cpu,
        half_precision=active_settings.ai_half_precision,
        warnings=warnings,
        python_executable=sys.executable,
        python_version=platform.python_version(),
        ai_extra_site_dir=active_settings.ai_extra_site_dir,
    )


def clear_cuda_cache_if_available() -> None:
    torch = get_torch_module()
    if torch is None or not is_cuda_available():
        return
    try:
        torch.cuda.empty_cache()
    except Exception:
        logger.warning("CUDA cache clear failed", exc_info=True)
