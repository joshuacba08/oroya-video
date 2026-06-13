from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    EncodedVideoNotFoundError,
    EnhancedFramesRequiredError,
    FFmpegNotAvailableError,
    InsufficientTempStorageError,
    JobNotFoundError,
    VideoEncodingFailedError,
)
from app.core.logging import get_logger
from app.core.paths import (
    ensure_job_encoded_directory,
    get_directory_size_bytes,
    get_job_silent_video_path,
    get_temp_path,
)
from app.db.repositories import job_repository
from app.schemas.job_schema import (
    DeleteEncodedVideoResponse,
    EncodedVideoResponse,
    VideoEncodingSummaryResponse,
)
from app.services.frame_extraction_service import time_to_datetime, validate_ffmpeg_available
from app.services.pipeline_progress import (
    ENCODING_PROGRESS_END,
    ENCODING_PROGRESS_START,
    calculate_stage_progress,
)
from app.services.process_registry_service import register_process, unregister_process

logger = get_logger(__name__)
ENCODED_VIDEO_FILE_NAME = "video_silent.mp4"
ENCODING_CODEC = "h264"
FFMPEG_ENCODING_CODEC = "libx264"
ENCODING_FORMAT = "mp4"
ENCODING_PIXEL_FORMAT = "yuv420p"


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def resolve_encoding_fps(job) -> float:
    video = job.video_asset or getattr(job, "video_asset", None)
    if video is not None and video.fps and video.fps > 0:
        return float(video.fps)
    logger.warning("Encoding FPS fallback applied for job %s", job.id)
    return 30.0


def build_video_encoding_command(
    input_pattern: Path,
    output_path: Path,
    fps: float,
    codec: str = FFMPEG_ENCODING_CODEC,
    pix_fmt: str = ENCODING_PIXEL_FORMAT,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        str(input_pattern),
        "-c:v",
        codec,
        "-pix_fmt",
        pix_fmt,
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]
    logger.info("Video encoding command built")
    return command


def parse_ffmpeg_encoding_progress_line(line: str) -> dict[str, str]:
    if "=" not in line:
        return {}
    key, value = line.split("=", maxsplit=1)
    return {key.strip(): value.strip()}


def ensure_encoding_storage_capacity(
    enhanced_frames_dir: Path,
    settings: Settings | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    temp_path = get_temp_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(temp_path)
    required_bytes = max(int(get_directory_size_bytes(enhanced_frames_dir) * 0.25), 1)
    if free_bytes < required_bytes:
        raise InsufficientTempStorageError(
            "Not enough temporary storage space to encode video."
        )


def _mark_encoding_failed(
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
            "encoding_error_code": error_code,
            "encoding_error_message": error_message,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "error",
        f"Video encoding failed: {error_message}",
        stage="failed",
    )
    db.commit()


def encode_video_for_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
):
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    if job.cancel_requested or job.status == "cancelled":
        return job

    try:
        ffmpeg_path = validate_ffmpeg_available()
    except FFmpegNotAvailableError as exc:
        _mark_encoding_failed(
            db,
            job,
            error_code=exc.error_code,
            error_message=exc.message,
        )
        raise

    enhanced_frames_value = job.enhanced_frames_dir
    if not enhanced_frames_value:
        _mark_encoding_failed(
            db,
            job,
            error_code="enhanced_frames_required",
            error_message="Enhanced frames are required before encoding video.",
        )
        raise EnhancedFramesRequiredError()

    enhanced_frames_dir = Path(enhanced_frames_value)
    frame_pattern = enhanced_frames_dir / "frame_%08d.png"
    first_frame = enhanced_frames_dir / "frame_00000000.png"
    if not enhanced_frames_dir.exists() or not first_frame.exists():
        _mark_encoding_failed(
            db,
            job,
            error_code="enhanced_frames_required",
            error_message="Enhanced frames are required before encoding video.",
        )
        raise EnhancedFramesRequiredError()

    enhanced_frames = max(
        job.enhanced_frames,
        sum(1 for item in enhanced_frames_dir.glob("*.png") if item.is_file()),
    )
    if enhanced_frames <= 0:
        _mark_encoding_failed(
            db,
            job,
            error_code="enhanced_frames_required",
            error_message="Enhanced frames are required before encoding video.",
        )
        raise EnhancedFramesRequiredError()

    try:
        ensure_encoding_storage_capacity(enhanced_frames_dir, active_settings)
    except InsufficientTempStorageError as exc:
        _mark_encoding_failed(
            db,
            job,
            error_code=exc.error_code,
            error_message=exc.message,
        )
        raise

    fps = resolve_encoding_fps(job)
    encoded_dir = ensure_job_encoded_directory(job.id, active_settings)
    output_path = get_job_silent_video_path(job.id, active_settings)
    command = build_video_encoding_command(frame_pattern, output_path, fps)
    command[0] = ffmpeg_path
    started_at = time.monotonic()
    now = time.time()

    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "encoding_video",
            "frames_processed": 0,
            "encoded_dir": str(encoded_dir),
            "encoded_video_path": str(output_path),
            "encoded_video_file_name": ENCODED_VIDEO_FILE_NAME,
            "encoding_fps": fps,
            "encoding_codec": ENCODING_CODEC,
            "encoding_format": ENCODING_FORMAT,
            "encoding_started_at": job.encoding_started_at or time_to_datetime(now),
            "encoding_error_code": None,
            "encoding_error_message": None,
            "error_code": None,
            "error_message": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Video encoding started.",
        stage="encoding_video",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Encoding from enhanced frames.",
        stage="encoding_video",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Encoding FPS: {fps}",
        stage="encoding_video",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Encoding codec: {FFMPEG_ENCODING_CODEC}",
        stage="encoding_video",
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
    register_process(job.id, process_id, "ffmpeg_encode", process)
    job_repository.update_job(
        db,
        job,
        {
            "process_id": process_id,
            "process_kind": "ffmpeg_encode",
            "process_started_at": time_to_datetime(time.time()),
            "process_ended_at": None,
        },
    )
    db.commit()
    logger.info("Video encoding started: %s", job_id)
    last_logged_frame = -100

    try:
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue

                progress_data = parse_ffmpeg_encoding_progress_line(line)
                if not progress_data:
                    continue

                if "frame" in progress_data:
                    frames_processed = _safe_int(progress_data["frame"]) or 0
                    progress_percent = calculate_stage_progress(
                        frames_processed,
                        enhanced_frames,
                        start=ENCODING_PROGRESS_START,
                        end=ENCODING_PROGRESS_END,
                        clamp_to=84.9,
                    )
                    job_repository.update_job(
                        db,
                        job,
                        {
                            "frames_processed": frames_processed,
                            "progress_percent": progress_percent,
                            "elapsed_time_seconds": int(time.monotonic() - started_at),
                        },
                    )
                    if frames_processed - last_logged_frame >= 100:
                        last_logged_frame = frames_processed
                        job_repository.create_job_log(
                            db,
                            job.id,
                            "info",
                            f"Encoding progress: {frames_processed}/{enhanced_frames}",
                            stage="encoding_video",
                        )
                    db.commit()
                    logger.info("Video encoding progress updated: %s", frames_processed)

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
                        "Video encoding cancelled by user.",
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
                    logger.warning("Video encoding cancelled: %s", job_id)
                    return job

        stderr_output = ""
        if process.stderr is not None:
            stderr_output = process.stderr.read().strip()

        return_code = process.wait()
        if return_code != 0:
            _mark_encoding_failed(
                db,
                job,
                error_code="video_encoding_failed",
                error_message=stderr_output or "Video could not be encoded from enhanced frames.",
            )
            logger.warning("Video encoding failed: %s", job_id)
            raise VideoEncodingFailedError()

        output_size = output_path.stat().st_size if output_path.exists() else None
        unregister_process(job.id)
        job_repository.update_job(
            db,
            job,
            {
                "status": "running",
                "current_stage": "encoding_video",
                "frames_processed": enhanced_frames,
                "progress_percent": ENCODING_PROGRESS_END,
                "encoded_dir": str(encoded_dir),
                "encoded_video_path": str(output_path),
                "encoded_video_file_name": ENCODED_VIDEO_FILE_NAME,
                "encoded_video_size_bytes": output_size,
                "encoding_fps": fps,
                "encoding_codec": ENCODING_CODEC,
                "encoding_format": ENCODING_FORMAT,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
                "encoding_completed_at": time_to_datetime(time.time()),
                "encoded_size_bytes": output_size,
                "process_id": None,
                "process_kind": None,
                "process_ended_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Video encoding completed.",
            stage="completed",
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Silent video generated: {output_path}",
            stage="encoding_video",
        )
        db.commit()
        logger.info("Video encoding completed: %s", job_id)
        return job
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        unregister_process(job.id)
        _mark_encoding_failed(
            db,
            job,
            error_code="video_encoding_failed",
            error_message="Video could not be encoded from enhanced frames.",
        )
        logger.exception("Video encoding failed")
        raise VideoEncodingFailedError() from exc


def get_encoded_video_summary(job) -> VideoEncodingSummaryResponse:
    logger.info("Encoded video summary requested: %s", job.id)
    return VideoEncodingSummaryResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        encoded_dir=job.encoded_dir,
        encoded_video_path=job.encoded_video_path,
        encoded_video_file_name=job.encoded_video_file_name,
        encoded_video_size_bytes=job.encoded_video_size_bytes,
        encoding_fps=job.encoding_fps,
        encoding_codec=job.encoding_codec,
        encoding_format=job.encoding_format,
        encoding_started_at=job.encoding_started_at,
        encoding_completed_at=job.encoding_completed_at,
        encoding_error_code=job.encoding_error_code,
        encoding_error_message=job.encoding_error_message,
    )


def get_encoded_video_metadata(job) -> EncodedVideoResponse:
    available = False
    path: str | None = None
    file_name: str | None = None
    size_bytes: int | None = None
    if job.encoded_video_path:
        candidate = Path(job.encoded_video_path)
        if candidate.exists() and candidate.is_file():
            available = True
            path = str(candidate)
            file_name = candidate.name
            size_bytes = candidate.stat().st_size

    logger.info("Encoded video metadata requested: %s", job.id)
    return EncodedVideoResponse(
        job_id=job.id,
        available=available,
        path=path,
        file_name=file_name,
        size_bytes=size_bytes,
        format=job.encoding_format or ENCODING_FORMAT,
        codec=job.encoding_codec or ENCODING_CODEC,
        has_audio=False,
    )


def delete_encoded_video_file(job) -> None:
    if not job.encoded_video_path:
        raise EncodedVideoNotFoundError()

    candidate = Path(job.encoded_video_path)
    if not candidate.exists() or not candidate.is_file():
        raise EncodedVideoNotFoundError()

    candidate.unlink()


def build_delete_encoded_video_response(job_id: str) -> DeleteEncodedVideoResponse:
    return DeleteEncodedVideoResponse(deleted=True, job_id=job_id)


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
