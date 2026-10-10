"""Optional face restoration with GFPGAN, applied to already upscaled frames."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.errors import (
    CUDAOutOfMemoryError,
    FaceRestoreFailedError,
    FaceRestoreNotAvailableError,
)
from app.services.ai_runtime_service import (
    clear_cuda_cache_if_available,
    ensure_torchvision_compat,
)
from app.utils.performance_utils import calculate_average_ms

ProgressCallback = Callable[[int, int], None]
StopCallback = Callable[[], bool]


class GFPGANFaceRestorer:
    """Restores faces in `input_dir` frames and writes them to `output_dir`.

    Frames without faces are copied unchanged. Upscale is 1: the frames were already
    upscaled by Real-ESRGAN, so output size equals input size.
    """

    def __init__(
        self,
        *,
        model_path: Path,
        weights_dir: Path,
        device: str,
        strength: float,
    ) -> None:
        self.model_path = model_path
        self.weights_dir = weights_dir
        self.device = device
        self.strength = strength
        self.processed_frames = 0
        self.faces_restored = 0
        self.timed_frames = 0
        self.total_frame_time_ms = 0.0
        self.average_frame_time_ms: int | None = None
        self._restorer: Any | None = None
        self._cv2: Any | None = None

    def load_model(self) -> None:
        if self._restorer is not None:
            return
        if not self.model_path.is_file():
            raise FaceRestoreNotAvailableError()

        ensure_torchvision_compat()
        try:
            import cv2
            import gfpgan.utils as gfpgan_utils
            import torch
        except ImportError as exc:
            raise FaceRestoreNotAvailableError() from exc

        # GFPGANer fija model_rootpath='gfpgan/weights' (relativo al cwd) y facexlib descarga
        # ahí los pesos de detección si faltan. Se redirige a la carpeta de modelos de la app,
        # donde la descarga del modelo ya los dejó: así funciona sin conexión.
        original_helper = gfpgan_utils.FaceRestoreHelper
        weights_dir = str(self.weights_dir)

        def helper_with_local_weights(*args: Any, **kwargs: Any) -> Any:
            return original_helper(*args, **{**kwargs, "model_rootpath": weights_dir})

        gfpgan_utils.FaceRestoreHelper = helper_with_local_weights
        try:
            self._restorer = gfpgan_utils.GFPGANer(
                model_path=str(self.model_path),
                upscale=1,
                arch="clean",
                channel_multiplier=2,
                bg_upsampler=None,
                device=torch.device(self.device),
            )
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise CUDAOutOfMemoryError() from exc
            raise FaceRestoreFailedError() from exc
        finally:
            gfpgan_utils.FaceRestoreHelper = original_helper
        self._cv2 = cv2

    def restore_frames(
        self,
        input_dir: Path,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        stop_callback: StopCallback | None = None,
    ) -> int:
        frames = sorted(frame for frame in input_dir.glob("*.png") if frame.is_file())
        output_dir.mkdir(parents=True, exist_ok=True)
        self.load_model()
        total = len(frames)

        for index, frame in enumerate(frames, start=1):
            if stop_callback and stop_callback():
                break
            output_path = output_dir / frame.name
            # Reanudación: los frames ya escritos (no vacíos) no se repiten.
            if not (output_path.is_file() and output_path.stat().st_size > 0):
                self._restore_frame(frame, output_path)
            self.processed_frames = index
            if progress_callback:
                progress_callback(index, total)
        return self.processed_frames

    def _restore_frame(self, input_path: Path, output_path: Path) -> None:
        assert self._restorer is not None and self._cv2 is not None
        image = self._cv2.imread(str(input_path), self._cv2.IMREAD_COLOR)
        if image is None:
            raise FaceRestoreFailedError()

        started_at = time.perf_counter()
        try:
            _, restored_faces, restored = self._restorer.enhance(
                image,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
                weight=self.strength,
            )
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                clear_cuda_cache_if_available()
                raise CUDAOutOfMemoryError() from exc
            raise FaceRestoreFailedError() from exc
        self.faces_restored += len(restored_faces)
        result = image if restored is None else restored

        ok, encoded = self._cv2.imencode(output_path.suffix, result)
        if not ok:
            raise FaceRestoreFailedError()
        temp_path = output_path.with_name(f"{output_path.name}.tmp")
        try:
            temp_path.write_bytes(encoded.tobytes())
            os.replace(temp_path, output_path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise FaceRestoreFailedError() from exc

        self.total_frame_time_ms += (time.perf_counter() - started_at) * 1000
        self.timed_frames += 1
        self.average_frame_time_ms = calculate_average_ms(
            self.total_frame_time_ms, self.timed_frames
        )
