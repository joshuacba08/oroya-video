"""Frame processors for the streaming pipeline: one decoded frame in, one processed frame out.

Frames travel as `rgb24` bytes (what ffmpeg reads and writes through the pipes). The mock
engine only needs the standard library; the AI processors convert to the BGR numpy images
that Real-ESRGAN and GFPGAN expect, and back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class Frame:
    data: bytes
    width: int
    height: int


class FrameProcessor(Protocol):
    engine: str
    failed_frames: int

    def process(self, frame: Frame) -> Frame: ...


class PassthroughProcessor:
    """Mock engine: the frame unchanged (the output scale is applied when encoding)."""

    engine = "mock"

    def __init__(self, frame_delay_seconds: float = 0.0) -> None:
        # Retardo opcional por frame (tests E2E y demos): permite pausar o cancelar a mitad.
        self.frame_delay_seconds = max(frame_delay_seconds, 0.0)
        self.failed_frames = 0

    def process(self, frame: Frame) -> Frame:
        if self.frame_delay_seconds:
            time.sleep(self.frame_delay_seconds)
        return frame


class ImageProcessor:
    """Real-ESRGAN upscale and/or GFPGAN face restoration on in-memory images."""

    def __init__(self, enhancer: Any | None = None, face_restorer: Any | None = None) -> None:
        self.enhancer = enhancer
        self.face_restorer = face_restorer
        self.engine = getattr(enhancer, "engine", "mock")

    @property
    def failed_frames(self) -> int:
        return getattr(self.enhancer, "failed_frames", 0)

    def load(self) -> None:
        if self.enhancer is not None:
            self.enhancer.load_model()
        if self.face_restorer is not None:
            self.face_restorer.load_model()

    def process(self, frame: Frame) -> Frame:
        import numpy as np

        rgb = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)
        image = np.ascontiguousarray(rgb[:, :, ::-1])
        if self.enhancer is not None:
            image = self.enhancer.enhance_image(image)
        if self.face_restorer is not None:
            image = self.face_restorer.restore_image(image)
        output = np.ascontiguousarray(image[:, :, ::-1])
        height, width = output.shape[:2]
        return Frame(output.tobytes(), width, height)
