"""Frame interpolation with RIFE 4.25 for the streaming pipeline (REQ-037).

`InterpolationSchedule` decides which output frames fall between two source frames and at
which timestep (pure arithmetic, testable without torch). `RIFEInterpolator` synthesises the
in-between frames. `InterpolationStage` (in `stream.py`) glues both to the frame stream.
"""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.core.errors import (
    CUDAOutOfMemoryError,
    FrameInterpolationFailedError,
    FrameInterpolationNotAvailableError,
)
from app.enhancers.stream import Frame

# Cambio de escena: diferencia media (0-1) entre dos fotogramas en gris y en pequeño. Por
# encima, interpolar mezclaría dos planos distintos: se repite el anterior.
SCENE_CHANGE_THRESHOLD = 0.15
SCENE_SAMPLE_WIDTH = 64
# La red trabaja con dimensiones múltiplo de 64 (de 128 con scale=0.5).
PAD_MODULO = 64
# A partir de 4K el flujo óptico se estima a media resolución (más rápido, menos VRAM).
HALF_SCALE_MIN_SIDE = 3840
ALLOWED_TARGET_FPS = ("2x", 48, 50, 60)


# Ritmos NTSC: el probe guarda los fps redondeados (23.976), pero son n·1000/1001.
NTSC_BASES = (24, 30, 48, 60, 120)


def source_fps_fraction(fps: float) -> Fraction:
    """Exact frame rate: 23.976 → 24000/1001, 29.97 → 30000/1001, 25.0 → 25."""
    for base in NTSC_BASES:
        if abs(fps - base * 1000 / 1001) < 0.005:
            return Fraction(base * 1000, 1001)
    return Fraction(fps).limit_denominator(1001)


def resolve_output_fps(source_fps: float, target: object) -> Fraction:
    source = source_fps_fraction(source_fps)
    if target == "2x":
        return source * 2
    return Fraction(int(target))  # type: ignore[call-overload]


class InterpolationSchedule:
    """Output frames between source frames i and i+1 for a source → output frame rate.

    Output frame n sits at source position n·fps_in/fps_out; those in [i, i+1) belong to
    interval i, with timestep = position − i (0 = source frame i itself).
    """

    def __init__(self, source_fps: Fraction, output_fps: Fraction) -> None:
        if output_fps <= source_fps:
            raise ValueError("The output frame rate must be higher than the source one.")
        ratio = output_fps / source_fps
        self.num = ratio.numerator
        self.den = ratio.denominator

    def timesteps(self, source_index: int) -> list[float]:
        first = math.ceil(source_index * self.num / self.den)
        end = math.ceil((source_index + 1) * self.num / self.den)
        return [(n * self.den - source_index * self.num) / self.num for n in range(first, end)]

    def total_outputs(self, source_frames: int) -> int:
        return math.ceil(source_frames * self.num / self.den)


def is_scene_change(first: Frame, second: Frame, threshold: float = SCENE_CHANGE_THRESHOLD) -> bool:
    import numpy as np

    if (first.width, first.height) != (second.width, second.height):
        return True
    step = max(first.width // SCENE_SAMPLE_WIDTH, 1)

    def gray(frame: Frame) -> Any:
        pixels = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)
        return pixels[::step, ::step].mean(axis=2)

    return float(np.abs(gray(first) - gray(second)).mean()) / 255.0 > threshold


class RIFEInterpolator:
    engine = "rife"

    def __init__(self, *, model_path: Path, device: str, half_precision: bool) -> None:
        self.model_path = model_path
        self.device = device
        self.half_precision = half_precision and device == "cuda"
        self._torch: Any | None = None
        self._flownet: Any | None = None
        self._encode: Any | None = None
        self._dtype: Any | None = None
        self._size: tuple[int, int] | None = None
        self._cached: tuple[Frame, Any, Any] | None = None

    def load_model(self) -> None:
        if self._flownet is not None:
            return
        if not self.model_path.is_file():
            raise FrameInterpolationNotAvailableError()
        try:
            import torch

            from app.enhancers.rife.IFNet_HDv3_v4_25 import Head, IFNet
        except ImportError as exc:
            raise FrameInterpolationNotAvailableError() from exc

        try:
            # Solo tensores: el .pkl nunca puede ejecutar código al cargarse.
            state = torch.load(self.model_path, map_location="cpu", weights_only=True)
            state = {key.replace("module.", "", 1): value for key, value in state.items()}
            flownet = IFNet()
            missing, _ = flownet.load_state_dict(state, strict=False)
            encode = Head()
            encode.load_state_dict(
                {k.removeprefix("encode."): v for k, v in state.items() if k.startswith("encode.")}
            )
        except (RuntimeError, OSError, ValueError) as exc:
            raise FrameInterpolationFailedError() from exc
        if missing:
            raise FrameInterpolationFailedError()

        dtype = torch.float16 if self.half_precision else torch.float32
        device = torch.device(self.device)
        self._flownet = flownet.eval().to(device, dtype)
        self._encode = encode.eval().to(device, dtype)
        self._dtype = dtype
        self._torch = torch

    def _prepare(self, width: int, height: int) -> None:
        if self._size == (width, height):
            return
        torch = self._torch
        scale = 0.5 if max(width, height) >= HALF_SCALE_MIN_SIDE else 1.0
        modulo = max(PAD_MODULO, int(PAD_MODULO / scale))
        self._pw = math.ceil(width / modulo) * modulo
        self._ph = math.ceil(height / modulo) * modulo
        self._padding = (0, self._pw - width, 0, self._ph - height)
        self._flownet.scale_list = [16 / scale, 8 / scale, 4 / scale, 2 / scale, 1 / scale]
        device = torch.device(self.device)
        self._flow_div = torch.tensor(
            [(self._pw - 1.0) / 2.0, (self._ph - 1.0) / 2.0], dtype=torch.float, device=device
        )
        horizontal = torch.linspace(-1.0, 1.0, self._pw, dtype=torch.float, device=device)
        horizontal = horizontal.view(1, 1, 1, self._pw).expand(-1, -1, self._ph, -1)
        vertical = torch.linspace(-1.0, 1.0, self._ph, dtype=torch.float, device=device)
        vertical = vertical.view(1, 1, self._ph, 1).expand(-1, -1, -1, self._pw)
        self._grid = torch.cat([horizontal, vertical], 1)
        self._size = (width, height)
        self._cached = None

    def _tensor(self, frame: Frame) -> tuple[Any, Any]:
        """(padded image, encoded features); the last frame is reused for the next pair."""
        if self._cached is not None and self._cached[0] is frame:
            return self._cached[1], self._cached[2]
        import numpy as np

        torch = self._torch
        pixels = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)
        image = torch.from_numpy(pixels.copy()).to(self.device)
        image = image.permute(2, 0, 1).unsqueeze(0).to(self._dtype) / 255.0
        image = torch.nn.functional.pad(image, self._padding)
        features = self._encode(image)
        self._cached = (frame, image, features)
        return image, features

    def interpolate(self, first: Frame, second: Frame, timesteps: list[float]) -> list[Frame]:
        """In-between frames at `timesteps` (0 < t < 1) from `first` towards `second`."""
        self.load_model()
        torch = self._torch
        width, height = first.width, first.height
        try:
            with torch.inference_mode():
                self._prepare(width, height)
                image0, features0 = self._tensor(first)
                image1, features1 = self._tensor(second)
                frames = []
                for timestep in timesteps:
                    step = torch.full(
                        [1, 1, self._ph, self._pw], timestep, dtype=self._dtype, device=self.device
                    )
                    output = self._flownet(
                        image0, image1, step, self._flow_div, self._grid, features0, features1
                    )
                    output = output[:, :, :height, :width].squeeze(0).permute(1, 2, 0)
                    pixels = (output.float().clamp(0, 1) * 255).round().to(torch.uint8).cpu()
                    frames.append(Frame(pixels.numpy().tobytes(), width, height))
                return frames
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise CUDAOutOfMemoryError() from exc
            raise FrameInterpolationFailedError() from exc
