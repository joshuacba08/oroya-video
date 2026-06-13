from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    FFmpegNotAvailableError,
    FrameExtractionFailedError,
    InsufficientTempStorageError,
    JobNotFoundError,
    VideoAssetFileMissingError,
)
from app.core.logging import get_logger
from app.core.paths import get_directory_size_bytes, get_temp_path
from app.db.repositories import job_repository
from app.services import job_workspace_service
from app.services.pipeline_progress import (
    EXTRACTION_PROGRESS_END,
    EXTRACTION_PROGRESS_START,
    calculate_stage_progress,
)
from app.services.process_registry_service import register_process, unregister_process

logger = get_logger(__name__)
FRAME_FILE_PATTERN = "frame_%08d.png"
FRAME_FORMAT = "png"
TEMP_STORAGE_MULTIPLIER = 3


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def resolve_job_input_video(job) -> Path:
    video = job.video_asset or getattr(job, "video_asset", None)
    if video is None:
        raise VideoAssetFileMissingError()

    if video.source_mode == "copy" and video.stored_path:
        candidate = Path(video.stored_path).expanduser().resolve()
    else:
        candidate = Path(video.source_path).expanduser().resolve()

    if not candidate.exists() or not candidate.is_file():
        raise VideoAssetFileMissingError()

    return candidate


def estimate_total_frames(job) -> int | None:
    video = job.video_asset or getattr(job, "video_asset", None)
    if video is None or video.duration_seconds is None or video.fps is None:
        return None

    estimated = round(video.duration_seconds * video.fps)
    return estimated if estimated > 0 else None


def build_frame_extraction_command(
    input_path: Path,
    output_dir: Path,
    frame_pattern: str = FRAME_FILE_PATTERN,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-vsync",
        "0",
        "-start_number",
        "0",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_dir / frame_pattern),
    ]
    logger.info("FFmpeg frame extraction command built")
    return command


def parse_ffmpeg_progress_line(line: str) -> dict[str, str]:
    if "=" not in line:
        return {}
    key, value = line.split("=", maxsplit=1)
    return {key.strip(): value.strip()}


def count_extracted_frames(frames_dir: Path) -> int:
    return sum(1 for item in frames_dir.glob("*.png") if item.is_file())


def validate_ffmpeg_available() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegNotAvailableError()
    return ffmpeg_path


def ensure_temp_storage_capacity(video_asset, settings: Settings | None = None) -> None:
    active_settings = _get_active_settings(settings)
    temp_path = get_temp_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(temp_path)
    required_bytes = max(video_asset.file_size_bytes * TEMP_STORAGE_MULTIPLIER, 1)
    if free_bytes < required_bytes:
        raise InsufficientTempStorageError()


def _mark_job_failed(
    db: Session,
    job,
    *,
    error_code: str,
    error_message: str,
) -> None:
    job_repository.update_job(
        db,
        job,
        {
            "status": "failed",
            "current_stage": "failed",
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "error",
        f"Frame extraction failed: {error_message}",
        stage="failed",
    )
    db.commit()


def extract_frames_for_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> object:
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()

    try:
        input_path = resolve_job_input_video(job)
        ensure_temp_storage_capacity(job.video_asset, active_settings)
        ffmpeg_path = validate_ffmpeg_available()
    except (
        VideoAssetFileMissingError,
        InsufficientTempStorageError,
        FFmpegNotAvailableError,
    ) as exc:
        _mark_job_failed(
            db,
            job,
            error_code=exc.error_code,
            error_message=exc.message,
        )
        raise

    logger.info("Frame extraction requested: %s", job_id)
    workspace = job_workspace_service.prepare_job_workspace(job_id, active_settings)
    original_frames_dir = workspace["original_frames_dir"]
    working_dir = workspace["working_dir"]
    enhanced_frames_dir = workspace["enhanced_frames_dir"]
    estimated_frames = estimate_total_frames(job)
    command = build_frame_extraction_command(input_path, original_frames_dir)
    command[0] = ffmpeg_path

    started_at = time.monotonic()
    now = time.time()
    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "extracting_frames",
            "frames_total": estimated_frames,
            "working_dir": str(working_dir),
            "original_frames_dir": str(original_frames_dir),
            "enhanced_frames_dir": str(enhanced_frames_dir),
            "frame_file_pattern": FRAME_FILE_PATTERN,
            "frame_format": FRAME_FORMAT,
            "extraction_started_at": job.extraction_started_at or time_to_datetime(now),
            "started_at": job.started_at or time_to_datetime(now),
            "pause_requested": False,
            "error_code": None,
            "error_message": None,
            "enhancement_error_code": None,
            "enhancement_error_message": None,
            "encoding_error_code": None,
            "encoding_error_message": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Job workspace prepared.",
        stage="extracting_frames",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Frame extraction started.",
        stage="extracting_frames",
    )
    db.commit()

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    process_id = int(getattr(process, "pid", 0) or id(process))
    register_process(job.id, process_id, "ffmpeg_extract", process)
    job_repository.update_job(
        db,
        job,
        {
            "process_id": process_id,
            "process_kind": "ffmpeg_extract",
            "process_started_at": time_to_datetime(time.time()),
            "process_ended_at": None,
        },
    )
    db.commit()
    logger.info("FFmpeg frame extraction started: %s", job_id)

    last_logged_frame = -100
    try:
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue

                progress_data = parse_ffmpeg_progress_line(line)
                if not progress_data:
                    continue

                if "frame" in progress_data:
                    frames_processed = _safe_int(progress_data["frame"]) or 0
                    progress_percent = calculate_stage_progress(
                        frames_processed,
                        estimated_frames,
                        start=EXTRACTION_PROGRESS_START,
                        end=EXTRACTION_PROGRESS_END,
                        clamp_to=24.9,
                    )

                    elapsed_seconds = int(time.monotonic() - started_at)
                    job_repository.update_job(
                        db,
                        job,
                        {
                            "frames_processed": frames_processed,
                            "progress_percent": progress_percent,
                            "elapsed_time_seconds": elapsed_seconds,
                        },
                    )
                    if frames_processed - last_logged_frame >= 100:
                        last_logged_frame = frames_processed
                        job_repository.create_job_log(
                            db,
                            job.id,
                            "info",
                            (
                                "Frame extraction progress: "
                                f"{frames_processed}/{estimated_frames or '?'}"
                            ),
                            stage="extracting_frames",
                        )
                    db.commit()
                    logger.info("FFmpeg progress updated: %s", frames_processed)

                db.refresh(job)
                if job.cancel_requested or job.status == "cancelled":
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    job_repository.update_job(
                        db,
                        job,
                        {
                            "status": "cancelled",
                            "current_stage": "cancelled",
                            "cancelled_at": time_to_datetime(time.time()),
                        },
                    )
                    job_repository.create_job_log(
                        db,
                        job.id,
                        "warning",
                        "Frame extraction cancelled by user.",
                        stage="cancelled",
                    )
                    unregister_process(job.id)
                    job_repository.update_job(
                        db,
                        job,
                        {
                            "process_id": None,
                            "process_kind": None,
                            "process_ended_at": time_to_datetime(time.time()),
                        },
                    )
                    db.commit()
                    logger.warning("Frame extraction cancelled: %s", job_id)
                    return job

        stderr_output = ""
        if process.stderr is not None:
            stderr_output = process.stderr.read().strip()

        return_code = process.wait()
        if return_code != 0:
            _mark_job_failed(
                db,
                job,
                error_code="frame_extraction_failed",
                error_message=stderr_output or "Video frames could not be extracted.",
            )
            logger.warning("FFmpeg frame extraction failed: %s", job_id)
            raise FrameExtractionFailedError()

        extracted_frames = count_extracted_frames(original_frames_dir)
        unregister_process(job.id)
        job_repository.update_job(
            db,
            job,
            {
                "status": "running",
                "current_stage": "extracting_frames",
                "frames_processed": extracted_frames,
                "frames_total": estimated_frames or extracted_frames,
                "extracted_frames": extracted_frames,
                "progress_percent": EXTRACTION_PROGRESS_END,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
                "extraction_completed_at": time_to_datetime(time.time()),
                "original_frames_size_bytes": get_directory_size_bytes(original_frames_dir),
                "temp_size_bytes": get_directory_size_bytes(working_dir),
                "process_id": None,
                "process_kind": None,
                "process_ended_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Frame extraction completed.",
            stage="extracting_frames",
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Extracted frames: {extracted_frames}",
            stage="extracting_frames",
        )
        db.commit()
        logger.info("FFmpeg frame extraction completed: %s", job_id)
        return job
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        unregister_process(job.id)
        _mark_job_failed(
            db,
            job,
            error_code="frame_extraction_failed",
            error_message="Video frames could not be extracted.",
        )
        logger.exception("FFmpeg frame extraction failed")
        raise FrameExtractionFailedError() from exc


def time_to_datetime(epoch_seconds: float):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch_seconds, UTC).replace(tzinfo=None)


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
