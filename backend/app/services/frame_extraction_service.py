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
    FFmpegStalledError,
    FrameExtractionFailedError,
    InsufficientDiskSpaceError,
    InsufficientTempStorageError,
    JobNotFoundError,
    VideoAssetFileMissingError,
)
from app.core.logging import get_logger
from app.core.paths import get_directory_size_bytes, get_temp_path, resolve_path
from app.db.database import commit_progress
from app.db.repositories import job_repository
from app.services import job_workspace_service
from app.services.pipeline_progress import (
    EXTRACTION_PROGRESS_END,
    EXTRACTION_PROGRESS_START,
    calculate_stage_progress,
)
from app.services.process_registry_service import (
    is_shutting_down,
    register_process,
    unregister_process,
)
from app.utils.color import decode_color_filter, source_color_for_video
from app.utils.enhancement_config import parse_enhancement_config_json
from app.utils.process_output import (
    StderrDrain,
    is_disk_full,
    stop_process_quietly,
    watch_process_output,
)
from app.utils.trim import TrimRange, effective_duration, get_job_trim, trim_input_args

logger = get_logger(__name__)
FRAME_FILE_PATTERN = "frame_%08d.png"
FRAME_FORMAT = "png"
TEMP_STORAGE_MULTIPLIER = 3
# Un frame PNG de video ocupa ~la mitad de su tamaño RGB sin comprimir (3 B/píxel).
PNG_BYTES_PER_PIXEL = 1.5
DISK_MARGIN_BYTES = 512 * 1024 * 1024
GIB = 1024**3


def estimate_png_frames_bytes(frames: int, width: int, height: int, scale: float = 1.0) -> int:
    return int(
        max(frames, 0) * max(width, 0) * max(height, 0) * scale * scale * PNG_BYTES_PER_PIXEL
    )


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def resolve_job_input_video(job) -> Path:
    video = job.video_asset or getattr(job, "video_asset", None)
    if video is None:
        raise VideoAssetFileMissingError()

    if video.source_mode == "copy" and video.stored_path:
        candidate = resolve_path(video.stored_path)
    else:
        candidate = Path(video.source_path).expanduser().resolve()

    if not candidate.exists() or not candidate.is_file():
        raise VideoAssetFileMissingError()

    return candidate


def estimate_total_frames(job) -> int | None:
    video = job.video_asset or getattr(job, "video_asset", None)
    duration = effective_duration(job)
    if video is None or duration is None or video.fps is None:
        return None

    estimated = round(duration * video.fps)
    return estimated if estimated > 0 else None


def build_frame_extraction_command(
    input_path: Path,
    output_dir: Path,
    frame_pattern: str = FRAME_FILE_PATTERN,
    trim: TrimRange | None = None,
    video_filters: str | None = None,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        *trim_input_args(trim),
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        *(["-vf", video_filters] if video_filters else []),
        # Un PNG por fotograma decodificado, sin duplicar ni descartar (antes `-vsync 0`,
        # opción obsoleta que las versiones nuevas de ffmpeg ya no aceptan).
        "-fps_mode",
        "passthrough",
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
    from app.services.tool_detection_service import resolve_tool_path

    ffmpeg_path = resolve_tool_path("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegNotAvailableError()
    return ffmpeg_path


def ensure_temp_storage_capacity(
    video_asset,
    settings: Settings | None = None,
    duration_seconds: float | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    temp_path = get_temp_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(temp_path)
    # Los PNG extraídos ocupan decenas de veces el MP4: se estima por resolución y frames
    # (de la parte recortada, si la hay).
    duration = duration_seconds if duration_seconds is not None else video_asset.duration_seconds
    frames = int((duration or 0) * (video_asset.fps or 0))
    estimated_bytes = estimate_png_frames_bytes(
        frames, video_asset.width or 0, video_asset.height or 0
    )
    required_bytes = (
        max(video_asset.file_size_bytes * TEMP_STORAGE_MULTIPLIER, estimated_bytes)
        + DISK_MARGIN_BYTES
    )
    if free_bytes < required_bytes:
        raise InsufficientTempStorageError(
            "Not enough free disk space to extract the frames: about "
            f"{required_bytes / GIB:.1f} GB are needed and {free_bytes / GIB:.1f} GB are free."
        )


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
            "process_id": None,
            "process_kind": None,
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


def get_reusable_extracted_frames(job) -> int | None:
    """Frames a previous run of this job (pause/resume, retry) already extracted, else None.

    The originals are complete, or the enhanced set is: after enhancement the originals are
    trimmed to the preview set and are no longer needed to continue.
    """
    expected = job.extracted_frames or 0
    if not job.extraction_completed_at or expected <= 0 or not job.original_frames_dir:
        return None
    originals_dir = Path(job.original_frames_dir)
    if not originals_dir.is_dir():
        return None
    if count_extracted_frames(originals_dir) == expected:
        return expected
    enhanced_dir = Path(job.enhanced_frames_dir) if job.enhanced_frames_dir else None
    if enhanced_dir and enhanced_dir.is_dir() and count_extracted_frames(enhanced_dir) >= expected:
        return expected
    return None


def _pre_ai_decode_filters(job, input_path: Path) -> str:
    from app.services.video_encoding_service import build_pre_ai_filters, combine_video_filters

    # Pipeline clásico (respaldo): sin sondeo extra; etiquetas del import o valores SD/HD.
    source = source_color_for_video(getattr(job, "video_asset", None), input_path, probe=False)
    enhancement_config = parse_enhancement_config_json(job.enhancement_config_json)
    return combine_video_filters(
        build_pre_ai_filters(enhancement_config), decode_color_filter(source)
    )


def extract_frames_for_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> object:
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()

    reusable_frames = get_reusable_extracted_frames(job)
    if reusable_frames is not None:
        # Al reanudar no se vuelve a ejecutar ffmpeg ni a retroceder el progreso.
        job_repository.update_job(
            db,
            job,
            {
                "status": "running",
                "progress_percent": max(job.progress_percent or 0.0, EXTRACTION_PROGRESS_END),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Reusing {reusable_frames} frames extracted earlier.",
            stage="extracting_frames",
        )
        db.commit()
        logger.info("Frame extraction skipped, frames already extracted: %s", job_id)
        return job

    try:
        input_path = resolve_job_input_video(job)
        ensure_temp_storage_capacity(job.video_asset, active_settings, effective_duration(job))
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
    command = build_frame_extraction_command(
        input_path,
        original_frames_dir,
        trim=get_job_trim(job),
        video_filters=_pre_ai_decode_filters(job, input_path),
    )
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
        encoding="utf-8",
        errors="replace",
        text=True,
        bufsize=1,
    )
    stderr_drain = StderrDrain(process.stderr)
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
        for raw_line in watch_process_output(
            process.stdout, active_settings.ffmpeg_stall_timeout_seconds
        ):
            if raw_line is None:
                # Sin salida de ffmpeg este segundo: comprobar la cancelación igualmente.
                db.refresh(job)
                if job.cancel_requested or job.status == "cancelled":
                    return finish_cancelled_ffmpeg_stage(
                        db, job, process, "Frame extraction cancelled by user."
                    )
                continue
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
                commit_progress(db)
                logger.debug("FFmpeg progress updated: %s", frames_processed)

            db.refresh(job)
            if job.cancel_requested or job.status == "cancelled":
                return finish_cancelled_ffmpeg_stage(
                    db, job, process, "Frame extraction cancelled by user."
                )

        stderr_output = stderr_drain.text()

        return_code = process.wait()
        # El cancel desde la API mata ffmpeg: stdout termina sin pasar por el chequeo del
        # bucle y el código de salida es != 0. No es un fallo, es una cancelación.
        db.refresh(job)
        if job.cancel_requested or job.status == "cancelled":
            return finish_cancelled_ffmpeg_stage(
                db, job, process, "Frame extraction cancelled by user."
            )
        if return_code != 0 and is_shutting_down():
            # Apagado del backend: el job queda como está y se marca `interrupted` al arrancar.
            unregister_process(job.id)
            logger.warning("Frame extraction stopped by backend shutdown: %s", job.id)
            return job
        if return_code != 0:
            unregister_process(job.id)
            if is_disk_full(stderr_output):
                disk_error = InsufficientDiskSpaceError()
                _mark_job_failed(
                    db, job, error_code=disk_error.error_code, error_message=disk_error.message
                )
                raise disk_error
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
    except FFmpegStalledError as exc:
        stop_process_quietly(process)
        unregister_process(job.id)
        _mark_job_failed(db, job, error_code=exc.error_code, error_message=exc.message)
        logger.error("FFmpeg frame extraction stalled: %s", job_id)
        raise
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


def finish_cancelled_ffmpeg_stage(db: Session, job, process, log_message: str) -> object:
    """Stop ffmpeg (if still alive) and leave the job cancelled, never failed."""
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
    unregister_process(job.id)
    job_repository.update_job(
        db,
        job,
        {
            "status": "cancelled",
            "current_stage": "cancelled",
            "cancelled_at": job.cancelled_at or time_to_datetime(time.time()),
            "process_id": None,
            "process_kind": None,
            "process_ended_at": time_to_datetime(time.time()),
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "warning",
        log_message,
        stage="cancelled",
    )
    db.commit()
    logger.warning("%s (%s)", log_message, job.id)
    return job


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
