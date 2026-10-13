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


class InterpolationStage:
    """Turn processed source frames into output frames at a higher frame rate.

    The frames between source i and i+1 need both, so they are produced when i+1 arrives:
    `push` returns the output frames of the previous interval (completing source frame i).
    At the end, `flush` completes the last frame (repeated: there is nothing after it).
    """

    def __init__(self, interpolator: Any, schedule: Any, scene_change: Any) -> None:
        self.interpolator = interpolator
        self.schedule = schedule
        self.scene_change = scene_change
        self.pending: tuple[int, Frame] | None = None
        self.scene_changes = 0

    def push(self, index: int, frame: Frame) -> tuple[int | None, list[Frame]]:
        """(source frame completed by this push or None, its output frames)."""
        completed: tuple[int | None, list[Frame]] = (None, [])
        if self.pending is not None:
            previous_index, previous = self.pending
            completed = (previous_index, self._interval(previous_index, previous, frame))
        self.pending = (index, frame)
        return completed

    def flush(self) -> tuple[int | None, list[Frame]]:
        if self.pending is None:
            return None, []
        index, frame = self.pending
        self.pending = None
        return index, [frame] * len(self.schedule.timesteps(index))

    def _interval(self, index: int, first: Frame, second: Frame) -> list[Frame]:
        timesteps = self.schedule.timesteps(index)
        if self.scene_change(first, second):
            self.scene_changes += 1
            return [first] * len(timesteps)
        between = [step for step in timesteps if step > 0]
        synthesised = iter(self.interpolator.interpolate(first, second, between) if between else [])
        return [first if step == 0 else next(synthesised) for step in timesteps]


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
