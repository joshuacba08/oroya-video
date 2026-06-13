from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any

from app.core.errors import (
    CUDAOutOfMemoryError,
    OriginalFramesNotFoundError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
    RealESRGANUnsupportedModelError,
)
from app.enhancers.base import CancelCallback, FrameEnhancer, ProgressCallback
from app.services.ai_runtime_service import clear_cuda_cache_if_available
from app.utils.performance_utils import calculate_average_ms


class RealESRGANFrameEnhancer(FrameEnhancer):
    name = "Real-ESRGAN Frame Enhancer"
    engine = "realesrgan"

    def __init__(
        self,
        *,
        model_path: Path,
        model_slug: str,
        device: str,
        scale: int | None,
        tile_size: int,
        tile_pad: int,
        pre_pad: int,
        half_precision: bool,
        max_failed_frames: int = 0,
        clear_cuda_cache: bool = True,
    ) -> None:
        self.model_path = model_path
        self.model_slug = model_slug
        self.device = device
        self.scale = scale
        self.tile_size = tile_size
        self.tile_pad = tile_pad
        self.pre_pad = pre_pad
        self.half_precision = half_precision
        self.max_failed_frames = max_failed_frames
        self.clear_cuda_cache = clear_cuda_cache
        self.processed_frames = 0
        self.completed_frames = 0
        self.failed_frames = 0
        self.total_frame_time_ms = 0.0
        self.average_frame_time_ms: int | None = None
        self.model_load_time_ms: int | None = None
        self._upsampler: Any | None = None
        self._cv2: Any | None = None
        self._default_outscale = scale or 4

    def enhance_frames(
        self,
        input_dir: Path,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> int:
        frame_files = sorted(frame for frame in input_dir.glob("*.png") if frame.is_file())
        if not frame_files:
            raise OriginalFramesNotFoundError()

        output_dir.mkdir(parents=True, exist_ok=True)
        self.load_model()
        total = len(frame_files)

        for frame in frame_files:
            if cancel_callback and cancel_callback():
                break

            output_path = output_dir / frame.name
            try:
                _, elapsed_time_ms = self.enhance_single_frame(frame, output_path)
            except CUDAOutOfMemoryError:
                if self.clear_cuda_cache:
                    clear_cuda_cache_if_available()
                raise
            except RealESRGANFrameProcessingFailedError:
                self.failed_frames += 1
                self.completed_frames += 1
                if progress_callback:
                    progress_callback(self.completed_frames, total)
                if self.failed_frames > self.max_failed_frames:
                    raise
                continue

            self.processed_frames += 1
            self.completed_frames += 1
            self.total_frame_time_ms += elapsed_time_ms
            self.average_frame_time_ms = calculate_average_ms(
                self.total_frame_time_ms,
                self.processed_frames,
            )
            if progress_callback:
                progress_callback(self.completed_frames, total)
            if self.clear_cuda_cache and self.device == "cuda":
                clear_cuda_cache_if_available()

        return self.processed_frames

    def load_model(self) -> None:
        if self._upsampler is not None:
            return

        started_at = time.perf_counter()
        try:
            self._upsampler, self._cv2, self._default_outscale = self._create_backend()
        except (
            RealESRGANNotAvailableError,
            RealESRGANUnsupportedModelError,
            CUDAOutOfMemoryError,
        ):
            raise
        except Exception as exc:  # pragma: no cover - defensive runtime wrapper
            raise RealESRGANModelLoadFailedError() from exc

        self.model_load_time_ms = round((time.perf_counter() - started_at) * 1000)

    def enhance_single_frame(
        self,
        input_path: Path,
        output_path: Path,
    ) -> tuple[Path, int]:
        self.load_model()
        if self._upsampler is None or self._cv2 is None:
            raise RealESRGANModelLoadFailedError()

        image = self._cv2.imread(str(input_path), self._cv2.IMREAD_UNCHANGED)
        if image is None:
            raise RealESRGANFrameProcessingFailedError()

        started_at = time.perf_counter()
        try:
            result, _ = self._upsampler.enhance(
                image,
                outscale=self.scale or self._default_outscale,
            )
        except RuntimeError as exc:
            message = str(exc).lower()
            if "out of memory" in message:
                raise CUDAOutOfMemoryError() from exc
            raise RealESRGANFrameProcessingFailedError() from exc
        except Exception as exc:  # pragma: no cover - defensive runtime wrapper
            raise RealESRGANFrameProcessingFailedError() from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._cv2.imwrite(str(output_path), result):
            raise RealESRGANFrameProcessingFailedError()

        elapsed_time_ms = round((time.perf_counter() - started_at) * 1000)
        return output_path, elapsed_time_ms

    def _create_backend(self) -> tuple[Any, Any, int]:
        if not self.model_path.exists() or not self.model_path.is_file():
            raise RealESRGANModelLoadFailedError()

        try:
            import cv2
            from basicsr.archs.rrdbnet_arch import RRDBNet
            from realesrgan import RealESRGANer
            from realesrgan.archs.srvgg_arch import SRVGGNetCompact
        except ImportError as exc:  # pragma: no cover - depends on optional packages
            raise RealESRGANNotAvailableError() from exc

        if self.model_slug == "realesrgan-x2":
            model = RRDBNet(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_block=23,
                num_grow_ch=32,
                scale=2,
            )
            netscale = 2
        elif self.model_slug == "realesrgan-x4":
            model = RRDBNet(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_block=23,
                num_grow_ch=32,
                scale=4,
            )
            netscale = 4
        elif self.model_slug == "realesrgan-general":
            model = SRVGGNetCompact(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_conv=32,
                upscale=4,
                act_type="prelu",
            )
            netscale = 4
        else:
            raise RealESRGANUnsupportedModelError()

        init_kwargs: dict[str, Any] = {
            "scale": netscale,
            "model_path": str(self.model_path),
            "model": model,
            "tile": self.tile_size,
            "tile_pad": self.tile_pad,
            "pre_pad": self.pre_pad,
            "half": self.half_precision and self.device == "cuda",
        }
        signature = inspect.signature(RealESRGANer.__init__)
        if "device" in signature.parameters:
            init_kwargs["device"] = self.device
        elif "gpu_id" in signature.parameters:
            init_kwargs["gpu_id"] = 0 if self.device == "cuda" else None

        try:
            upsampler = RealESRGANer(**init_kwargs)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise CUDAOutOfMemoryError() from exc
            raise RealESRGANModelLoadFailedError() from exc
        except Exception as exc:
            raise RealESRGANModelLoadFailedError() from exc

        return upsampler, cv2, netscale
