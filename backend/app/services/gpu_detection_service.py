import subprocess

from app.core.logging import get_logger
from app.schemas.system_schema import GPUInfo, GPUResponse
from app.services.tool_detection_service import COMMAND_TIMEOUT_SECONDS, detect_tool

logger = get_logger(__name__)
NVIDIA_SMI_QUERY = (
    "name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu"
)
NVIDIA_SMI_ARGS = [
    f"--query-gpu={NVIDIA_SMI_QUERY}",
    "--format=csv,noheader,nounits",
]


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None

    normalized = value.strip()
    if normalized in {"", "N/A", "[Not Supported]", "Not Supported"}:
        return None

    try:
        return int(normalized)
    except ValueError:
        return None


def parse_nvidia_smi_output(output: str) -> list[GPUInfo]:
    gpus: list[GPUInfo] = []

    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue

        parts = [part.strip() for part in raw_line.split(",")]
        if len(parts) < 7:
            continue

        gpus.append(
            GPUInfo(
                name=parts[0],
                driver_version=parts[1] or None,
                memory_total_mb=_parse_optional_int(parts[2]),
                memory_used_mb=_parse_optional_int(parts[3]),
                memory_free_mb=_parse_optional_int(parts[4]),
                utilization_percent=_parse_optional_int(parts[5]),
                temperature_celsius=_parse_optional_int(parts[6]),
            )
        )

    return gpus


def get_gpu_status() -> GPUResponse:
    nvidia_smi = detect_tool("nvidia-smi", ["--version"])
    if not nvidia_smi.available or not nvidia_smi.path:
        logger.warning("NVIDIA GPU not detected")
        return GPUResponse(available=False, provider=None, gpus=[])

    try:
        command_result = subprocess.run(
            [nvidia_smi.path, *NVIDIA_SMI_ARGS],
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("GPU detection failed: %s", exc)
        return GPUResponse(available=False, provider=None, gpus=[])

    if command_result.returncode != 0:
        logger.warning("GPU detection failed with exit code %s", command_result.returncode)
        return GPUResponse(available=False, provider=None, gpus=[])

    gpus = parse_nvidia_smi_output(command_result.stdout)
    if not gpus:
        logger.warning("NVIDIA GPU not detected")
        return GPUResponse(available=False, provider=None, gpus=[])

    logger.info("GPU detection completed")
    return GPUResponse(available=True, provider="nvidia", gpus=gpus)
