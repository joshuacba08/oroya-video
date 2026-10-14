"""Motion preview (REQ-043): process a few seconds with the project's settings and play them
next to the same original fragment, before processing the whole video.

A preview is a regular job (`job_kind = "preview"`) run by the same streaming pipeline, so
what you see is exactly what the export will look like. It skips the export step, is hidden
from the queue, the dashboard and the history, goes ahead of waiting exports and is deleted
when the next one is made (and at startup).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    InvalidProjectConfigurationError,
    JobNotFoundError,
    PreviewNotAvailableError,
)
from app.core.logging import get_logger
from app.db.models import ProcessingJob
from app.db.repositories import job_repository
from app.db.repositories.job_repository import PREVIEW_JOB_KIND
from app.schemas.job_schema import JobControlResponse, JobCreateRequest
from app.services import job_workspace_service
from app.services.frame_extraction_service import (
    resolve_job_input_video,
    time_to_datetime,
    validate_ffmpeg_available,
)
from app.services.job_preflight_service import ensure_job_preflight_ready
from app.services.tool_detection_service import resolve_tool_path
from app.services.video_encoding_service import EVEN_DIMENSIONS_FILTER
from app.utils.color import OUTPUT_COLOR_ARGS, encode_color_filter
from app.utils.trim import MIN_TRIM_SECONDS
from app.workers.queue import PRIORITY_PREVIEW, job_queue

logger = get_logger(__name__)

DEFAULT_PREVIEW_SECONDS = 3.0
MAX_PREVIEW_SECONDS = 5.0
ORIGINAL_CLIP_NAME = "preview_original.mp4"


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _preview_jobs(db: Session, project_id: str | None = None) -> list[ProcessingJob]:
    query = db.query(ProcessingJob).filter(ProcessingJob.job_kind == PREVIEW_JOB_KIND)
    if project_id:
        query = query.filter(ProcessingJob.project_id == project_id)
    return query.all()


def delete_previews(
    db: Session, settings: Settings, project_id: str | None = None, keep_running: bool = True
) -> int:
    """Delete preview jobs and their files (those running are left alone when asked)."""
    deleted = 0
    for job in _preview_jobs(db, project_id):
        if keep_running and job.status in {"running", "queued"}:
            continue
        job_id, owner = job.id, job.project_id
        job_repository.delete_job(db, job)
        db.commit()
        job_workspace_service.delete_job_files(job_id, owner, settings, [])
        deleted += 1
    return deleted


async def create_preview_clip(
    db: Session,
    project_id: str,
    start_seconds: float,
    duration_seconds: float = DEFAULT_PREVIEW_SECONDS,
    settings: Settings | None = None,
) -> JobControlResponse:
    from app.services.job_service import create_processing_job

    active_settings = _get_active_settings(settings)
    duration_seconds = min(max(duration_seconds, MIN_TRIM_SECONDS), MAX_PREVIEW_SECONDS)
    delete_previews(db, active_settings, project_id)

    created = create_processing_job(db, JobCreateRequest(project_id=project_id), active_settings)
    job = job_repository.get_job_by_id(db, created.job.id)
    video_duration = created.video.duration_seconds or 0
    start = max(start_seconds, 0.0)
    if video_duration:
        start = min(start, max(video_duration - MIN_TRIM_SECONDS, 0.0))
    end = start + duration_seconds
    if video_duration:
        end = min(end, video_duration)
    if end - start < MIN_TRIM_SECONDS:
        job_repository.delete_job(db, job)
        db.commit()
        raise InvalidProjectConfigurationError("The preview fragment is too short.")

    export_config = json.loads(job.export_config_json or "{}")
    export_config["trim"] = {"start_seconds": round(start, 3), "end_seconds": round(end, 3)}
    job_repository.update_job(
        db,
        job,
        {
            "job_kind": PREVIEW_JOB_KIND,
            # Siempre por streaming: es lo que hará la exportación con estos ajustes.
            "pipeline_mode": "streaming",
            "export_config_json": json.dumps(export_config),
        },
    )
    db.commit()

    await asyncio.to_thread(ensure_job_preflight_ready, db, job.id, active_settings)
    job = job_repository.update_job(
        db,
        job,
        {"status": "queued", "current_stage": "queued", "queued_at": time_to_datetime(_now())},
    )
    job_repository.create_job_log(db, job.id, "info", "Motion preview queued.", stage="queued")
    db.commit()
    await job_queue.enqueue(job.id, priority=PRIORITY_PREVIEW)
    logger.info("Motion preview queued: %s (%s-%s s)", job.id, start, end)
    return JobControlResponse(job=job_repository.to_job_response(job), message="Preview queued.")


def _now() -> float:
    return time.time()


def build_original_clip_command(
    input_path: Path, output_path: Path, start: float, duration: float, width: int, height: int
) -> list[str]:
    """The same original fragment, upscaled with Lanczos to the preview size (no audio)."""
    video_filters = ",".join(
        [
            f"scale={width}:{height}:flags=lanczos",
            EVEN_DIMENSIONS_FILTER,
            encode_color_filter(),
        ]
    )
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        video_filters,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        *OUTPUT_COLOR_ARGS,
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _video_size(path: Path, settings: Settings) -> tuple[int, int]:
    ffprobe = resolve_tool_path("ffprobe", settings) or "ffprobe"
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )  # fmt: skip
    width, height = (int(value) for value in result.stdout.strip().split(","))
    return width, height


def finish_preview_job(db: Session, job: ProcessingJob, settings: Settings) -> None:
    """After processing and audio: make the original clip and mark the preview completed."""
    enhanced = Path(job.muxed_video_path or job.encoded_video_path or "")
    trim = json.loads(job.export_config_json or "{}").get("trim") or {}
    start = float(trim.get("start_seconds", 0))
    duration = float(trim.get("end_seconds", start + DEFAULT_PREVIEW_SECONDS)) - start
    ffmpeg_path = validate_ffmpeg_available()
    original = Path(job.working_dir or enhanced.parent) / ORIGINAL_CLIP_NAME
    width, height = _video_size(enhanced, settings)
    command = build_original_clip_command(
        resolve_job_input_video(job), original, start, duration, width, height
    )
    command[0] = ffmpeg_path
    subprocess.run(command, capture_output=True, timeout=300, check=True)
    job_repository.update_job(
        db,
        job,
        {
            "status": "completed",
            "current_stage": "completed",
            "progress_percent": 100.0,
            "completed_at": time_to_datetime(_now()),
            "final_export_path": None,
        },
    )
    job_repository.create_job_log(db, job.id, "info", "Motion preview ready.", stage="completed")
    db.commit()


def get_preview_clip_path(db: Session, job_id: str, variant: str) -> Path:
    job = job_repository.get_job_by_id(db, job_id)
    if job is None or job.job_kind != PREVIEW_JOB_KIND:
        raise JobNotFoundError()
    if job.status != "completed":
        raise PreviewNotAvailableError()
    if variant == "enhanced":
        path = Path(job.muxed_video_path or job.encoded_video_path or "")
    elif variant == "original":
        path = Path(job.working_dir or "") / ORIGINAL_CLIP_NAME
    else:
        raise PreviewNotAvailableError()
    if not path.is_file():
        raise PreviewNotAvailableError()
    return path
