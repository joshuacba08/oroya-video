from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    FilteredPreviewFailedError,
    InvalidFrameIndexError,
    JobNotFoundError,
    PreviewFrameAccessDeniedError,
    PreviewFrameNotFoundError,
    PreviewNotAvailableError,
)
from app.core.logging import get_logger
from app.core.paths import (
    build_frame_file_name,
    get_job_filtered_frames_path,
    to_client_path,
)
from app.db.repositories import job_repository
from app.schemas.preview_schema import (
    CompareFrameResponse,
    PreviewFrameListItem,
    PreviewFrameListResponse,
    PreviewFrameResponse,
    PreviewInfoResponse,
)
from app.services.frame_extraction_service import validate_ffmpeg_available
from app.services.video_encoding_service import build_post_ai_filters
from app.utils.enhancement_config import parse_enhancement_config_json

logger = get_logger(__name__)
COMPARE_MODES = ["split", "slider", "side_by_side"]
FRAME_NAME_PATTERN = re.compile(r"^frame_(\d{8})\.png$")


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _get_job_or_raise(db: Session, job_id: str):
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    return job


def _validate_frame_index(frame_index: int) -> None:
    if frame_index < 0:
        raise InvalidFrameIndexError()


def _count_png_files(directory: Path | None) -> int:
    if directory is None or not directory.exists() or not directory.is_dir():
        return 0
    return sum(1 for item in directory.glob("*.png") if item.is_file())


def _collect_frame_indexes(directory: Path | None) -> set[int]:
    if directory is None or not directory.exists() or not directory.is_dir():
        return set()
    indexes: set[int] = set()
    for item in directory.glob("*.png"):
        if not item.is_file():
            continue
        match = FRAME_NAME_PATTERN.match(item.name)
        if match:
            indexes.add(int(match.group(1)))
    return indexes


def _resolve_frame_path(directory: Path, frame_index: int) -> Path:
    _validate_frame_index(frame_index)
    resolved_dir = directory.resolve()
    if not resolved_dir.exists() or not resolved_dir.is_dir():
        raise PreviewNotAvailableError()

    frame_path = (resolved_dir / build_frame_file_name(frame_index)).resolve()
    if frame_path.suffix.lower() != ".png":
        raise PreviewFrameAccessDeniedError()
    try:
        frame_path.relative_to(resolved_dir)
    except ValueError as exc:
        raise PreviewFrameAccessDeniedError() from exc
    if not frame_path.exists() or not frame_path.is_file():
        raise PreviewFrameNotFoundError()
    return frame_path


def _build_preview_frame_response(
    job,
    frame_index: int,
    frame_type: str,
    frame_path: Path,
    settings: Settings | None = None,
) -> PreviewFrameResponse:
    active_settings = _get_active_settings(settings)
    return PreviewFrameResponse(
        job_id=job.id,
        frame_index=frame_index,
        frame_type=frame_type,  # type: ignore[arg-type]
        file_name=frame_path.name,
        path=to_client_path(frame_path, active_settings),
        url=f"/api/v1/jobs/{job.id}/preview/{frame_type}/{frame_index}",
        available=True,
        size_bytes=frame_path.stat().st_size,
    )


def get_preview_info(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> PreviewInfoResponse:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    original_dir = Path(job.original_frames_dir) if job.original_frames_dir else None
    enhanced_dir = Path(job.enhanced_frames_dir) if job.enhanced_frames_dir else None

    original_count = _count_png_files(original_dir)
    enhanced_count = _count_png_files(enhanced_dir)
    if original_count == 0:
        raise PreviewNotAvailableError()

    # Los fotogramas no tienen por qué ser contiguos: el pipeline por streaming solo guarda
    # pares de muestra repartidos por el video. Se recomienda el par central.
    comparable = sorted(_collect_frame_indexes(original_dir) & _collect_frame_indexes(enhanced_dir))
    comparable_count = len(comparable)
    recommended_index = comparable[comparable_count // 2] if comparable else None

    return PreviewInfoResponse(
        job_id=job.id,
        project_id=job.project_id,
        status=job.status,
        current_stage=job.current_stage,
        original_frames_available=original_count > 0,
        enhanced_frames_available=enhanced_count > 0,
        original_frames_count=original_count,
        enhanced_frames_count=enhanced_count,
        comparable_frames_count=comparable_count,
        recommended_frame_index=recommended_index,
        frame_pattern=job.frame_file_pattern or "frame_%08d.png",
        frame_format=job.frame_format or "png",
        original_frames_dir=(
            to_client_path(original_dir, active_settings)
            if original_dir and original_dir.exists()
            else None
        ),
        enhanced_frames_dir=(
            to_client_path(enhanced_dir, active_settings)
            if enhanced_dir and enhanced_dir.exists()
            else None
        ),
    )


def get_original_frame_path(
    db: Session,
    job_id: str,
    frame_index: int,
) -> Path:
    job = _get_job_or_raise(db, job_id)
    if not job.original_frames_dir:
        raise PreviewNotAvailableError()
    return _resolve_frame_path(Path(job.original_frames_dir), frame_index)


def get_enhanced_frame_path(
    db: Session,
    job_id: str,
    frame_index: int,
) -> Path:
    job = _get_job_or_raise(db, job_id)
    if not job.enhanced_frames_dir:
        raise PreviewNotAvailableError()
    return _resolve_frame_path(Path(job.enhanced_frames_dir), frame_index)


def _build_filtered_preview_config(
    job,
    *,
    denoise: int | None,
    sharpen: int | None,
    compression_cleanup: bool | None,
) -> dict[str, object]:
    config = parse_enhancement_config_json(job.enhancement_config_json)
    if denoise is not None:
        config["denoise"] = denoise
    if sharpen is not None:
        config["sharpen"] = sharpen
    if compression_cleanup is not None:
        config["compression_cleanup"] = compression_cleanup
    return config


def get_filtered_frame_path(
    db: Session,
    job_id: str,
    frame_index: int,
    *,
    denoise: int | None = None,
    sharpen: int | None = None,
    compression_cleanup: bool | None = None,
    settings: Settings | None = None,
) -> Path:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if not job.enhanced_frames_dir:
        raise PreviewNotAvailableError()
    enhanced_path = _resolve_frame_path(Path(job.enhanced_frames_dir), frame_index)

    config = _build_filtered_preview_config(
        job,
        denoise=denoise,
        sharpen=sharpen,
        compression_cleanup=compression_cleanup,
    )
    # Los filtros previos (limpieza, ruido) se aplican antes de la IA: aquí solo los posteriores.
    video_filters = build_post_ai_filters(config)
    if not video_filters:
        return enhanced_path

    filters_hash = hashlib.sha1(video_filters.encode()).hexdigest()[:10]
    filtered_dir = get_job_filtered_frames_path(job.id, active_settings)
    filtered_path = filtered_dir / f"{enhanced_path.stem}_{filters_hash}.png"
    if filtered_path.is_file() and filtered_path.stat().st_size > 0:
        return filtered_path

    ffmpeg_path = validate_ffmpeg_available()
    filtered_dir.mkdir(parents=True, exist_ok=True)
    temp_path = filtered_path.with_name(f"{filtered_path.name}.tmp.png")
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-y",
        "-i",
        str(enhanced_path),
        "-vf",
        video_filters,
        "-frames:v",
        "1",
        str(temp_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        temp_path.unlink(missing_ok=True)
        logger.exception("Filtered preview render failed: %s", job_id)
        raise FilteredPreviewFailedError() from exc

    if result.returncode != 0 or not temp_path.is_file():
        temp_path.unlink(missing_ok=True)
        logger.warning(
            "Filtered preview render failed for job %s: %s",
            job_id,
            (result.stderr or "").strip()[:300],
        )
        raise FilteredPreviewFailedError()

    os.replace(temp_path, filtered_path)
    _prune_stale_filtered_variants(filtered_dir, enhanced_path.stem, filtered_path.name)
    logger.info("Filtered preview rendered: %s frame %s", job_id, frame_index)
    return filtered_path


def _prune_stale_filtered_variants(
    filtered_dir: Path,
    frame_stem: str,
    current_name: str,
) -> None:
    try:
        for variant in filtered_dir.glob(f"{frame_stem}_*.png"):
            if variant.name != current_name and variant.is_file():
                variant.unlink()
    except OSError:
        logger.warning("Could not prune stale filtered previews", exc_info=True)


def get_compare_frame_info(
    db: Session,
    job_id: str,
    frame_index: int,
    settings: Settings | None = None,
) -> CompareFrameResponse:
    job = _get_job_or_raise(db, job_id)
    original_path = get_original_frame_path(db, job_id, frame_index)
    enhanced_path = get_enhanced_frame_path(db, job_id, frame_index)
    return CompareFrameResponse(
        job_id=job.id,
        frame_index=frame_index,
        original=_build_preview_frame_response(
            job,
            frame_index,
            "original",
            original_path,
            settings,
        ),
        enhanced=_build_preview_frame_response(
            job,
            frame_index,
            "enhanced",
            enhanced_path,
            settings,
        ),
        compare_modes=COMPARE_MODES,
    )


def get_recommended_preview_frame_index(
    db: Session,
    job_id: str,
) -> int:
    info = get_preview_info(db, job_id)
    if info.comparable_frames_count <= 0 or info.recommended_frame_index is None:
        raise PreviewNotAvailableError()
    return info.recommended_frame_index


def list_preview_frames(
    db: Session,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
) -> PreviewFrameListResponse:
    job = _get_job_or_raise(db, job_id)
    original_dir = Path(job.original_frames_dir) if job.original_frames_dir else None
    enhanced_dir = Path(job.enhanced_frames_dir) if job.enhanced_frames_dir else None

    original_indexes = _collect_frame_indexes(original_dir)
    enhanced_indexes = _collect_frame_indexes(enhanced_dir)
    all_indexes = sorted(original_indexes | enhanced_indexes)
    if not all_indexes:
        raise PreviewNotAvailableError()

    paged_indexes = all_indexes[offset : offset + limit]
    items = [
        PreviewFrameListItem(
            index=index,
            file_name=build_frame_file_name(index),
            original_available=index in original_indexes,
            enhanced_available=index in enhanced_indexes,
            original_url=(
                f"/api/v1/jobs/{job.id}/preview/original/{index}"
                if index in original_indexes
                else None
            ),
            enhanced_url=(
                f"/api/v1/jobs/{job.id}/preview/enhanced/{index}"
                if index in enhanced_indexes
                else None
            ),
        )
        for index in paged_indexes
    ]
    return PreviewFrameListResponse(
        job_id=job.id,
        items=items,
        total=len(all_indexes),
        limit=limit,
        offset=offset,
    )
