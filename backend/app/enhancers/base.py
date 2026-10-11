from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]
PauseCallback = Callable[[], bool]


class FrameEnhancer(ABC):
    name: str
    engine: str

    @abstractmethod
    def enhance_frames(
        self,
        input_dir: Path,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
        pause_callback: PauseCallback | None = None,
    ) -> int:
        raise NotImplementedError
