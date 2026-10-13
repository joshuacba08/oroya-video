from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIModelDisabledError,
    AIModelFileNotFoundError,
    AIModelNotFoundError,
    AIRuntimeNotAvailableError,
    CUDANotAvailableError,
    CUDAOutOfMemoryError,
    InsufficientDiskSpaceError,
    InsufficientTempStorageError,
    InvalidFrameIndexError,
    JobNotFoundError,
    OriginalFramesNotFoundError,
    OroyaVideoError,
    RealESRGANDryRunFailedError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANJobNotReadyError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
    RealESRGANUnsupportedModelError,
    TorchNotAvailableError,
)
from app.core.logging import get_logger
from app.core.paths import (
    build_frame_file_name,
    ensure_ai_dry_runs_directory,
    get_job_enhanced_frames_path,
    get_model_path,
)
from app.db.database import commit_progress
from app.db.models import AIModel, ProcessingJob
from app.db.repositories import ai_model_repository, job_repository
from app.enhancers.realesrgan_enhancer import RealESRGANFrameEnhancer
from app.schemas.ai_runtime_schema import (
    AIModelValidationResponse,
    RealESRGANDryRunRequest,
    RealESRGANDryRunResponse,
)
from app.schemas.realesrgan_schema import (
    RealESRGANJobSummaryResponse,
    RealESRGANJobValidationResponse,
)
from app.services.ai_model_service import GENERAL_WDN_RELATIVE_PATH
from app.services.ai_runtime_service import (
    clear_cuda_cache_if_available,
    get_ai_runtime_status,
    get_missing_realesrgan_modules,
    resolve_ai_device,
)
from app.services.frame_extraction_service import time_to_datetime
from app.services.pipeline_progress import (
    ENHANCEMENT_PROGRESS_END,
    ENHANCEMENT_PROGRESS_START,
    calculate_stage_progress,
)
from app.utils.enhancement_config import parse_enhancement_config_json
from app.utils.image_utils import validate_input_image_path

logger = get_logger(__name__)

# Progreso y comprobaciones de cancelar/pausar como mucho cada este intervalo: con frames de
# ~100 ms, hacerlo en cada frame era un commit y un SELECT por frame.
DB_SYNC_INTERVAL_SECONDS = 0.5

# El modelo cargado se conserva entre jobs (cargarlo cuesta segundos y VRAM). Una sola entrada:
# si cambia el modelo o la configuración, se libera el anterior.
_enhancer_cache: dict[tuple, RealESRGANFrameEnhancer] = {}


# Por debajo de este espacio libre la mejora se pausa en vez de fallar con el disco lleno.
LOW_DISK_PAUSE_BYTES = int(1.5 * 1024**3)
DISK_CHECK_INTERVAL_SECONDS = 5.0


def free_disk_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def estimate_enhanced_bytes_needed(context: RealESRGANContext) -> int:
    """Space for the frames still to enhance: original size x outscale² per frame."""
    originals = [item for item in context.input_dir.glob("*.png") if item.is_file()]
    if not originals:
        return 0
    sample = originals[: min(len(originals), 20)]
    average_original = sum(item.stat().st_size for item in sample) / len(sample)
    done = sum(1 for item in context.output_dir.glob("*.png") if item.is_file())
    remaining = max(context.total_frames - done, 0)
    scale = context.scale or 4
    return int(remaining * average_original * scale * scale)


@dataclass(slots=True)
class RealESRGANContext:
    model_slug: str
    model_path: Path
    device: str
    scale: int | None
    tile_size: int
    tile_pad: int
    pre_pad: int
    half_precision: bool
    input_dir: Path
    output_dir: Path
    total_frames: int
    denoise_model_path: Path | None = None
    denoise_strength: float | None = None


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _get_job_or_raise(db: Session, job_id: str) -> ProcessingJob:
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    return job


def _get_model_or_raise(db: Session, model_slug: str) -> AIModel:
    model = ai_model_repository.get_ai_model_by_slug(db, model_slug)
    if not model:
        raise AIModelNotFoundError()
    return model


def _deserialize_job_enhancement_config(job: ProcessingJob) -> dict[str, object]:
    return parse_enhancement_config_json(job.enhancement_config_json)


def _resolve_job_model_slug(job: ProcessingJob) -> str:
    enhancement_config = _deserialize_job_enhancement_config(job)
    configured_slug = enhancement_config.get("model_id")
    if isinstance(configured_slug, str) and configured_slug.strip():
        return configured_slug.strip()
    if job.ai_model_slug.strip():
        return job.ai_model_slug.strip()
    raise AIModelNotFoundError()


def _count_png_frames(frames_dir: Path) -> int:
    return sum(1 for frame in frames_dir.glob("*.png") if frame.is_file())


def _resolve_model_file_info(
    model: AIModel,
    settings: Settings | None = None,
) -> tuple[Path | None, bool, int | None]:
    if not model.relative_path:
        return None, False, None

    candidate_path = get_model_path(model.relative_path, settings)
    if not candidate_path.exists() or not candidate_path.is_file():
        return candidate_path, False, None

    try:
        file_size_bytes = candidate_path.stat().st_size
    except OSError:
        return candidate_path, False, None

    if file_size_bytes <= 0:
        return candidate_path, False, file_size_bytes

    return candidate_path, True, file_size_bytes


def _resolve_runtime_device(
    settings: Settings | None = None,
    *,
    raise_on_unavailable: bool,
) -> tuple[str | None, list[str], bool]:
    runtime_status = get_ai_runtime_status(settings)
    warnings = list(runtime_status.warnings)
    if runtime_status.selected_device is not None:
        return runtime_status.selected_device, warnings, runtime_status.available
    if not raise_on_unavailable:
        return None, warnings, runtime_status.available
    active_settings = _get_active_settings(settings)
    return (
        resolve_ai_device(
            active_settings.ai_device,
            allow_cpu=active_settings.ai_allow_cpu,
        ),
        warnings,
        runtime_status.available,
    )


def validate_realesrgan_model(
    db: Session,
    model_slug: str,
    settings: Settings | None = None,
) -> AIModelValidationResponse:
    logger.info("Real-ESRGAN model validation requested: %s", model_slug)
    model = _get_model_or_raise(db, model_slug)

    warnings: list[str] = []
    file_path, is_installed, file_size_bytes = _resolve_model_file_info(model, settings)
    device, runtime_warnings, runtime_available = _resolve_runtime_device(
        settings,
        raise_on_unavailable=False,
    )
    warnings.extend(runtime_warnings)
    if runtime_available:
        missing_modules = get_missing_realesrgan_modules()
        if missing_modules:
            runtime_available = False
            warnings.append(
                "Real-ESRGAN Python packages are missing or broken: " + ", ".join(missing_modules)
            )

    if not model.is_enabled:
        warnings.append("Selected Real-ESRGAN model is disabled.")
    if file_path is None:
        warnings.append("Model file path is not configured.")
    elif not is_installed:
        if file_size_bytes == 0:
            warnings.append("Model file is empty.")
        else:
            warnings.append("Model file does not exist.")

    can_run = model.is_enabled and is_installed and runtime_available and device is not None
    response = AIModelValidationResponse(
        model_slug=model.slug,
        exists_in_registry=True,
        is_enabled=model.is_enabled,
        is_installed=is_installed,
        file_path=str(file_path) if file_path is not None else None,
        file_exists=is_installed,
        file_size_bytes=file_size_bytes,
        estimated_vram_mb=model.estimated_vram_mb,
        runtime_available=runtime_available,
        can_run=can_run,
        device=device,
        warnings=warnings,
    )
    logger.info("Real-ESRGAN model validation completed: %s", model_slug)
    return response


def resolve_realesrgan_model_path(
    db: Session,
    model_slug: str,
    settings: Settings | None = None,
) -> Path:
    logger.info("Real-ESRGAN model file resolved: %s", model_slug)
    model = _get_model_or_raise(db, model_slug)
    if not model.is_enabled:
        raise AIModelDisabledError()

    file_path, is_installed, _ = _resolve_model_file_info(model, settings)
    if not is_installed or file_path is None:
        raise AIModelFileNotFoundError()
    return file_path.resolve()


def resolve_dry_run_input_frame(
    db: Session,
    request: RealESRGANDryRunRequest,
) -> Path:
    if request.input_frame_path:
        return validate_input_image_path(Path(request.input_frame_path))

    if request.job_id is None or request.frame_index is None:
        raise RealESRGANDryRunFailedError()
    if request.frame_index < 0:
        raise InvalidFrameIndexError()

    job = _get_job_or_raise(db, request.job_id)
    if not job.original_frames_dir:
        raise OriginalFramesNotFoundError()

    frame_path = Path(job.original_frames_dir) / build_frame_file_name(request.frame_index)
    return validate_input_image_path(frame_path)


def run_realesrgan_dry_run(
    db: Session,
    request: RealESRGANDryRunRequest,
    settings: Settings | None = None,
) -> RealESRGANDryRunResponse:
    active_settings = _get_active_settings(settings)
    logger.info("Real-ESRGAN dry-run requested: %s", request.model_slug)

    try:
        input_frame_path = resolve_dry_run_input_frame(db, request)
        model = _get_model_or_raise(db, request.model_slug)
        if not model.is_enabled:
            raise AIModelDisabledError()

        model_path = resolve_realesrgan_model_path(db, model.slug, active_settings)
        device, warnings, _ = _resolve_runtime_device(
            active_settings,
            raise_on_unavailable=True,
        )
        if device is None:
            raise AIRuntimeNotAvailableError()

        enhancer = RealESRGANFrameEnhancer(
            model_path=model_path,
            model_slug=model.slug,
            device=device,
            scale=model.scale_factor,
            tile_size=active_settings.realesrgan_tile_size,
            tile_pad=active_settings.realesrgan_tile_pad,
            pre_pad=active_settings.realesrgan_pre_pad,
            half_precision=active_settings.ai_half_precision,
            max_failed_frames=active_settings.realesrgan_max_failed_frames,
            clear_cuda_cache=active_settings.realesrgan_clear_cuda_cache,
        )
        dry_runs_dir = ensure_ai_dry_runs_directory(active_settings)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_frame_path = dry_runs_dir / f"{model.slug}_{timestamp}.png"
        output_frame_path.parent.mkdir(parents=True, exist_ok=True)
        output_path, elapsed_time_ms = enhancer.enhance_single_frame(
            input_frame_path,
            output_frame_path,
        )
    except (
        AIModelDisabledError,
        AIModelFileNotFoundError,
        AIModelNotFoundError,
        AIRuntimeNotAvailableError,
        CUDANotAvailableError,
        CUDAOutOfMemoryError,
        InvalidFrameIndexError,
        JobNotFoundError,
        OriginalFramesNotFoundError,
        RealESRGANFrameProcessingFailedError,
        RealESRGANModelLoadFailedError,
        RealESRGANNotAvailableError,
        RealESRGANUnsupportedModelError,
        TorchNotAvailableError,
    ):
        logger.warning("Real-ESRGAN dry-run failed: %s", request.model_slug, exc_info=True)
        raise
    except OroyaVideoError:
        raise
    except Exception as exc:  # pragma: no cover - defensive runtime wrapper
        logger.exception("Real-ESRGAN dry-run failed")
        raise RealESRGANDryRunFailedError() from exc

    logger.info("Real-ESRGAN dry-run completed: %s", request.model_slug)
    return RealESRGANDryRunResponse(
        success=True,
        model_slug=model.slug,
        engine="realesrgan",
        device=device,
        input_frame_path=str(input_frame_path),
        output_frame_path=str(output_path),
        elapsed_time_ms=elapsed_time_ms,
        message="Real-ESRGAN dry-run completed successfully.",
        warnings=warnings,
    )


ENHANCEMENT_SCALE_TO_OUTSCALE = {"original": 1, "2x": 2, "4x": 4}


def resolve_enhancement_outscale(
    enhancement_config: dict[str, object],
    model: AIModel,
) -> int | None:
    configured_scale = enhancement_config.get("scale")
    if isinstance(configured_scale, str):
        outscale = ENHANCEMENT_SCALE_TO_OUTSCALE.get(configured_scale.strip().lower())
        if outscale is not None:
            return outscale
    return model.scale_factor


def prepare_realesrgan_context(
    db: Session,
    job: ProcessingJob,
    settings: Settings | None = None,
) -> RealESRGANContext:
    active_settings = _get_active_settings(settings)
    model_slug = _resolve_job_model_slug(job)
    model = _get_model_or_raise(db, model_slug)
    model_path = resolve_realesrgan_model_path(db, model.slug, active_settings)
    device, _, _ = _resolve_runtime_device(active_settings, raise_on_unavailable=True)
    if device is None:
        raise AIRuntimeNotAvailableError()

    if not job.original_frames_dir:
        raise OriginalFramesNotFoundError()
    input_dir = Path(job.original_frames_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise OriginalFramesNotFoundError()

    total_frames = _count_png_frames(input_dir)
    if total_frames <= 0:
        raise OriginalFramesNotFoundError()

    output_dir = get_job_enhanced_frames_path(job.id, active_settings)
    output_dir.mkdir(parents=True, exist_ok=True)

    enhancement_config = _deserialize_job_enhancement_config(job)
    context = RealESRGANContext(
        model_slug=model.slug,
        model_path=model_path,
        device=device,
        scale=resolve_enhancement_outscale(enhancement_config, model),
        tile_size=active_settings.realesrgan_tile_size,
        tile_pad=active_settings.realesrgan_tile_pad,
        pre_pad=active_settings.realesrgan_pre_pad,
        half_precision=active_settings.ai_half_precision and device == "cuda",
        input_dir=input_dir,
        output_dir=output_dir,
        total_frames=total_frames,
    )
    logger.info("Real-ESRGAN context prepared: %s", job.id)
    return context


def get_streaming_enhancer(
    db: Session,
    job: ProcessingJob,
    settings: Settings | None = None,
) -> RealESRGANFrameEnhancer:
    """Real-ESRGAN for the streaming pipeline: same model, device and scale as the classic
    one, but frames come in memory instead of from an extracted-frames folder."""
    active_settings = _get_active_settings(settings)
    model = _get_model_or_raise(db, _resolve_job_model_slug(job))
    model_path = resolve_realesrgan_model_path(db, model.slug, active_settings)
    device, _, _ = _resolve_runtime_device(active_settings, raise_on_unavailable=True)
    if device is None:
        raise AIRuntimeNotAvailableError()
    working_dir = Path(job.working_dir or ".")
    enhancement_config = _deserialize_job_enhancement_config(job)
    denoise_model_path = get_model_path(GENERAL_WDN_RELATIVE_PATH, active_settings)
    model_denoise = enhancement_config.get("model_denoise")
    context = RealESRGANContext(
        model_slug=model.slug,
        model_path=model_path,
        device=device,
        scale=resolve_enhancement_outscale(_deserialize_job_enhancement_config(job), model),
        tile_size=active_settings.realesrgan_tile_size,
        tile_pad=active_settings.realesrgan_tile_pad,
        pre_pad=active_settings.realesrgan_pre_pad,
        half_precision=active_settings.ai_half_precision and device == "cuda",
        input_dir=working_dir,
        output_dir=working_dir,
        total_frames=0,
        denoise_model_path=denoise_model_path if denoise_model_path.is_file() else None,
        denoise_strength=(
            model_denoise / 100
            if isinstance(model_denoise, int) and not isinstance(model_denoise, bool)
            else DEFAULT_MODEL_DENOISE
        ),
    )
    return _get_enhancer(context, active_settings)


# Reducción de ruido por defecto del modelo General (la del -dn oficial).
DEFAULT_MODEL_DENOISE = 0.5


def validate_realesrgan_job_requirements(
    db: Session,
    job: ProcessingJob,
    settings: Settings | None = None,
) -> RealESRGANJobValidationResponse:
    logger.info("Real-ESRGAN job validation requested: %s", job.id)
    warnings: list[str] = []
    model_slug = None
    estimated_vram_mb: int | None = None
    model_installed = False
    input_frames_available = False
    device: str | None = None

    try:
        model_slug = _resolve_job_model_slug(job)
        model = _get_model_or_raise(db, model_slug)
        estimated_vram_mb = model.estimated_vram_mb
        if not model.is_enabled:
            warnings.append("Selected Real-ESRGAN model is disabled.")
        file_path, model_installed, file_size_bytes = _resolve_model_file_info(model, settings)
        if not model_installed:
            if file_path is None:
                warnings.append("Selected Real-ESRGAN model path is not configured.")
            elif file_size_bytes == 0:
                warnings.append("Selected Real-ESRGAN model file is empty.")
            else:
                warnings.append("Selected Real-ESRGAN model is not installed.")
    except AIModelNotFoundError:
        warnings.append("Selected Real-ESRGAN model was not found in the registry.")
        model = None
    else:
        if not model.is_enabled:
            model_installed = False

    if job.original_frames_dir:
        input_dir = Path(job.original_frames_dir)
        input_frames_available = input_dir.exists() and _count_png_frames(input_dir) > 0
    if not input_frames_available:
        warnings.append("Original frames are not available for Real-ESRGAN.")

    try:
        device, runtime_warnings, _ = _resolve_runtime_device(settings, raise_on_unavailable=True)
    except (AIRuntimeNotAvailableError, CUDANotAvailableError, TorchNotAvailableError) as exc:
        runtime_status = get_ai_runtime_status(settings)
        warnings.extend(runtime_status.warnings)
        warnings.append(exc.message)
    else:
        warnings.extend(runtime_warnings)

    ready = (
        model_slug is not None
        and model_installed
        and input_frames_available
        and device is not None
        and not any(
            warning.startswith("Selected Real-ESRGAN model is disabled") for warning in warnings
        )
    )
    return RealESRGANJobValidationResponse(
        job_id=job.id,
        ready=ready,
        model_slug=model_slug,
        model_installed=model_installed,
        input_frames_available=input_frames_available,
        device=device,
        estimated_vram_mb=estimated_vram_mb,
        warnings=warnings,
    )


def ensure_realesrgan_job_ready(
    db: Session,
    job: ProcessingJob,
    settings: Settings | None = None,
) -> RealESRGANJobValidationResponse:
    validation = validate_realesrgan_job_requirements(db, job, settings)
    if not validation.ready:
        raise RealESRGANJobNotReadyError()
    return validation


def _mark_realesrgan_failed(
    db: Session,
    job: ProcessingJob,
    exc: OroyaVideoError,
) -> None:
    completed_at = time_to_datetime(time.time())
    job_repository.update_job(
        db,
        job,
        {
            "status": "failed",
            "current_stage": "failed",
            "error_code": exc.error_code,
            "error_message": exc.message,
            "enhancement_error_code": exc.error_code,
            "enhancement_error_message": exc.message,
            "enhancement_completed_at": completed_at,
            "realesrgan_error_code": exc.error_code,
            "realesrgan_error_message": exc.message,
            "realesrgan_completed_at": completed_at,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "error",
        f"Real-ESRGAN enhancement failed: {exc.message}",
        stage="failed",
    )
    db.commit()


def _enhancer_cache_key(context: RealESRGANContext, settings: Settings) -> tuple:
    return (
        str(context.model_path),
        context.model_slug,
        context.device,
        context.scale,
        context.tile_size,
        context.tile_pad,
        context.pre_pad,
        context.half_precision,
        settings.realesrgan_max_failed_frames,
        settings.realesrgan_clear_cuda_cache,
        str(context.denoise_model_path),
        context.denoise_strength,
    )


def release_cached_enhancer() -> None:
    if _enhancer_cache:
        _enhancer_cache.clear()
        clear_cuda_cache_if_available()


def _get_enhancer(context: RealESRGANContext, settings: Settings) -> RealESRGANFrameEnhancer:
    key = _enhancer_cache_key(context, settings)
    cached = _enhancer_cache.get(key)
    if cached is not None:
        cached.reset_counters()
        return cached
    release_cached_enhancer()
    enhancer = RealESRGANFrameEnhancer(
        model_path=context.model_path,
        model_slug=context.model_slug,
        device=context.device,
        scale=context.scale,
        tile_size=context.tile_size,
        tile_pad=context.tile_pad,
        pre_pad=context.pre_pad,
        half_precision=context.half_precision,
        max_failed_frames=settings.realesrgan_max_failed_frames,
        clear_cuda_cache=settings.realesrgan_clear_cuda_cache,
        denoise_model_path=context.denoise_model_path,
        denoise_strength=context.denoise_strength,
    )
    _enhancer_cache[key] = enhancer
    return enhancer


def process_realesrgan_frames_for_job(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> ProcessingJob:
    active_settings = _get_active_settings(settings)
    job = _get_job_or_raise(db, job_id)
    if job.cancel_requested or job.status == "cancelled":
        return job

    context = prepare_realesrgan_context(db, job, active_settings)
    needed_bytes = estimate_enhanced_bytes_needed(context) + LOW_DISK_PAUSE_BYTES
    free_bytes = free_disk_bytes(context.output_dir)
    if free_bytes < needed_bytes:
        # Mejor avisar ahora que fallar tras horas de proceso.
        error = InsufficientTempStorageError(
            "Not enough free disk space to enhance the frames: about "
            f"{needed_bytes / 1024**3:.1f} GB are needed and {free_bytes / 1024**3:.1f} GB "
            "are free. Free some space or choose a smaller output scale."
        )
        _mark_realesrgan_failed(db, job, error)
        raise error
    enhancer = _get_enhancer(context, active_settings)
    low_disk = False
    last_disk_check = 0.0
    started_at = time.monotonic()
    now = time.time()
    last_logged_frame = 0
    last_sync = 0.0
    log_step = max(1, min(100, max(context.total_frames // 20, 1)))

    def progress_callback(processed: int, total: int) -> None:
        nonlocal last_logged_frame, last_sync
        progress_percent = calculate_stage_progress(
            processed,
            total,
            start=ENHANCEMENT_PROGRESS_START,
            end=ENHANCEMENT_PROGRESS_END,
            clamp_to=59.9,
        )
        job_repository.update_job(
            db,
            job,
            {
                "frames_processed": processed,
                "enhanced_frames": enhancer.processed_frames,
                "progress_percent": progress_percent,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
                "realesrgan_frames_total": total,
                "realesrgan_frames_processed": enhancer.processed_frames,
                "realesrgan_failed_frames": enhancer.failed_frames,
                "realesrgan_average_frame_time_ms": enhancer.average_frame_time_ms,
            },
        )
        if processed - last_logged_frame >= log_step:
            last_logged_frame = processed
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                f"Real-ESRGAN progress: {processed}/{total}",
                stage="enhancing_frames",
            )
        if processed >= total or time.monotonic() - last_sync >= DB_SYNC_INTERVAL_SECONDS:
            commit_progress(db)
            last_sync = time.monotonic()

    def sync_job_state() -> None:
        nonlocal last_sync
        if time.monotonic() - last_sync < DB_SYNC_INTERVAL_SECONDS:
            return
        # Guardar el progreso pendiente antes de recargar el job (refresh lo descartaría).
        commit_progress(db)
        db.refresh(job)
        last_sync = time.monotonic()

    def cancel_callback() -> bool:
        sync_job_state()
        return job.cancel_requested or job.status == "cancelled"

    def pause_callback() -> bool:
        nonlocal low_disk, last_disk_check
        sync_job_state()
        if time.monotonic() - last_disk_check >= DISK_CHECK_INTERVAL_SECONDS:
            last_disk_check = time.monotonic()
            if free_disk_bytes(context.output_dir) < LOW_DISK_PAUSE_BYTES:
                # Pausa en vez de fallo: al liberar espacio, reanudar sigue donde quedó.
                low_disk = True
                return True
        return bool(job.pause_requested)

    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "enhancing_frames",
            "frames_processed": 0,
            "enhancer_engine": "realesrgan",
            "enhanced_frames_dir": str(context.output_dir),
            "enhancement_started_at": job.enhancement_started_at or time_to_datetime(now),
            "enhancement_completed_at": None,
            "enhancement_error_code": None,
            "enhancement_error_message": None,
            "error_code": None,
            "error_message": None,
            "realesrgan_model_slug": context.model_slug,
            "realesrgan_model_path": str(context.model_path),
            "realesrgan_device": context.device,
            "realesrgan_scale": context.scale,
            "realesrgan_tile_size": context.tile_size,
            "realesrgan_tile_pad": context.tile_pad,
            "realesrgan_pre_pad": context.pre_pad,
            "realesrgan_half_precision": context.half_precision,
            "realesrgan_frames_total": context.total_frames,
            "realesrgan_frames_processed": 0,
            "realesrgan_failed_frames": 0,
            "realesrgan_average_frame_time_ms": None,
            "realesrgan_started_at": job.realesrgan_started_at or time_to_datetime(now),
            "realesrgan_completed_at": None,
            "realesrgan_error_code": None,
            "realesrgan_error_message": None,
            "process_kind": "realesrgan",
            "process_started_at": job.process_started_at or time_to_datetime(now),
            "process_ended_at": None,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Real-ESRGAN enhancement started.",
        stage="enhancing_frames",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Model: {context.model_slug}",
        stage="enhancing_frames",
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        f"Device: {context.device}",
        stage="enhancing_frames",
    )
    db.commit()

    try:
        logger.info("Real-ESRGAN model loading started: %s", job.id)
        enhancer.load_model()
        logger.info("Real-ESRGAN model loading completed: %s", job.id)
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            "Real-ESRGAN model loaded.",
            stage="enhancing_frames",
        )
        db.commit()

        logger.info("Real-ESRGAN batch processing started: %s", job.id)
        enhancer.enhance_frames(
            context.input_dir,
            context.output_dir,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            pause_callback=pause_callback,
        )
    except (
        AIModelFileNotFoundError,
        AIRuntimeNotAvailableError,
        CUDANotAvailableError,
        CUDAOutOfMemoryError,
        OriginalFramesNotFoundError,
        RealESRGANFrameProcessingFailedError,
        RealESRGANModelLoadFailedError,
        RealESRGANNotAvailableError,
        RealESRGANUnsupportedModelError,
        TorchNotAvailableError,
    ) as exc:
        db.rollback()
        logger.exception("Real-ESRGAN batch processing failed")
        _mark_realesrgan_failed(db, job, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive runtime wrapper
        db.rollback()
        logger.exception("Real-ESRGAN batch processing failed")
        wrapped_exc = RealESRGANFrameProcessingFailedError()
        _mark_realesrgan_failed(db, job, wrapped_exc)
        raise wrapped_exc from exc

    db.commit()
    db.refresh(job)
    if enhancer.tile_fallbacks:
        job_repository.update_job(db, job, {"realesrgan_tile_size": enhancer.tile_size})
        job_repository.create_job_log(
            db,
            job.id,
            "warning",
            "GPU memory was insufficient; Real-ESRGAN continued with tile size "
            f"{enhancer.tile_size}.",
            stage="enhancing_frames",
        )
        db.commit()
    if job.cancel_requested or job.status == "cancelled":
        cancelled_at = time_to_datetime(time.time())
        job_repository.update_job(
            db,
            job,
            {
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancelled_at": cancelled_at,
                "enhanced_frames": enhancer.processed_frames,
                "frames_processed": enhancer.completed_frames,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
                "realesrgan_frames_processed": enhancer.processed_frames,
                "realesrgan_failed_frames": enhancer.failed_frames,
                "realesrgan_average_frame_time_ms": enhancer.average_frame_time_ms,
                "realesrgan_completed_at": cancelled_at,
                "process_kind": None,
                "process_ended_at": cancelled_at,
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "warning",
            "Real-ESRGAN enhancement cancelled by user.",
            stage="cancelled",
        )
        db.commit()
        logger.warning("Real-ESRGAN enhancement cancelled: %s", job.id)
        return job

    if job.pause_requested or low_disk:
        paused_at = time_to_datetime(time.time())
        disk_error = InsufficientDiskSpaceError() if low_disk else None
        job_repository.update_job(
            db,
            job,
            {
                "status": "paused",
                "error_code": disk_error.error_code if disk_error else None,
                "error_message": disk_error.message if disk_error else None,
                "current_stage": "enhancing_frames",
                "enhanced_frames": enhancer.processed_frames,
                "frames_processed": enhancer.completed_frames,
                "elapsed_time_seconds": int(time.monotonic() - started_at),
                "realesrgan_frames_processed": enhancer.processed_frames,
                "realesrgan_failed_frames": enhancer.failed_frames,
                "realesrgan_average_frame_time_ms": enhancer.average_frame_time_ms,
                "process_kind": None,
                "process_ended_at": paused_at,
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "warning" if low_disk else "info",
            "Enhancement paused: the disk is almost full."
            if low_disk
            else "Enhancement paused by user.",
            stage="enhancing_frames",
        )
        db.commit()
        logger.info("Real-ESRGAN enhancement paused: %s", job.id)
        return job

    completed_at = time_to_datetime(time.time())
    enhanced_frames = _count_png_frames(context.output_dir)
    job_repository.update_job(
        db,
        job,
        {
            "status": "running",
            "current_stage": "enhancing_frames",
            "frames_total": job.frames_total or context.total_frames,
            "frames_processed": context.total_frames,
            "enhanced_frames": enhanced_frames,
            "progress_percent": ENHANCEMENT_PROGRESS_END,
            "elapsed_time_seconds": int(time.monotonic() - started_at),
            "enhancement_completed_at": completed_at,
            "realesrgan_frames_total": context.total_frames,
            "realesrgan_frames_processed": enhancer.processed_frames,
            "realesrgan_failed_frames": enhancer.failed_frames,
            "realesrgan_average_frame_time_ms": enhancer.average_frame_time_ms,
            "realesrgan_completed_at": completed_at,
            "enhanced_frames_size_bytes": sum(
                frame.stat().st_size
                for frame in context.output_dir.glob("*.png")
                if frame.is_file()
            ),
            "process_kind": None,
            "process_ended_at": completed_at,
        },
    )
    job_repository.create_job_log(
        db,
        job.id,
        "info",
        "Real-ESRGAN enhancement completed.",
        stage="enhancing_frames",
    )
    if enhancer.average_frame_time_ms is not None:
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Average frame time: {enhancer.average_frame_time_ms} ms",
            stage="enhancing_frames",
        )
    db.commit()
    logger.info("Real-ESRGAN batch processing completed: %s", job.id)
    return job


def get_realesrgan_job_summary(
    db: Session,
    job_id: str,
) -> RealESRGANJobSummaryResponse:
    job = _get_job_or_raise(db, job_id)
    return RealESRGANJobSummaryResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        model_slug=job.realesrgan_model_slug,
        model_path=job.realesrgan_model_path,
        device=job.realesrgan_device,
        scale=job.realesrgan_scale,
        tile_size=job.realesrgan_tile_size,
        tile_pad=job.realesrgan_tile_pad,
        pre_pad=job.realesrgan_pre_pad,
        half_precision=job.realesrgan_half_precision,
        frames_total=job.realesrgan_frames_total,
        frames_processed=job.realesrgan_frames_processed,
        failed_frames=job.realesrgan_failed_frames,
        average_frame_time_ms=job.realesrgan_average_frame_time_ms,
        started_at=job.realesrgan_started_at,
        completed_at=job.realesrgan_completed_at,
        error_code=job.realesrgan_error_code,
        error_message=job.realesrgan_error_message,
    )
