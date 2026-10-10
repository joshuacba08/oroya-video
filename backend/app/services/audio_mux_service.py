from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AudioMuxFailedError,
    EncodedVideoNotFoundError,
    FFmpegNotAvailableError,
    InsufficientTempStorageError,
    JobNotFoundError,
    MuxedVideoNotFoundError,
)
from app.core.logging import get_logger
from app.core.paths import (
    ensure_job_muxed_directory,
    get_job_muxed_video_path,
    get_temp_path,
    resolve_path,
    to_client_path,
)
from app.db.repositories import job_repository
from app.schemas.job_schema import (
    AudioMuxSummaryResponse,
    DeleteMuxedVideoResponse,
    MuxedVideoResponse,
)
from app.services.frame_extraction_service import (
    finish_cancelled_ffmpeg_stage,
    time_to_datetime,
)
from app.services.pipeline_progress import MUX_PROGRESS_END, MUX_PROGRESS_START
from app.services.process_registry_service import (
    is_shutting_down,
    register_process,
    unregister_process,
)
from app.utils.enhancement_config import parse_enhancement_config_json
from app.utils.process_output import StderrDrain

logger = get_logger(__name__)
MUXED_VIDEO_FILE_NAME = "video_with_audio.mp4"
MUXED_VIDEO_FORMAT = "mp4"
MUXED_VIDEO_CODEC = "h264"


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _validate_ffmpeg_available() -> str:
    from app.services.tool_detection_service import resolve_tool_path

    ffmpeg_path = resolve_tool_path("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegNotAvailableError()
    return ffmpeg_path


def resolve_original_video_path(job) -> Path:
    video = job.video_asset or getattr(job, "video_asset", None)
    if video is None:
        raise EncodedVideoNotFoundError()
    if video.source_mode == "copy" and video.stored_path:
        return resolve_path(video.stored_path)
    return Path(video.source_path).expanduser().resolve()


def build_audio_copy_mux_command(
    silent_video_path: Path,
    original_video_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(silent_video_path),
        "-i",
        str(original_video_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-shortest",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]


def build_audio_aac_mux_command(
    silent_video_path: Path,
    original_video_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(silent_video_path),
        "-i",
        str(original_video_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "320k",
        "-shortest",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]


def build_no_audio_mux_command(
    silent_video_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(silent_video_path),
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]


def has_audio_stream(video_asset) -> bool:
    return bool(video_asset and getattr(video_asset, "has_audio", False))


def ensure_mux_storage_capacity(
    encoded_video_path: Path,
    settings: Settings | None = None,
) -> None:
    active_settings = _get_active_settings(settings)
    temp_path = get_temp_path(active_settings)
    _, _, free_bytes = shutil.disk_usage(temp_path)
    required_bytes = max(int(encoded_video_path.stat().st_size * 1.5), 1)
    if free_bytes < required_bytes:
        raise InsufficientTempStorageError(
            "Not enough temporary storage space to mux audio into the encoded video."
        )


def _mark_mux_failed(
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
            "audio_mux_error_code": error_code,
            "audio_mux_error_message": error_message,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "error",
        f"Audio mux failed: {error_message}",
        stage="failed",
    )
    db.commit()


def _run_mux_command(
    db: Session,
    job,
    command: list[str],
    started_at: float,
) -> tuple[str, str]:
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
    register_process(job.id, process_id, "ffmpeg_mux", process)
    job_repository.update_job(
        db,
        job,
        {
            "process_id": process_id,
            "process_kind": "ffmpeg_mux",
            "process_started_at": time_to_datetime(time.time()),
            "process_ended_at": None,
        },
    )
    db.commit()

    try:
        if process.stdout is not None:
            for raw_line in process.stdout:
                if raw_line.strip():
                    job_repository.update_job(
                        db,
                        job,
                        {
                            "progress_percent": max(job.progress_percent, MUX_PROGRESS_START + 1.0),
                            "elapsed_time_seconds": int(time.monotonic() - started_at),
                        },
                    )
                    db.commit()

                db.refresh(job)
                if job.cancel_requested or job.status == "cancelled":
                    finish_cancelled_ffmpeg_stage(db, job, process, "Audio mux cancelled by user.")
                    return "cancelled", ""

        stderr_output = stderr_drain.text()

        return_code = process.wait()
        db.refresh(job)
        if job.cancel_requested or job.status == "cancelled":
            finish_cancelled_ffmpeg_stage(db, job, process, "Audio mux cancelled by user.")
            return "cancelled", ""
        if return_code != 0 and is_shutting_down():
            # Apagado del backend: el job queda como está y se marca `interrupted` al arrancar.
            unregister_process(job.id)
            return "stopped", ""
        if return_code != 0:
            unregister_process(job.id)
            return "failed", stderr_output

        unregister_process(job.id)
        return "completed", stderr_output
    except OSError as exc:
        unregister_process(job.id)
        raise AudioMuxFailedError() from exc


def mux_audio_for_job(
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

    if not job.encoded_video_path:
        _mark_mux_failed(
            db,
            job,
            error_code="encoded_video_not_found",
            error_message="Encoded video was not found for this job.",
        )
        raise EncodedVideoNotFoundError()

    silent_video_path = Path(job.encoded_video_path)
    if not silent_video_path.exists() or not silent_video_path.is_file():
        _mark_mux_failed(
            db,
            job,
            error_code="encoded_video_not_found",
            error_message="Encoded video was not found for this job.",
        )
        raise EncodedVideoNotFoundError()

    try:
        ffmpeg_path = _validate_ffmpeg_available()
        ensure_mux_storage_capacity(silent_video_path, active_settings)
    except (FFmpegNotAvailableError, InsufficientTempStorageError) as exc:
        _mark_mux_failed(
            db,
            job,
            error_code=exc.error_code,
            error_message=exc.message,
        )
        raise

    original_video_path = resolve_original_video_path(job)
    ensure_job_muxed_directory(job.id, active_settings)
    output_path = get_job_muxed_video_path(job.id, active_settings)
    if output_path.exists():
        output_path.unlink()

    started_at = time.monotonic()
    now = time.time()
    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "muxing_audio",
            "muxed_video_path": str(output_path),
            "muxed_video_file_name": MUXED_VIDEO_FILE_NAME,
            "audio_mux_started_at": job.audio_mux_started_at or time_to_datetime(now),
            "audio_mux_error_code": None,
            "audio_mux_error_message": None,
            "error_code": None,
            "error_message": None,
            "progress_percent": max(job.progress_percent, MUX_PROGRESS_START),
        },
    )
    job_repository.create_job_log(db, job.id, "info", "Audio mux started.", stage="muxing_audio")
    db.commit()

    video_asset = job.video_asset or getattr(job, "video_asset", None)
    export_config = parse_enhancement_config_json(job.export_config_json)
    keep_audio = export_config.get("keep_audio", True) is not False
    if not keep_audio and has_audio_stream(video_asset):
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Audio disabled by export settings.",
            stage="muxing_audio",
        )
        db.commit()
    if keep_audio and has_audio_stream(video_asset):
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Audio strategy: copy.",
            stage="muxing_audio",
        )
        db.commit()
        command = build_audio_copy_mux_command(silent_video_path, original_video_path, output_path)
        command[0] = ffmpeg_path
        status, stderr_output = _run_mux_command(db, job, command, started_at)
        if status in {"cancelled", "stopped"}:
            return job
        if status == "failed":
            if output_path.exists():
                output_path.unlink()
            job_repository.create_job_log(
                db,
                job.id,
                "warning",
                "Audio copy failed. Retrying with AAC fallback.",
                stage="muxing_audio",
            )
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                "Audio strategy: transcode_aac.",
                stage="muxing_audio",
            )
            db.commit()
            fallback_command = build_audio_aac_mux_command(
                silent_video_path,
                original_video_path,
                output_path,
            )
            fallback_command[0] = ffmpeg_path
            status, stderr_output = _run_mux_command(db, job, fallback_command, started_at)
            if status in {"cancelled", "stopped"}:
                return job
            if status == "failed":
                _mark_mux_failed(
                    db,
                    job,
                    error_code="audio_mux_failed",
                    error_message=(
                        stderr_output or "Audio could not be muxed into the encoded video."
                    ),
                )
                raise AudioMuxFailedError()
            audio_strategy = "transcode_aac"
            audio_codec = "aac"
        else:
            audio_strategy = "copy"
            audio_codec = getattr(video_asset, "audio_codec", None)
    else:
        if keep_audio:
            # Con keep_audio=False ya se registró "Audio disabled by export settings.".
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                "No audio stream detected. Exporting video without audio.",
                stage="muxing_audio",
            )
            db.commit()
        command = build_no_audio_mux_command(silent_video_path, output_path)
        command[0] = ffmpeg_path
        status, stderr_output = _run_mux_command(db, job, command, started_at)
        if status in {"cancelled", "stopped"}:
            return job
        if status == "failed":
            _mark_mux_failed(
                db,
                job,
                error_code="audio_mux_failed",
                error_message=stderr_output or "Audio could not be muxed into the encoded video.",
            )
            raise AudioMuxFailedError()
        audio_strategy = "none"
        audio_codec = None

    if not output_path.exists() or not output_path.is_file():
        _mark_mux_failed(
            db,
            job,
            error_code="audio_mux_failed",
            error_message="Audio could not be muxed into the encoded video.",
        )
        raise AudioMuxFailedError()

    output_size = output_path.stat().st_size
    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "muxing_audio",
            "muxed_video_path": str(output_path),
            "muxed_video_file_name": MUXED_VIDEO_FILE_NAME,
            "muxed_video_size_bytes": output_size,
            "audio_strategy": audio_strategy,
            "audio_codec": audio_codec,
            "audio_mux_completed_at": time_to_datetime(time.time()),
            "progress_percent": MUX_PROGRESS_END,
            "elapsed_time_seconds": int(time.monotonic() - started_at),
            "muxed_size_bytes": output_size,
            "process_id": None,
            "process_kind": None,
            "process_ended_at": time_to_datetime(time.time()),
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Audio mux completed.",
        stage="muxing_audio",
    )
    db.commit()
    logger.info("Audio mux completed: %s", job.id)
    return job


def get_muxed_video_summary(
    db: Session,
    job_id: str,
) -> AudioMuxSummaryResponse:
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    return AudioMuxSummaryResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        muxed_video_path=job.muxed_video_path,
        muxed_video_file_name=job.muxed_video_file_name,
        muxed_video_size_bytes=job.muxed_video_size_bytes,
        audio_strategy=job.audio_strategy,
        audio_codec=job.audio_codec,
        audio_mux_started_at=job.audio_mux_started_at,
        audio_mux_completed_at=job.audio_mux_completed_at,
        audio_mux_error_code=job.audio_mux_error_code,
        audio_mux_error_message=job.audio_mux_error_message,
    )


def get_muxed_video_metadata(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> MuxedVideoResponse:
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()

    available = False
    path: str | None = None
    file_name: str | None = None
    size_bytes: int | None = None
    if job.muxed_video_path:
        candidate = Path(job.muxed_video_path)
        if candidate.exists() and candidate.is_file():
            available = True
            path = to_client_path(candidate, active_settings)
            file_name = candidate.name
            size_bytes = candidate.stat().st_size

    return MuxedVideoResponse(
        job_id=job.id,
        available=available,
        path=path,
        file_name=file_name,
        size_bytes=size_bytes,
        format=MUXED_VIDEO_FORMAT,
        video_codec=MUXED_VIDEO_CODEC,
        audio_codec=job.audio_codec,
        has_audio=job.audio_strategy not in {None, "none"},
        audio_strategy=job.audio_strategy,
    )


def delete_muxed_video(
    db: Session,
    job_id: str,
) -> DeleteMuxedVideoResponse:
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    if not job.muxed_video_path:
        raise MuxedVideoNotFoundError()

    candidate = Path(job.muxed_video_path)
    if not candidate.exists() or not candidate.is_file():
        raise MuxedVideoNotFoundError()

    candidate.unlink()
    job_repository.update_job(
        db,
        job,
        {
            "muxed_video_path": None,
            "muxed_video_file_name": None,
            "muxed_video_size_bytes": None,
            "audio_strategy": None,
            "audio_codec": None,
            "audio_mux_started_at": None,
            "audio_mux_completed_at": None,
            "audio_mux_error_code": None,
            "audio_mux_error_message": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Muxed video deleted.",
        stage=job.current_stage,
    )
    db.commit()
    return DeleteMuxedVideoResponse(deleted=True, job_id=job.id)
