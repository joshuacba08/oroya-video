import shutil
import subprocess

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.paths import get_data_bin_path
from app.schemas.system_schema import ToolInfo, ToolsResponse

logger = get_logger(__name__)
COMMAND_TIMEOUT_SECONDS = 5
TOOL_VERSION_ARGS: dict[str, list[str]] = {
    "ffmpeg": ["-version"],
    "ffprobe": ["-version"],
    "nvidia-smi": ["--version"],
}
TOOL_LOG_LABELS = {
    "ffmpeg": "FFmpeg",
    "ffprobe": "FFprobe",
    "nvidia-smi": "nvidia-smi",
}


def _extract_version_text(command_result: subprocess.CompletedProcess[str]) -> str | None:
    output = "\n".join(
        part.strip() for part in (command_result.stdout, command_result.stderr) if part.strip()
    )
    if not output:
        return None

    return output.splitlines()[0].strip()


def resolve_tool_path(command: str, settings: Settings | None = None) -> str | None:
    """Resuelve un ejecutable prefiriendo el bin del data dir sobre el PATH."""
    bin_dir = get_data_bin_path(settings)
    for candidate in (bin_dir / f"{command}.exe", bin_dir / command):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(command)


def detect_tool(command: str, version_args: list[str] | None = None) -> ToolInfo:
    executable_path = resolve_tool_path(command)
    if not executable_path:
        logger.warning("%s not detected", TOOL_LOG_LABELS.get(command, command))
        return ToolInfo(available=False)

    version: str | None = None
    if version_args:
        try:
            command_result = subprocess.run(
                [executable_path, *version_args],
                capture_output=True,
                text=True,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            if command_result.returncode == 0:
                version = _extract_version_text(command_result)
            else:
                logger.warning(
                    "Failed to read version for %s",
                    TOOL_LOG_LABELS.get(command, command),
                )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning(
                "Error while detecting %s version: %s",
                TOOL_LOG_LABELS.get(command, command),
                exc,
            )

    return ToolInfo(available=True, path=executable_path, version=version)


def get_tools_status() -> ToolsResponse:
    response = ToolsResponse(
        ffmpeg=detect_tool("ffmpeg", TOOL_VERSION_ARGS["ffmpeg"]),
        ffprobe=detect_tool("ffprobe", TOOL_VERSION_ARGS["ffprobe"]),
        nvidia_smi=detect_tool("nvidia-smi", TOOL_VERSION_ARGS["nvidia-smi"]),
    )
    logger.info("Tool detection completed")
    return response
