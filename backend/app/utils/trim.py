"""Optional trim of the source video (`export_config.trim`): process only a fragment.

Shared by frame extraction (and the streaming decoder) and audio mux so video and audio are
cut at the same points.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.enhancement_config import parse_enhancement_config_json

MIN_TRIM_SECONDS = 0.5


@dataclass(frozen=True)
class TrimRange:
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_trim(config: object, video_duration: float | None = None) -> TrimRange | None:
    """Trim from an export config dict, clamped to the video; None when it covers it all."""
    if not isinstance(config, dict):
        return None
    start = _number(config.get("start_seconds")) or 0.0
    end = _number(config.get("end_seconds"))
    if video_duration:
        end = video_duration if end is None else min(end, video_duration)
    if end is None or start <= 0 and video_duration and end >= video_duration:
        return None
    start = max(start, 0.0)
    if end - start < MIN_TRIM_SECONDS:
        return None
    return TrimRange(start, end)


def get_job_trim(job) -> TrimRange | None:
    export_config = parse_enhancement_config_json(getattr(job, "export_config_json", None))
    video = getattr(job, "video_asset", None)
    return parse_trim(export_config.get("trim"), getattr(video, "duration_seconds", None))


def trim_input_args(trim: TrimRange | None) -> list[str]:
    """ffmpeg input options (before -i): seek to the start and read only the fragment."""
    if trim is None:
        return []
    return ["-ss", f"{trim.start_seconds:.3f}", "-t", f"{trim.duration_seconds:.3f}"]


def effective_duration(job) -> float | None:
    trim = get_job_trim(job)
    if trim is not None:
        return trim.duration_seconds
    video = getattr(job, "video_asset", None)
    return getattr(video, "duration_seconds", None)
