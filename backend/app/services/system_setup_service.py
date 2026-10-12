from __future__ import annotations

import zipfile
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import get_data_bin_path
from app.schemas.system_schema import (
    FFmpegDownloadProgressResponse,
    FFmpegDownloadStartResponse,
)
from app.services.download_service import get_download_state, start_download
from app.services.tool_detection_service import resolve_tool_path

logger = get_logger(__name__)

FFMPEG_DOWNLOAD_KEY = "tool:ffmpeg"
# Release versionada y permanente de gyan.dev (build "essentials": libx264 y AAC, lo que usa
# el pipeline) con SHA-256 fijado. Antes era la build rolling "latest" de BtbN: cambiaba
# a diario y no se podía verificar.
FFMPEG_VERSION = "9.0.2"
FFMPEG_DOWNLOAD_URL = (
    f"https://github.com/GyanD/codexffmpeg/releases/download/{FFMPEG_VERSION}/"
    f"ffmpeg-{FFMPEG_VERSION}-essentials_build.zip"
)
FFMPEG_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
FFMPEG_TOOLS = ("ffmpeg.exe", "ffprobe.exe")


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def is_ffmpeg_installed(settings: Settings | None = None) -> bool:
    return (
        resolve_tool_path("ffmpeg", settings) is not None
        and resolve_tool_path("ffprobe", settings) is not None
    )


def start_ffmpeg_download(
    settings: Settings | None = None,
) -> FFmpegDownloadStartResponse:
    active_settings = _get_active_settings(settings)

    if is_ffmpeg_installed(active_settings):
        return FFmpegDownloadStartResponse(status="completed", already_installed=True)

    bin_dir = get_data_bin_path(active_settings)
    archive_path = bin_dir / "ffmpeg-download.zip"

    def on_complete() -> None:
        _extract_ffmpeg(archive_path, bin_dir)

    state = start_download(
        FFMPEG_DOWNLOAD_KEY,
        FFMPEG_DOWNLOAD_URL,
        archive_path,
        sha256=FFMPEG_SHA256,
        on_complete=on_complete,
    )
    logger.info("FFmpeg download started")
    return FFmpegDownloadStartResponse(status=state.status, already_installed=False)


def _extract_ffmpeg(archive_path: Path, bin_dir: Path) -> None:
    extracted: set[str] = set()
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.namelist():
            file_name = entry.rsplit("/", maxsplit=1)[-1]
            if file_name in FFMPEG_TOOLS and "/bin/" in entry:
                target = bin_dir / file_name
                with archive.open(entry) as source, open(target, "wb") as output:
                    output.write(source.read())
                extracted.add(file_name)

    archive_path.unlink(missing_ok=True)
    missing = set(FFMPEG_TOOLS) - extracted
    if missing:
        raise RuntimeError(f"FFmpeg archive did not contain: {', '.join(sorted(missing))}")
    logger.info("FFmpeg extracted to %s", bin_dir)


def get_ffmpeg_download_progress(
    settings: Settings | None = None,
) -> FFmpegDownloadProgressResponse:
    active_settings = _get_active_settings(settings)
    state = get_download_state(FFMPEG_DOWNLOAD_KEY)
    status = state.status
    if status == "idle" and is_ffmpeg_installed(active_settings):
        status = "completed"
    return FFmpegDownloadProgressResponse(
        status=status,
        bytes_done=state.bytes_done,
        bytes_total=state.bytes_total,
        percent=state.percent if status != "completed" else 100.0,
        error_code=state.error_code,
        error_message=state.error_message,
    )
