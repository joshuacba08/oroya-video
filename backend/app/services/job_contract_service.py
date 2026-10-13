from __future__ import annotations

from app.db.models import ProcessingJob
from app.services.pipeline_progress import (
    ENCODING_PROGRESS_END,
    ENCODING_PROGRESS_START,
    ENHANCEMENT_PROGRESS_END,
    ENHANCEMENT_PROGRESS_START,
    EXPORT_PROGRESS_END,
    EXPORT_PROGRESS_START,
    EXTRACTION_PROGRESS_END,
    EXTRACTION_PROGRESS_START,
    FACE_RESTORE_PROGRESS_END,
    FACE_RESTORE_PROGRESS_START,
    MUX_PROGRESS_END,
    MUX_PROGRESS_START,
    PROCESSING_PROGRESS_END,
    PROCESSING_PROGRESS_START,
)

STAGE_LABELS = {
    "idle": "Idle",
    "preflight": "Preflight",
    "queued": "Queued",
    "recovering": "Recovering",
    "retrying": "Retrying",
    "extracting_frames": "Extracting frames",
    "processing": "Processing frames",
    "enhancing_frames": "Enhancing frames",
    "restoring_faces": "Restoring faces",
    "encoding_video": "Encoding video",
    "muxing_audio": "Muxing audio",
    "exporting": "Exporting",
    "cleaning": "Cleaning",
    "interrupted": "Interrupted",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


def build_job_actions(job: ProcessingJob) -> dict[str, bool]:
    can_retry = job.status in {"failed", "cancelled", "interrupted"} and (
        job.retry_count < job.max_retries
    )
    return {
        "can_start": job.status in {"pending", "paused"},
        "can_cancel": job.status in {"pending", "queued", "running", "paused", "retrying"},
        "can_pause": job.status == "queued"
        or (
            job.status == "running"
            and job.current_stage in PAUSABLE_STAGES
            and not job.pause_requested
        ),
        "can_retry": can_retry,
        "can_cleanup": job.status not in {"queued", "running", "retrying", "cleaning"},
        "can_delete": job.status != "running",
        "can_open_export": bool(job.final_export_path),
    }


# Etapas que se detienen limpiamente y se reanudan donde quedaron.
PAUSABLE_STAGES = {"enhancing_frames", "processing"}


def build_stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage.replace("_", " ").title())


def build_stage_progress_percent(job: ProcessingJob) -> float:
    progress = float(job.progress_percent or 0.0)
    stage = job.current_stage
    if stage == "extracting_frames":
        return _relative_stage_progress(
            progress,
            EXTRACTION_PROGRESS_START,
            EXTRACTION_PROGRESS_END,
        )
    if stage == "enhancing_frames":
        return _relative_stage_progress(
            progress, ENHANCEMENT_PROGRESS_START, ENHANCEMENT_PROGRESS_END
        )
    if stage == "processing":
        return _relative_stage_progress(
            progress, PROCESSING_PROGRESS_START, PROCESSING_PROGRESS_END
        )
    if stage == "restoring_faces":
        return _relative_stage_progress(
            progress, FACE_RESTORE_PROGRESS_START, FACE_RESTORE_PROGRESS_END
        )
    if stage == "encoding_video":
        return _relative_stage_progress(progress, ENCODING_PROGRESS_START, ENCODING_PROGRESS_END)
    if stage == "muxing_audio":
        return _relative_stage_progress(progress, MUX_PROGRESS_START, MUX_PROGRESS_END)
    if stage == "exporting":
        return _relative_stage_progress(progress, EXPORT_PROGRESS_START, EXPORT_PROGRESS_END)
    if stage == "completed":
        return 100.0
    return 0.0


def _relative_stage_progress(progress: float, start: float, end: float) -> float:
    if end <= start:
        return 0.0
    return round(max(min(((progress - start) / (end - start)) * 100.0, 100.0), 0.0), 2)


def is_preview_available(job: ProcessingJob) -> bool:
    return bool(job.original_frames_dir and job.enhanced_frames_dir and job.enhanced_frames > 0)


def is_export_available(job: ProcessingJob) -> bool:
    return bool(job.final_export_path)


# Velocidad de referencia del encode libx264 para estimar antes de llegar a esa etapa.
ENCODE_FRAMES_PER_SECOND_GUESS = 60.0
MUX_SECONDS_GUESS = 3
# Por debajo de esta fracción de la etapa, extrapolar el tiempo es poco fiable.
MIN_STAGE_FRACTION_FOR_ETA = 0.03


def _encode_seconds_guess(total_frames: int) -> int:
    return int(total_frames / ENCODE_FRAMES_PER_SECOND_GUESS) + MUX_SECONDS_GUESS


def _extrapolate_stage(job: ProcessingJob) -> int | None:
    fraction = build_stage_progress_percent(job) / 100.0
    elapsed = job.elapsed_time_seconds or 0
    if fraction < MIN_STAGE_FRACTION_FOR_ETA or elapsed <= 0:
        return None
    return int(elapsed * (1.0 - fraction) / fraction)


def estimate_remaining_seconds(job: ProcessingJob) -> int | None:
    """Remaining time for an active job, or None when there is not enough data yet."""
    if job.status not in {"running", "queued"}:
        return None
    total_frames = job.realesrgan_frames_total or job.frames_total or 0
    stage = job.current_stage

    if stage == "processing":
        # Streaming: decodificar, mejorar y codificar en el mismo ms/frame medido.
        average_ms = job.realesrgan_average_frame_time_ms
        if not average_ms or not total_frames:
            return _extrapolate_stage(job)
        remaining_frames = max(total_frames - (job.frames_processed or 0), 0)
        return int(remaining_frames * average_ms / 1000) + MUX_SECONDS_GUESS
    if stage == "enhancing_frames":
        average_ms = job.realesrgan_average_frame_time_ms
        if not average_ms or not total_frames:
            return _extrapolate_stage(job)
        done = job.realesrgan_frames_processed or job.frames_processed or 0
        remaining_frames = max(total_frames - done, 0)
        return int(remaining_frames * average_ms / 1000) + _encode_seconds_guess(total_frames)
    if stage == "restoring_faces":
        remaining = _extrapolate_stage(job)
        return None if remaining is None else remaining + _encode_seconds_guess(total_frames)
    if stage == "encoding_video":
        remaining = _extrapolate_stage(job)
        return None if remaining is None else remaining + MUX_SECONDS_GUESS
    if stage in {"muxing_audio", "exporting"}:
        return _extrapolate_stage(job) or MUX_SECONDS_GUESS
    # Extracción o en cola: aún no se sabe cuánto tarda la mejora.
    return None
