"""Poster frame of an imported video, shown before any processing (workspace, project cards)."""

from __future__ import annotations

import subprocess
import threading
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    FFmpegNotAvailableError,
    VideoAssetFileMissingError,
    VideoAssetNotFoundError,
    VideoThumbnailFailedError,
)
from app.core.logging import get_logger
from app.core.paths import get_temp_path, resolve_path
from app.db.repositories import video_repository
from app.services.tool_detection_service import resolve_tool_path

logger = get_logger(__name__)

THUMBNAIL_MAX_WIDTH = 1280
THUMBNAIL_TIMEOUT_SECONDS = 30
# Un fotograma al 10 % de la duración (máx. 5 s): evita el negro típico del primer frame.
THUMBNAIL_POSITION_RATIO = 0.1
THUMBNAIL_MAX_SECONDS = 5.0

# Varias tarjetas pueden pedir a la vez la miniatura del mismo video: una sola generación.
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def get_thumbnail_path(video_id: str, settings: Settings | None = None) -> Path:
    return get_temp_path(_get_active_settings(settings)) / "thumbnails" / f"{video_id}.png"


def delete_thumbnail(video_id: str, settings: Settings | None = None) -> None:
    get_thumbnail_path(video_id, settings).unlink(missing_ok=True)


def _video_source_path(video) -> Path:
    if video.source_mode == "copy" and video.stored_path:
        return resolve_path(video.stored_path)
    return Path(video.source_path).expanduser().resolve()


def get_video_thumbnail(db: Session, video_id: str, settings: Settings | None = None) -> Path:
    """Path of the cached poster PNG, generating it with ffmpeg on first request."""
    with _locks_guard:
        lock = _locks[video_id]
    with lock:
        return _get_or_create_thumbnail(db, video_id, settings)


def _get_or_create_thumbnail(db: Session, video_id: str, settings: Settings | None) -> Path:
    active_settings = _get_active_settings(settings)
    video = video_repository.get_video_asset_by_id(db, video_id)
    if video is None:
        raise VideoAssetNotFoundError()

    thumbnail = get_thumbnail_path(video_id, active_settings)
    if thumbnail.is_file() and thumbnail.stat().st_size > 0:
        return thumbnail

    source = _video_source_path(video)
    if not source.is_file():
        raise VideoAssetFileMissingError()
    ffmpeg = resolve_tool_path("ffmpeg", active_settings)
    if not ffmpeg:
        raise FFmpegNotAvailableError()

    position = min((video.duration_seconds or 0) * THUMBNAIL_POSITION_RATIO, THUMBNAIL_MAX_SECONDS)
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    temp_path = thumbnail.with_name(f"{thumbnail.stem}.tmp.png")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{position:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        f"scale='min({THUMBNAIL_MAX_WIDTH},iw)':-2",
        str(temp_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=THUMBNAIL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        temp_path.unlink(missing_ok=True)
        raise VideoThumbnailFailedError() from exc
    if result.returncode != 0 or not temp_path.is_file():
        temp_path.unlink(missing_ok=True)
        logger.warning("Thumbnail generation failed for %s: %s", video_id, result.stderr[-300:])
        raise VideoThumbnailFailedError()
    temp_path.replace(thumbnail)
    return thumbnail
