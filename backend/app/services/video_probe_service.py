import json
import shutil
import subprocess
from pathlib import Path

from app.core.errors import (
    FFprobeNotAvailableError,
    OroyaVideoError,
    UnsupportedVideoFormatError,
    VideoFileNotFoundError,
    VideoProbeFailedError,
    VideoStreamNotFoundError,
)
from app.core.logging import get_logger
from app.schemas.video_schema import (
    AudioStreamInfo,
    StreamSummary,
    VideoFileInfo,
    VideoFormatInfo,
    VideoProbeRequest,
    VideoProbeResponse,
    VideoStreamInfo,
)

logger = get_logger(__name__)
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}
FFPROBE_TIMEOUT_SECONDS = 15
BYTES_IN_MB = 1024**2


def parse_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value

    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_float(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)

    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_fps(value: str | None) -> float | None:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        if "/" in normalized:
            numerator_raw, denominator_raw = normalized.split("/", maxsplit=1)
            numerator = float(numerator_raw)
            denominator = float(denominator_raw)
            if denominator == 0:
                return None
            fps = numerator / denominator
        else:
            fps = float(normalized)
    except (TypeError, ValueError):
        return None

    if fps <= 0:
        return None

    return round(fps, 3)


def format_duration(seconds: float | None) -> str | None:
    if seconds is None or seconds < 0:
        return None

    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def _resolve_video_path(file_path: str) -> Path:
    resolved_path = Path(file_path).expanduser().resolve()
    if not resolved_path.exists() or not resolved_path.is_file():
        raise VideoFileNotFoundError()

    return resolved_path


def _validate_extension(file_path: Path) -> None:
    if file_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        logger.warning("Unsupported video format: %s", file_path.suffix.lower())
        raise UnsupportedVideoFormatError()


def _get_ffprobe_path() -> str:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        logger.warning("FFprobe not available")
        raise FFprobeNotAvailableError()

    return ffprobe_path


def _run_ffprobe(ffprobe_path: str, file_path: Path) -> dict:
    try:
        command_result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Video probe failed: %s", exc)
        raise VideoProbeFailedError() from exc

    if command_result.returncode != 0:
        logger.warning(
            "Video probe failed: ffprobe returned exit code %s",
            command_result.returncode,
        )
        raise VideoProbeFailedError()

    try:
        return json.loads(command_result.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("Video probe failed: ffprobe returned invalid JSON")
        raise VideoProbeFailedError() from exc


def _get_primary_stream(streams: list[dict], stream_type: str) -> dict | None:
    return next((stream for stream in streams if stream.get("codec_type") == stream_type), None)


def _build_file_info(file_path: Path) -> VideoFileInfo:
    file_size_bytes = file_path.stat().st_size
    return VideoFileInfo(
        path=str(file_path),
        name=file_path.name,
        extension=file_path.suffix.lower(),
        size_bytes=file_size_bytes,
        size_mb=round(file_size_bytes / BYTES_IN_MB, 1),
    )


def _build_format_info(format_data: dict) -> VideoFormatInfo:
    duration_seconds = parse_float(format_data.get("duration"))
    return VideoFormatInfo(
        format_name=format_data.get("format_name"),
        duration_seconds=duration_seconds,
        duration_label=format_duration(duration_seconds),
        bit_rate=parse_int(format_data.get("bit_rate")),
    )


def _build_video_info(video_stream: dict) -> VideoStreamInfo:
    width = parse_int(video_stream.get("width"))
    height = parse_int(video_stream.get("height"))
    return VideoStreamInfo(
        codec=video_stream.get("codec_name"),
        codec_long_name=video_stream.get("codec_long_name"),
        width=width,
        height=height,
        resolution_label=f"{width}x{height}" if width and height else None,
        fps=parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        pix_fmt=video_stream.get("pix_fmt"),
        profile=video_stream.get("profile"),
        bit_rate=parse_int(video_stream.get("bit_rate")),
    )


def _build_audio_info(audio_stream: dict | None, warnings: list[str]) -> AudioStreamInfo:
    if not audio_stream:
        logger.warning("No audio stream detected")
        warnings.append("No audio stream detected.")
        return AudioStreamInfo(available=False)

    return AudioStreamInfo(
        available=True,
        codec=audio_stream.get("codec_name"),
        codec_long_name=audio_stream.get("codec_long_name"),
        sample_rate=parse_int(audio_stream.get("sample_rate")),
        channels=parse_int(audio_stream.get("channels")),
        channel_layout=audio_stream.get("channel_layout"),
        bit_rate=parse_int(audio_stream.get("bit_rate")),
    )


def _build_stream_summaries(streams: list[dict]) -> list[StreamSummary]:
    summaries: list[StreamSummary] = []
    for stream in streams:
        summaries.append(
            StreamSummary(
                index=parse_int(stream.get("index")) or 0,
                type=stream.get("codec_type", "unknown"),
                codec=stream.get("codec_name"),
                width=parse_int(stream.get("width")),
                height=parse_int(stream.get("height")),
            )
        )

    return summaries


def probe_video(payload: VideoProbeRequest) -> VideoProbeResponse:
    logger.info("Video probe requested: %s", payload.file_path)

    try:
        file_path = _resolve_video_path(payload.file_path)
        _validate_extension(file_path)
        ffprobe_path = _get_ffprobe_path()
        probe_payload = _run_ffprobe(ffprobe_path, file_path)

        streams = probe_payload.get("streams", [])
        format_data = probe_payload.get("format", {})
        video_stream = _get_primary_stream(streams, "video")
        if not video_stream:
            logger.warning("No video stream detected")
            raise VideoStreamNotFoundError()

        warnings: list[str] = []
        audio_stream = _get_primary_stream(streams, "audio")

        response = VideoProbeResponse(
            valid=True,
            file=_build_file_info(file_path),
            format=_build_format_info(format_data),
            video=_build_video_info(video_stream),
            audio=_build_audio_info(audio_stream, warnings),
            streams=_build_stream_summaries(streams),
            warnings=warnings,
        )
        logger.info("Video probe completed: %s", file_path.name)
        return response
    except OroyaVideoError as exc:
        logger.warning("Video probe failed: %s", exc.error_code)
        raise
