"""Modern super-resolution and restoration models through spandrel (REQ-039).

spandrel (MIT) loads many architectures (RealPLKSR, SPAN, DAT, HAT…) from a .pth/.safetensors
file and detects the architecture and scale itself. Same in-memory interface as
`RealESRGANFrameEnhancer.enhance_image`: a BGR uint8 image in, a BGR uint8 image out.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.core.errors import (
    CUDAOutOfMemoryError,
    RealESRGANFrameProcessingFailedError,
    RealESRGANModelLoadFailedError,
    RealESRGANNotAvailableError,
)
from app.enhancers.realesrgan_enhancer import CUDA_CACHE_CLEAR_INTERVAL, OOM_TILE_LADDER
from app.services.ai_runtime_service import clear_cuda_cache_if_available
from app.utils.performance_utils import calculate_average_ms

# Solape entre tiles: suficiente para el campo receptivo de estas redes y sin costuras.
TILE_OVERLAP = 32


class SpandrelFrameEnhancer:
    engine = "spandrel"

    def __init__(
        self,
        *,
        model_path: Path,
        model_slug: str,
        device: str,
        scale: int | None,
        half_precision: bool,
        tile_size: int = 0,
        max_failed_frames: int = 0,
        clear_cuda_cache: bool = True,
    ) -> None:
        self.model_path = model_path
        self.model_slug = model_slug
        self.device = device
        # Escala pedida; si difiere de la del modelo, se reescala con Lanczos al final.
        self.scale = scale
        self.half_precision = half_precision
        self.tile_size = tile_size
        self.max_failed_frames = max_failed_frames
        self.clear_cuda_cache = clear_cuda_cache
        self.native_scale: int | None = None
        self.model_load_time_ms: int | None = None
        self.tile_fallbacks = 0
        self._model: Any | None = None
        self._torch: Any | None = None
        self._cv2: Any | None = None
        self._dtype: Any | None = None
        self.reset_counters()

    def reset_counters(self) -> None:
        self.processed_frames = 0
        self.completed_frames = 0
        self.failed_frames = 0
        self.timed_frames = 0
        self.total_frame_time_ms = 0.0
        self.average_frame_time_ms: int | None = None
        self.tile_fallbacks = 0

    def load_model(self) -> None:
        if self._model is not None:
            return
        started_at = time.perf_counter()
        try:
            import cv2
            import spandrel
            import torch
        except ImportError as exc:
            raise RealESRGANNotAvailableError() from exc
        if not self.model_path.is_file():
            raise RealESRGANModelLoadFailedError()
        try:
            descriptor = spandrel.ModelLoader(device="cpu").load_from_file(str(self.model_path))
        except Exception as exc:  # noqa: BLE001 - archivo dañado o arquitectura no soportada
            raise RealESRGANModelLoadFailedError() from exc
        if not isinstance(descriptor, spandrel.ImageModelDescriptor):
            raise RealESRGANModelLoadFailedError()

        # fp16 solo si el modelo lo admite; si no, fp32. Nunca bf16: con RealPLKSR "dysample" la
        # salida sale pixelada (desplazamientos de muestreo poco precisos) y además fue más
        # lento que fp32 en una RTX 5060 Ti.
        dtype = torch.float32
        if self.device == "cuda" and self.half_precision and descriptor.supports_half:
            dtype = torch.float16
        try:
            descriptor.to(torch.device(self.device)).eval()
            descriptor.model.to(dtype)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise CUDAOutOfMemoryError() from exc
            raise RealESRGANModelLoadFailedError() from exc
        if self.device == "cuda":
            torch.backends.cudnn.benchmark = True
        self._model = descriptor
        self._torch = torch
        self._cv2 = cv2
        self._dtype = dtype
        self.native_scale = descriptor.scale
        self.model_load_time_ms = round((time.perf_counter() - started_at) * 1000)

    # -- inferencia ----------------------------------------------------------------------

    def _to_tensor(self, image: Any) -> Any:
        torch = self._torch
        rgb = image[:, :, ::-1].copy()
        tensor = torch.from_numpy(rgb).to(self.device).permute(2, 0, 1).unsqueeze(0)
        return tensor.to(self._dtype) / 255.0

    def _from_tensor(self, tensor: Any) -> Any:
        torch = self._torch
        output = tensor.squeeze(0).permute(1, 2, 0).float().clamp(0, 1)
        rgb = (output * 255.0).round().to(torch.uint8).cpu().numpy()
        return rgb[:, :, ::-1].copy()

    def _infer(self, tensor: Any) -> Any:
        if not self.tile_size:
            return self._model(tensor)
        return self._infer_tiled(tensor, self.tile_size)

    def _infer_tiled(self, tensor: Any, tile: int) -> Any:
        _, channels, height, width = tensor.shape
        scale = self.native_scale or 1
        output = tensor.new_zeros((1, channels, height * scale, width * scale))
        for top in range(0, height, tile):
            for left in range(0, width, tile):
                bottom, right = min(top + tile, height), min(left + tile, width)
                pad_top, pad_left = max(top - TILE_OVERLAP, 0), max(left - TILE_OVERLAP, 0)
                pad_bottom = min(bottom + TILE_OVERLAP, height)
                pad_right = min(right + TILE_OVERLAP, width)
                result = self._model(tensor[:, :, pad_top:pad_bottom, pad_left:pad_right])
                y0, x0 = (top - pad_top) * scale, (left - pad_left) * scale
                output[:, :, top * scale : bottom * scale, left * scale : right * scale] = result[
                    :, :, y0 : y0 + (bottom - top) * scale, x0 : x0 + (right - left) * scale
                ]
        return output

    def _reduce_memory_footprint(self) -> bool:
        if self.device != "cuda":
            return False
        smaller = [tile for tile in OOM_TILE_LADDER if not self.tile_size or tile < self.tile_size]
        if not smaller:
            return False
        self.tile_size = smaller[0]
        self.tile_fallbacks += 1
        return True

    def resize_to_output(self, image: Any, source: Any | None = None) -> Any:
        """Lanczos to the requested scale (from the source size when given)."""
        reference = source if source is not None else image
        scale = self.scale or self.native_scale or 1
        height, width = reference.shape[:2]
        size = (int(width * scale), int(height * scale))
        if image.shape[1] == size[0] and image.shape[0] == size[1]:
            return image
        shrinking = image.shape[1] > size[0]
        interpolation = self._cv2.INTER_AREA if shrinking else self._cv2.INTER_LANCZOS4
        return self._cv2.resize(image, size, interpolation=interpolation)

    def enhance_image(self, image: Any) -> Any:
        self.load_model()
        torch = self._torch
        while True:
            started_at = time.perf_counter()
            try:
                with torch.inference_mode():
                    result = self._from_tensor(self._infer(self._to_tensor(image)))
                break
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    clear_cuda_cache_if_available()
                    if self._reduce_memory_footprint():
                        continue
                    raise CUDAOutOfMemoryError() from exc
                self.failed_frames += 1
                self.completed_frames += 1
                if self.failed_frames > self.max_failed_frames:
                    raise RealESRGANFrameProcessingFailedError() from exc
                return self.resize_to_output(image)

        result = self.resize_to_output(result, source=image)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        self.processed_frames += 1
        self.completed_frames += 1
        self.timed_frames += 1
        self.total_frame_time_ms += elapsed_ms
        self.average_frame_time_ms = calculate_average_ms(
            self.total_frame_time_ms, self.timed_frames
        )
        if (
            self.clear_cuda_cache
            and self.device == "cuda"
            and self.processed_frames % CUDA_CACHE_CLEAR_INTERVAL == 0
        ):
            clear_cuda_cache_if_available()
        return result
