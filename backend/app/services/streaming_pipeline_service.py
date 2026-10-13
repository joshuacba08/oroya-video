"""Streaming pipeline (REQ-036): decode → process in memory → encode in segments → concat.

Instead of extracting every frame to PNG (tens of GB for a long video), one ffmpeg decoder
streams `rgb24` frames through a pipe, each frame is enhanced in memory and written to an
ffmpeg encoder that produces a short MP4 segment. Disk use is bounded to the segments (the
final video size) plus a few preview samples.

- Segments are named `seg_<index>_<first source frame>_<frame count>.mp4` and written to a
  temporary file renamed when complete, so a finished segment is never half-written.
- Pause (and a backend shutdown) close the current segment early; resume seeks the decoder
  to the first frame not yet encoded. Cancel aborts the segment in progress.
- A few original/enhanced pairs are saved as PNG with their real frame index for the
  before/after preview, plus the latest processed pair for the live view.
- When every segment exists they are joined with `concat -c copy` into `video_silent.mp4`;
  audio mux and export then run as in the classic pipeline.
"""

from __future__ import annotations

import math
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AIModelFileNotFoundError,
    AIRuntimeNotAvailableError,
    CUDANotAvailableError,
    CUDAOutOfMemoryError,
    FaceRestoreFailedError,
    FaceRestoreNotAvailableError,
    FFmpegNotAvailableError,
    FFmpegStalledError,
    FrameEnhancerNotFoundError,
    FrameExtractionFailedError,
    FrameInterpolationFailedError,
    FrameInterpolationNotAvailableError,
    InsufficientDiskSpaceError,
    JobNotFoundError,
    OroyaVideoError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
    RealESRGANUnsupportedModelError,
    TorchNotAvailableError,
    VideoAssetFileMissingError,
    VideoEncodingFailedError,
)
from app.core.logging import get_logger
from app.core.paths import (
    build_frame_file_name,
    ensure_job_encoded_directory,
    get_job_silent_video_path,
)
from app.db.database import commit_progress
from app.db.models import ProcessingJob
from app.db.repositories import job_repository
from app.enhancers.rife_interpolator import source_fps_fraction
from app.enhancers.stream import (
    Frame,
    FrameProcessor,
    ImageProcessor,
    InterpolationStage,
    PassthroughProcessor,
)
from app.services import job_workspace_service
from app.services.encoding_options import (
    EncodingChoice,
    build_video_codec_args,
    detect_hardware_encoders,
    hardware_fits,
    resolve_encoding,
)
from app.services.face_restore_service import build_face_restorer
from app.services.frame_extraction_service import (
    FRAME_FILE_PATTERN,
    FRAME_FORMAT,
    estimate_total_frames,
    resolve_job_input_video,
    time_to_datetime,
    validate_ffmpeg_available,
)
from app.services.interpolation_service import build_interpolation_stage
from app.services.pipeline_progress import (
    PROCESSING_PROGRESS_END,
    PROCESSING_PROGRESS_START,
    calculate_stage_progress,
)
from app.services.process_registry_service import (
    is_shutting_down,
    register_process,
    unregister_process,
)
from app.services.realesrgan_service import (
    LOW_DISK_PAUSE_BYTES,
    free_disk_bytes,
    get_spandrel_enhancer,
    get_streaming_enhancer,
    resolve_realesrgan_model_path,
)
from app.services.tool_detection_service import resolve_tool_path
from app.services.video_encoding_service import (
    ENCODED_VIDEO_FILE_NAME,
    ENCODING_FORMAT,
    EVEN_DIMENSIONS_FILTER,
    OUTPUT_RESOLUTION_FACTORS,
    build_enhancement_video_filters,
    build_output_scale_filter,
    build_post_ai_filters,
    build_pre_ai_filters,
    combine_video_filters,
    resolve_encoding_fps,
)
from app.utils.color import (
    OUTPUT_COLOR_ARGS,
    decode_color_filter,
    encode_color_filter,
    source_color_for_video,
)
from app.utils.enhancement_config import parse_enhancement_config_json
from app.utils.png import encode_png_rgb, read_png_size
from app.utils.process_output import StderrDrain, is_disk_full, stop_process_quietly
from app.utils.trim import get_job_trim

logger = get_logger(__name__)

STAGE = "processing"
SEGMENTS_DIR_NAME = "segments"
SEGMENT_NAME_PATTERN = re.compile(r"^seg_(\d{5})_(\d{8})_(\d{6})\.mp4$")
CONCAT_LIST_FILE_NAME = "segments.txt"
# Progreso y comprobaciones de pausar/cancelar como mucho cada este intervalo.
DB_SYNC_INTERVAL_SECONDS = 0.5
# La muestra "en vivo" se guarda como mucho cada este intervalo y sin pasar del ~10 % del
# tiempo de proceso (un PNG de 4K tarda en comprimirse).
LIVE_PREVIEW_INTERVAL_SECONDS = 2.0
LIVE_PREVIEW_MAX_OVERHEAD = 10
FRAME_QUEUE_SIZE = 4
# Los parámetros del codificador (encoding_options) son idénticos en todos los tramos para
# unirlos sin recodificar.

PROCESSOR_ERRORS = (
    AIModelFileNotFoundError,
    AIRuntimeNotAvailableError,
    CUDANotAvailableError,
    CUDAOutOfMemoryError,
    FaceRestoreFailedError,
    FaceRestoreNotAvailableError,
    FrameEnhancerNotFoundError,
    FrameInterpolationFailedError,
    FrameInterpolationNotAvailableError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
    RealESRGANUnsupportedModelError,
    TorchNotAvailableError,
)


def _get_active_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


# ---------------------------------------------------------------------------------------------
# Tramos


@dataclass(frozen=True, slots=True)
class Segment:
    index: int
    start_frame: int
    frame_count: int
    path: Path

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.frame_count


def segment_file_name(index: int, start_frame: int, frame_count: int) -> str:
    return f"seg_{index:05d}_{start_frame:08d}_{frame_count:06d}.mp4"


def list_completed_segments(segments_dir: Path) -> list[Segment]:
    """Finished segments in order, up to the first gap (anything after a gap is redone)."""
    if not segments_dir.is_dir():
        return []
    found: list[Segment] = []
    for item in segments_dir.iterdir():
        match = SEGMENT_NAME_PATTERN.match(item.name)
        if match and item.is_file() and item.stat().st_size > 0:
            index, start, count = (int(value) for value in match.groups())
            found.append(Segment(index, start, count, item))
    found.sort(key=lambda segment: segment.index)

    contiguous: list[Segment] = []
    for segment in found:
        expected_index = len(contiguous)
        expected_start = contiguous[-1].end_frame if contiguous else 0
        if segment.index != expected_index or segment.start_frame != expected_start:
            break
        contiguous.append(segment)
    return contiguous


def preview_sample_indexes(total_frames: int, samples: int) -> set[int]:
    """`samples` frame indexes spread over the whole video (first and last included)."""
    if total_frames <= 0 or samples <= 0:
        return set()
    if total_frames <= samples:
        return set(range(total_frames))
    step = (total_frames - 1) / (samples - 1) if samples > 1 else 0
    return {round(position * step) for position in range(samples)}


# ---------------------------------------------------------------------------------------------
# Comandos ffmpeg


def _fps_arg(fps: float | Fraction) -> str:
    if isinstance(fps, Fraction):
        return f"{fps.numerator}/{fps.denominator}"
    return f"{fps:.6f}".rstrip("0").rstrip(".")


def build_decoder_command(
    input_path: Path,
    fps: float | Fraction,
    start_seconds: float = 0.0,
    duration_seconds: float | None = None,
    *,
    probe: bool = False,
    video_filters: str | None = None,
) -> list[str]:
    """Decode to raw `rgb24` frames on stdout at a constant frame rate (audio stays in sync
    with VFR sources too). With `probe`, a single PNG frame to learn the decoded size."""
    output = (
        ["-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "pipe:1"]
        if probe
        else ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        *(["-ss", f"{start_seconds:.3f}"] if start_seconds > 0 else []),
        *(["-t", f"{duration_seconds:.3f}"] if duration_seconds is not None else []),
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-vf",
        ",".join(item for item in (f"fps={_fps_arg(fps)}", video_filters) if item),
        *output,
    ]


def build_segment_encoder_command(
    output_path: Path,
    width: int,
    height: int,
    fps: float | Fraction,
    video_filters: str | None = None,
    codec_args: list[str] | None = None,
) -> list[str]:
    if codec_args is None:
        codec_args = build_video_codec_args(EncodingChoice(), hardware_available=False).args
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-framerate",
        _fps_arg(fps),
        "-i",
        "pipe:0",
        *(["-vf", video_filters] if video_filters else []),
        *codec_args,
        *OUTPUT_COLOR_ARGS,
        "-f",
        "mp4",
        str(output_path),
    ]


def build_concat_command(list_file: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


# ---------------------------------------------------------------------------------------------
# Procesos


class _StreamError(Exception):
    def __init__(self, error: OroyaVideoError, message: str | None = None) -> None:
        super().__init__(message or error.message)
        self.error = error
        self.message = message or error.message


class FrameReader:
    """Read fixed-size raw frames from the decoder in a background thread.

    The main loop waits with a timeout, so it can check pause/cancel while the decoder is
    busy and detect a decoder that hangs.
    """

    _END = object()

    def __init__(self, stream, frame_size: int) -> None:
        self._stream = stream
        self._frame_size = frame_size
        self._frames: queue.Queue[object] = queue.Queue(maxsize=FRAME_QUEUE_SIZE)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="stream-decoder")
        self._thread.start()

    def _put(self, item: object) -> None:
        while not self._stopped.is_set():
            try:
                self._frames.put(item, timeout=0.5)
                return
            except queue.Full:
                continue

    def _run(self) -> None:
        try:
            while not self._stopped.is_set():
                data = self._stream.read(self._frame_size)
                if not data or len(data) < self._frame_size:
                    break
                self._put(data)
        except (OSError, ValueError):
            pass
        finally:
            self._put(self._END)

    def get(self, timeout: float) -> bytes | None:
        """Next frame, None at the end of the stream; raises `queue.Empty` on timeout."""
        item = self._frames.get(timeout=timeout)
        return None if item is self._END else item  # type: ignore[return-value]

    def stop(self) -> None:
        self._stopped.set()


class SegmentEncoder:
    """One ffmpeg libx264 process writing one segment from raw frames on stdin."""

    def __init__(
        self,
        ffmpeg_path: str,
        job_id: str,
        temp_path: Path,
        width: int,
        height: int,
        fps: float | Fraction,
        video_filters: str | None,
        codec_args: list[str] | None = None,
    ) -> None:
        self.job_id = job_id
        self.temp_path = temp_path
        self.frames = 0
        command = build_segment_encoder_command(
            self.temp_path, width, height, fps, video_filters, codec_args
        )
        command[0] = ffmpeg_path
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._stderr = StderrDrain(self.process.stderr)
        register_process(job_id, int(self.process.pid), "ffmpeg_encode", self.process)

    def write(self, data: bytes) -> None:
        try:
            self.process.stdin.write(data)  # type: ignore[union-attr]
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise self._failure() from exc
        self.frames += 1

    def _failure(self) -> _StreamError:
        stop_process_quietly(self.process)
        stderr = self._stderr.text()
        unregister_process(self.job_id, "ffmpeg_encode")
        self.temp_path.unlink(missing_ok=True)
        if is_disk_full(stderr):
            return _StreamError(InsufficientDiskSpaceError())
        return _StreamError(VideoEncodingFailedError(), stderr or None)

    def finish(self, final_path: Path, timeout_seconds: float) -> Path:
        """Close stdin, wait for ffmpeg and give the finished segment its final name."""
        try:
            self.process.stdin.close()  # type: ignore[union-attr]
            return_code = self.process.wait(timeout=timeout_seconds)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise self._failure() from exc
        if return_code != 0:
            raise self._failure()
        unregister_process(self.job_id, "ffmpeg_encode")
        os.replace(self.temp_path, final_path)
        return final_path

    def abort(self) -> None:
        stop_process_quietly(self.process)
        unregister_process(self.job_id, "ffmpeg_encode")
        self.temp_path.unlink(missing_ok=True)


def probe_decoded_size(
    ffmpeg_path: str, input_path: Path, fps: float | Fraction, start: float
) -> tuple[int, int] | None:
    """Size of the decoded frames (after rotation metadata), from one PNG frame; None when no
    frame is left from `start` (resuming a job whose segments are all done)."""
    command = build_decoder_command(input_path, fps, start, probe=True)
    command[0] = ffmpeg_path
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, check=False)
        if result.returncode != 0:
            raise _StreamError(
                FrameExtractionFailedError(),
                result.stderr.decode("utf-8", "replace").strip() or None,
            )
        return read_png_size(result.stdout) if result.stdout else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise _StreamError(FrameExtractionFailedError()) from exc


def _write_png(path: Path, frame: Frame) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_bytes(encode_png_rgb(frame.data, frame.width, frame.height))
    os.replace(temp_path, path)


# ---------------------------------------------------------------------------------------------
# Job


def build_frame_processor(
    db: Session,
    job: ProcessingJob,
    settings: Settings,
) -> tuple[FrameProcessor, int]:
    """Processor for the job's engine and the scale it applies (1 for the mock engine)."""
    engine = settings.frame_enhancer_engine.strip().lower()
    face_restorer = build_face_restorer(db, job, settings)
    if engine == "realesrgan":
        enhancer = get_streaming_enhancer(db, job, settings)
        ai_strength = parse_enhancement_config_json(job.enhancement_config_json).get(
            "ai_strength", 100
        )
        if isinstance(ai_strength, bool) or not isinstance(ai_strength, int):
            ai_strength = 100
        cleanup = build_ai_cleanup(db, job, settings)
        return (
            ImageProcessor(enhancer, face_restorer, ai_strength / 100, cleanup),
            enhancer.scale or 1,
        )
    if engine != "mock":
        raise FrameEnhancerNotFoundError()
    if face_restorer is not None:
        return ImageProcessor(None, face_restorer), 1
    return PassthroughProcessor(settings.mock_enhancer_frame_delay_ms / 1000), 1


AI_CLEANUP_MODEL_SLUG = "deh264-1x"


def build_ai_cleanup(db: Session, job: ProcessingJob, settings: Settings):
    """1x compression clean-up model before upscaling, when enabled for the job."""
    config = parse_enhancement_config_json(job.enhancement_config_json).get("ai_cleanup")
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return None
    model_path = resolve_realesrgan_model_path(db, AI_CLEANUP_MODEL_SLUG, settings)
    return get_spandrel_enhancer(model_path, AI_CLEANUP_MODEL_SLUG, 1, settings)


def _mark_failed(db: Session, job: ProcessingJob, code: str, message: str) -> None:
    db.rollback()
    db.refresh(job)
    if job.status == "cancelled":
        return
    now = time_to_datetime(time.time())
    job_repository.update_job(
        db,
        job,
        {
            "status": "failed",
            "current_stage": "failed",
            "error_code": code,
            "error_message": message,
            "enhancement_error_code": code,
            "enhancement_error_message": message,
            "process_id": None,
            "process_kind": None,
            "process_ended_at": now,
        },
    )
    job_repository.create_job_log(db, job.id, "error", f"Processing failed: {message}", stage=STAGE)
    db.commit()


def process_job_streaming(
    db: Session,
    job_id: str,
    settings: Settings | None = None,
) -> ProcessingJob:
    active_settings = _get_active_settings(settings)
    job = job_repository.get_job_by_id(db, job_id)
    if not job:
        raise JobNotFoundError()
    if job.cancel_requested or job.status == "cancelled":
        return job

    if job.encoding_completed_at and job.encoded_video_path:
        if Path(job.encoded_video_path).is_file():
            # Reintento tras fallar el audio o la exportación: el video ya está codificado.
            job_repository.update_job(db, job, {"status": "running"})
            job_repository.create_job_log(
                db, job.id, "info", "Reusing the video encoded earlier.", stage=STAGE
            )
            db.commit()
            return job

    try:
        ffmpeg_path = validate_ffmpeg_available()
        input_path = resolve_job_input_video(job)
        processor, processor_scale = build_frame_processor(db, job, active_settings)
        interpolation, output_fps = build_interpolation_stage(
            db, job, active_settings, resolve_encoding_fps(job)
        )
    except (FFmpegNotAvailableError, VideoAssetFileMissingError, *PROCESSOR_ERRORS) as exc:
        _mark_failed(db, job, exc.error_code, exc.message)
        raise

    run = _StreamingRun(db, job, active_settings, ffmpeg_path, input_path)
    try:
        return run.execute(processor, processor_scale, interpolation, output_fps)
    except _StreamError as exc:
        run.stop_processes()
        _mark_failed(db, job, exc.error.error_code, exc.message)
        logger.warning("Streaming pipeline failed for job %s: %s", job.id, exc.message)
        raise exc.error from exc
    except PROCESSOR_ERRORS as exc:
        run.stop_processes()
        _mark_failed(db, job, exc.error_code, exc.message)
        logger.exception("Frame processing failed for job %s", job.id)
        raise
    except Exception:
        run.stop_processes()
        raise


class _StreamingRun:
    def __init__(
        self,
        db: Session,
        job: ProcessingJob,
        settings: Settings,
        ffmpeg_path: str,
        input_path: Path,
    ) -> None:
        self.db = db
        self.job = job
        self.settings = settings
        self.ffmpeg_path = ffmpeg_path
        self.input_path = input_path
        self.decoder: subprocess.Popen | None = None
        self.decoder_stderr: StderrDrain | None = None
        self.reader: FrameReader | None = None
        self.encoder: SegmentEncoder | None = None

    # -- procesos ------------------------------------------------------------------------

    def stop_processes(self) -> None:
        if self.encoder is not None:
            self.encoder.abort()
            self.encoder = None
        self._stop_decoder()

    def _stop_decoder(self) -> None:
        if self.reader is not None:
            self.reader.stop()
        if self.decoder is not None:
            stop_process_quietly(self.decoder)
            unregister_process(self.job.id, "ffmpeg_decode")

    def _start_decoder(self, start_seconds: float, duration: float | None) -> None:
        command = build_decoder_command(
            self.input_path,
            self.fps_exact,
            start_seconds,
            duration,
            video_filters=self.decode_filters,
        )
        command[0] = self.ffmpeg_path
        self.decoder = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.decoder_stderr = StderrDrain(self.decoder.stderr)
        register_process(self.job.id, int(self.decoder.pid), "ffmpeg_decode", self.decoder)
        self.reader = FrameReader(self.decoder.stdout, self.width * self.height * 3)

    # -- ejecución -----------------------------------------------------------------------

    def execute(
        self,
        processor: FrameProcessor,
        processor_scale: int,
        interpolation: InterpolationStage | None = None,
        output_fps: Fraction | None = None,
    ) -> ProcessingJob:
        db, job, settings = self.db, self.job, self.settings
        workspace = job_workspace_service.prepare_job_workspace(job.id, settings)
        self.originals_dir = workspace["original_frames_dir"]
        self.enhanced_dir = workspace["enhanced_frames_dir"]
        encoded_dir = ensure_job_encoded_directory(job.id, settings)
        self.segments_dir = encoded_dir / SEGMENTS_DIR_NAME
        self.segments_dir.mkdir(parents=True, exist_ok=True)

        self.fps = resolve_encoding_fps(job)
        self.interpolation = interpolation
        # Fracción exacta (24000/1001…) para decodificar y codificar al mismo ritmo.
        self.fps_exact = source_fps_fraction(self.fps)
        self.output_fps: Fraction = output_fps or self.fps_exact
        self.encoder = None
        self.segment_done = 0
        self.segment_start = 0
        trim = get_job_trim(job)
        self.estimated_total = estimate_total_frames(job) or 0
        self.segment_frames = job.segment_frames or max(settings.streaming_segment_frames, 1)
        completed = list_completed_segments(self.segments_dir)
        self.segment_index = len(completed)
        self.start_frame = completed[-1].end_frame if completed else 0
        self.samples = preview_sample_indexes(
            self.estimated_total, settings.streaming_preview_samples
        )

        enhancement_config = parse_enhancement_config_json(job.enhancement_config_json)
        export_config = parse_enhancement_config_json(job.export_config_json)
        # Limpieza y ruido antes de la IA (decodificador); nitidez y escala, después.
        source_color = source_color_for_video(
            job.video_asset, self.input_path, resolve_tool_path("ffprobe")
        )
        self.decode_filters = combine_video_filters(
            build_pre_ai_filters(enhancement_config), decode_color_filter(source_color)
        )
        user_filters = combine_video_filters(
            build_enhancement_video_filters(enhancement_config),
            build_output_scale_filter(export_config, job.video_asset, processor_scale),
        )
        # Códec, calidad, GPU y 10 bits (REQ-040): iguales en todos los tramos.
        self.encoding = resolve_encoding(export_config)
        output_factor = OUTPUT_RESOLUTION_FACTORS.get(
            str(export_config.get("output_resolution", "")).lower(), 1
        )
        video = job.video_asset
        hardware = (
            self.encoding.hardware
            and hardware_fits(
                (getattr(video, "width", 0) or 0) * output_factor,
                (getattr(video, "height", 0) or 0) * output_factor,
            )
            and detect_hardware_encoders(self.ffmpeg_path).get(self.encoding.codec, False)
        )
        self.encoder_args = build_video_codec_args(self.encoding, hardware)
        if self.encoding.hardware and not hardware:
            job_repository.create_job_log(
                db,
                job.id,
                "warning",
                "GPU encoding is not available here; encoding on the CPU.",
                stage=STAGE,
            )
        self.video_filters = combine_video_filters(
            build_post_ai_filters(enhancement_config),
            build_output_scale_filter(export_config, job.video_asset, processor_scale),
            EVEN_DIMENSIONS_FILTER,
            encode_color_filter(self.encoder_args.pix_fmt),
        )

        trim_start = trim.start_seconds if trim else 0.0
        seek = trim_start + self.start_frame / self.fps
        remaining = (trim.end_seconds - seek) if trim else None
        now = time.time()
        job_repository.update_job(
            db,
            job,
            {
                "status": "running",
                "current_stage": STAGE,
                "pipeline_mode": "streaming",
                "segment_frames": self.segment_frames,
                "segments_completed": len(completed),
                "segments_total": math.ceil(self.estimated_total / self.segment_frames) or None,
                "frames_total": self.estimated_total or None,
                "frames_processed": self.start_frame,
                "enhanced_frames": self.start_frame,
                "progress_percent": self._progress(self.start_frame),
                "working_dir": str(workspace["working_dir"]),
                "original_frames_dir": str(self.originals_dir),
                "enhanced_frames_dir": str(self.enhanced_dir),
                "encoded_dir": str(encoded_dir),
                "frame_file_pattern": FRAME_FILE_PATTERN,
                "frame_format": FRAME_FORMAT,
                "enhancer_engine": processor.engine,
                "started_at": job.started_at or time_to_datetime(now),
                "extraction_started_at": job.extraction_started_at or time_to_datetime(now),
                "enhancement_started_at": job.enhancement_started_at or time_to_datetime(now),
                "encoding_started_at": job.encoding_started_at or time_to_datetime(now),
                "pause_requested": False,
                "error_code": None,
                "error_message": None,
                "enhancement_error_code": None,
                "enhancement_error_message": None,
                "process_kind": "ffmpeg_stream",
                "process_started_at": time_to_datetime(now),
                "process_ended_at": None,
                **self._ai_fields(processor),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            (
                f"Streaming pipeline resumed at frame {self.start_frame} "
                f"(segment {self.segment_index + 1})."
                if self.start_frame
                else f"Streaming pipeline started ({processor.engine}, {self.fps:g} fps)."
            ),
            stage=STAGE,
        )
        if interpolation is not None:
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                f"Frame interpolation (RIFE 4.25): {self.fps:g} → {float(self.output_fps):g} fps.",
                stage=STAGE,
            )
        if user_filters:
            job_repository.create_job_log(
                db, job.id, "info", f"Encoding filters: {user_filters}", stage=STAGE
            )
        db.commit()

        if interpolation is not None:
            interpolation.interpolator.load_model()
        if isinstance(processor, ImageProcessor):
            processor.load()
            job_repository.create_job_log(db, job.id, "info", "AI models loaded.", stage=STAGE)
            db.commit()

        outcome = "completed"
        size = (
            probe_decoded_size(self.ffmpeg_path, self.input_path, self.fps_exact, seek)
            if remaining is None or remaining > 0
            else None
        )
        if size is not None:
            self.width, self.height = size
            self._start_decoder(seek, remaining)
            outcome = self._loop(processor)

        db.refresh(job)
        if outcome == "cancelled" or job.cancel_requested or job.status == "cancelled":
            return self._finish_cancelled()
        if outcome == "shutdown":
            # Como la mejora clásica: queda en pausa y se reanuda desde el último tramo.
            logger.warning("Streaming pipeline paused by backend shutdown: %s", job.id)
        if outcome in {"paused", "low_disk", "shutdown"}:
            return self._finish_paused(low_disk=outcome == "low_disk")
        return self._concat_segments(processor)

    def _ai_fields(self, processor: FrameProcessor) -> dict[str, object]:
        enhancer = getattr(processor, "enhancer", None)
        if enhancer is None:
            return {}
        return {
            "realesrgan_model_slug": enhancer.model_slug,
            "realesrgan_model_path": str(enhancer.model_path),
            "realesrgan_device": enhancer.device,
            "realesrgan_scale": enhancer.scale,
            "realesrgan_tile_size": enhancer.tile_size,
            "realesrgan_half_precision": enhancer.half_precision,
            "realesrgan_frames_total": self.estimated_total or None,
            "realesrgan_started_at": self.job.realesrgan_started_at
            or time_to_datetime(time.time()),
        }

    def _progress(self, frames_done: int) -> float:
        return calculate_stage_progress(
            frames_done,
            self.estimated_total,
            start=PROCESSING_PROGRESS_START,
            end=PROCESSING_PROGRESS_END,
            clamp_to=PROCESSING_PROGRESS_END - 0.1,
        )

    def _loop(self, processor: FrameProcessor) -> str:
        db, job, settings = self.db, self.job, self.settings
        assert self.reader is not None
        frame_index = self.start_frame
        run_started = time.monotonic()
        processed_this_run = 0
        last_sync = 0.0
        last_output = time.monotonic()
        next_live_at = 0.0
        live_index: int | None = job.preview_frame_index
        stall_timeout = settings.ffmpeg_stall_timeout_seconds

        def sync(force: bool = False) -> None:
            nonlocal last_sync
            if not force and time.monotonic() - last_sync < DB_SYNC_INTERVAL_SECONDS:
                return
            average_ms = (
                round((time.monotonic() - run_started) * 1000 / processed_this_run)
                if processed_this_run
                else None
            )
            updates: dict[str, object] = {
                "frames_processed": frame_index,
                "enhanced_frames": frame_index,
                "extracted_frames": frame_index,
                "progress_percent": self._progress(frame_index),
                "elapsed_time_seconds": int(time.monotonic() - run_started),
                "realesrgan_average_frame_time_ms": average_ms,
                "segments_completed": self.segment_index,
                "preview_frame_index": live_index,
            }
            if getattr(processor, "enhancer", None) is not None:
                updates["realesrgan_frames_processed"] = frame_index
                updates["realesrgan_failed_frames"] = processor.failed_frames
            job_repository.update_job(db, job, updates)
            # Guardar el progreso antes de recargar el job (refresh lo descartaría).
            commit_progress(db)
            db.refresh(job)
            last_sync = time.monotonic()

        def stop_requested() -> str | None:
            if is_shutting_down():
                return "shutdown"
            if job.cancel_requested or job.status == "cancelled":
                return "cancelled"
            if job.pause_requested:
                return "paused"
            return None

        def stop_reason_after_failure() -> str | None:
            # Cancelar o apagar terminan los ffmpeg: ese fallo no es un error del job.
            db.rollback()
            db.refresh(job)
            return stop_requested()

        while True:
            sync()
            if (reason := stop_requested()) is not None:
                return self._interrupt(reason)
            try:
                data = self.reader.get(timeout=1.0)
            except queue.Empty:
                if time.monotonic() - last_output >= stall_timeout:
                    raise _StreamError(FFmpegStalledError()) from None
                continue
            last_output = time.monotonic()
            if data is None:
                break

            original = Frame(data, self.width, self.height)
            processed = processor.process(original)
            try:
                self._emit(*self._outputs(frame_index, processed))
            except _StreamError:
                if (reason := stop_reason_after_failure()) is not None:
                    return self._interrupt(reason)
                raise

            if frame_index in self.samples:
                self._save_pair(frame_index, original, processed)
            if time.monotonic() >= next_live_at:
                started = time.monotonic()
                if frame_index not in self.samples:
                    self._save_pair(frame_index, original, processed)
                if live_index is not None and live_index not in self.samples:
                    self._delete_pair(live_index)
                live_index = frame_index
                spent = time.monotonic() - started
                next_live_at = time.monotonic() + max(
                    LIVE_PREVIEW_INTERVAL_SECONDS, spent * LIVE_PREVIEW_MAX_OVERHEAD
                )

            frame_index += 1
            processed_this_run += 1
            if self.segment_done >= self.segment_frames:
                try:
                    self._close_segment()
                except _StreamError:
                    if (reason := stop_reason_after_failure()) is not None:
                        return self._interrupt(reason)
                    raise
                sync(force=True)
                if free_disk_bytes(self.segments_dir) < LOW_DISK_PAUSE_BYTES:
                    return self._interrupt("low_disk")

        # Fin del decodificador; también ocurre cuando cancelar o apagar lo terminó.
        sync(force=True)
        if (reason := stop_requested()) is not None:
            return self._interrupt(reason)
        if self.interpolation is not None:
            # El último fotograma no tiene siguiente: sus fotogramas de salida lo repiten.
            self._emit(*self.interpolation.flush())
        if self.encoder is not None:
            self._close_segment()
        self._check_decoder_exit()
        # Al terminar solo quedan los pares de muestra (la limpieza conserva N fotogramas).
        if live_index is not None and live_index not in self.samples:
            self._delete_pair(live_index)
            live_index = max(self.samples, default=None)
        sync(force=True)
        return "completed"

    def _outputs(self, frame_index: int, processed: Frame) -> tuple[int | None, list[Frame]]:
        """(source frame completed now, output frames to encode)."""
        if self.interpolation is None:
            return frame_index, [processed]
        return self.interpolation.push(frame_index, processed)

    def _emit(self, completed: int | None, frames: list[Frame]) -> None:
        if completed is None:
            return
        for frame in frames:
            if self.encoder is None:
                self.encoder = SegmentEncoder(
                    self.ffmpeg_path,
                    self.job.id,
                    self.segments_dir / f"seg_{self.segment_index:05d}.part.mp4",
                    frame.width,
                    frame.height,
                    self.output_fps,
                    self.video_filters,
                    self.encoder_args.args,
                )
            self.encoder.write(frame.data)
        # Un tramo cuenta fotogramas de origen completos: reanudar empieza en el siguiente.
        if self.segment_done == 0:
            self.segment_start = completed
        self.segment_done += 1

    def _close_segment(self) -> None:
        assert self.encoder is not None
        encoder, self.encoder = self.encoder, None
        final_path = self.segments_dir / segment_file_name(
            self.segment_index, self.segment_start, self.segment_done
        )
        self.segment_done = 0
        encoder.finish(final_path, self.settings.ffmpeg_stall_timeout_seconds)
        self.segment_index += 1

    def _interrupt(self, reason: str) -> str:
        """Stop decoding. Pause and shutdown keep the segment in progress; cancel drops it.

        A frame waiting for its successor (interpolation) is decoded again on resume.
        """
        self._stop_decoder()
        if self.encoder is not None:
            if reason == "cancelled" or self.segment_done == 0:
                self.encoder.abort()
                self.encoder = None
                self.segment_done = 0
            else:
                try:
                    self._close_segment()
                except _StreamError:
                    # Al apagar, el codificador puede haber sido terminado ya: se rehace el tramo.
                    self.encoder = None
                    self.segment_done = 0
        return reason

    def _check_decoder_exit(self) -> None:
        assert self.decoder is not None
        try:
            return_code = self.decoder.wait(timeout=30)
        except subprocess.TimeoutExpired:
            stop_process_quietly(self.decoder)
            return_code = -1
        unregister_process(self.job.id, "ffmpeg_decode")
        stderr = self.decoder_stderr.text() if self.decoder_stderr else ""
        if return_code != 0 and not is_shutting_down():
            if is_disk_full(stderr):
                raise _StreamError(InsufficientDiskSpaceError())
            raise _StreamError(FrameExtractionFailedError(), stderr or None)

    def _save_pair(self, frame_index: int, original: Frame, processed: Frame) -> None:
        name = build_frame_file_name(frame_index)
        try:
            _write_png(self.originals_dir / name, original)
            _write_png(self.enhanced_dir / name, processed)
        except OSError:
            # La vista previa nunca debe parar el proceso.
            logger.warning("Preview sample %s could not be saved", frame_index, exc_info=True)

    def _delete_pair(self, frame_index: int) -> None:
        """Drop a live-preview pair (and its filtered variants). Best effort: on Windows the
        file can be open by the preview right now (WinError 32); it must never stop the job."""
        name = build_frame_file_name(frame_index)
        filtered_dir = self.enhanced_dir.parent / "filtered"
        paths = [
            self.originals_dir / name,
            self.enhanced_dir / name,
            *filtered_dir.glob(f"{Path(name).stem}_*.png"),
        ]
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Preview frame %s still in use; left in place", path)

    # -- desenlaces ----------------------------------------------------------------------

    def _finish_cancelled(self) -> ProcessingJob:
        db, job = self.db, self.job
        now = time_to_datetime(time.time())
        job_repository.update_job(
            db,
            job,
            {
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancelled_at": job.cancelled_at or now,
                "process_id": None,
                "process_kind": None,
                "process_ended_at": now,
            },
        )
        job_repository.create_job_log(
            db, job.id, "warning", "Processing cancelled by user.", stage="cancelled"
        )
        db.commit()
        return job

    def _finish_paused(self, *, low_disk: bool) -> ProcessingJob:
        db, job = self.db, self.job
        disk_error = InsufficientDiskSpaceError() if low_disk else None
        job_repository.update_job(
            db,
            job,
            {
                "status": "paused",
                "current_stage": STAGE,
                "segments_completed": self.segment_index,
                "error_code": disk_error.error_code if disk_error else None,
                "error_message": disk_error.message if disk_error else None,
                "process_id": None,
                "process_kind": None,
                "process_ended_at": time_to_datetime(time.time()),
            },
        )
        job_repository.create_job_log(
            db,
            job.id,
            "warning" if low_disk else "info",
            "Processing paused: the disk is almost full."
            if low_disk
            else f"Processing paused after {self.segment_index} segments.",
            stage=STAGE,
        )
        db.commit()
        return job

    def _concat_segments(self, processor: FrameProcessor) -> ProcessingJob:
        db, job, settings = self.db, self.job, self.settings
        segments = list_completed_segments(self.segments_dir)
        if not segments:
            raise _StreamError(FrameExtractionFailedError(), "The video has no frames to process.")
        list_file = self.segments_dir / CONCAT_LIST_FILE_NAME
        list_file.write_text(
            "".join(f"file '{segment.path.name}'\n" for segment in segments), encoding="utf-8"
        )
        output_path = get_job_silent_video_path(job.id, settings)
        command = build_concat_command(list_file, output_path)
        command[0] = self.ffmpeg_path
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        register_process(job.id, int(process.pid), "ffmpeg_concat", process)
        try:
            _, stderr_bytes = process.communicate(timeout=settings.ffmpeg_stall_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            stop_process_quietly(process)
            unregister_process(job.id, "ffmpeg_concat")
            raise _StreamError(FFmpegStalledError()) from exc
        unregister_process(job.id, "ffmpeg_concat")
        stderr = stderr_bytes.decode("utf-8", "replace").strip()
        db.refresh(job)
        if job.cancel_requested or job.status == "cancelled":
            return self._finish_cancelled()
        if process.returncode != 0:
            if is_shutting_down():
                return job
            if is_disk_full(stderr):
                raise _StreamError(InsufficientDiskSpaceError())
            raise _StreamError(VideoEncodingFailedError(), stderr or None)

        total = segments[-1].end_frame
        output_size = output_path.stat().st_size
        now = time_to_datetime(time.time())
        updates: dict[str, object] = {
            "status": "running",
            "current_stage": STAGE,
            "frames_total": total,
            "frames_processed": total,
            "enhanced_frames": total,
            "extracted_frames": total,
            "segments_completed": len(segments),
            "segments_total": len(segments),
            "progress_percent": PROCESSING_PROGRESS_END,
            "extraction_completed_at": now,
            "enhancement_completed_at": now,
            "encoding_completed_at": now,
            "encoded_video_path": str(output_path),
            "encoded_video_file_name": ENCODED_VIDEO_FILE_NAME,
            "encoded_video_size_bytes": output_size,
            "encoded_size_bytes": output_size,
            "encoding_fps": float(self.output_fps),
            "encoding_codec": self.encoding.codec,
            "encoding_format": ENCODING_FORMAT,
            "process_id": None,
            "process_kind": None,
            "process_ended_at": now,
        }
        if getattr(processor, "enhancer", None) is not None:
            updates.update(
                {
                    "realesrgan_frames_total": total,
                    "realesrgan_frames_processed": total,
                    "realesrgan_failed_frames": processor.failed_frames,
                    "realesrgan_completed_at": now,
                }
            )
        job_repository.update_job(db, job, updates)
        job_repository.create_job_log(
            db,
            job.id,
            "info",
            f"Streaming pipeline completed: {total} frames in {len(segments)} segments.",
            stage=STAGE,
        )
        if self.interpolation is not None and self.interpolation.scene_changes:
            job_repository.create_job_log(
                db,
                job.id,
                "info",
                f"{self.interpolation.scene_changes} scene changes kept without interpolation.",
                stage=STAGE,
            )
        if processor.failed_frames:
            job_repository.create_job_log(
                db,
                job.id,
                "warning",
                f"{processor.failed_frames} frames could not be enhanced and were upscaled "
                "without AI.",
                stage=STAGE,
            )
        db.commit()
        logger.info("Streaming pipeline completed: %s", job.id)
        return job
