from __future__ import annotations

import shutil
from pathlib import Path

from app.core.errors import OriginalFramesNotFoundError
from app.enhancers.base import CancelCallback, FrameEnhancer, PauseCallback, ProgressCallback


class MockFrameEnhancer(FrameEnhancer):
    name = "Mock Frame Enhancer"
    engine = "mock"

    def enhance_frames(
        self,
        input_dir: Path,
        output_dir: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
        pause_callback: PauseCallback | None = None,
    ) -> int:
        frame_files = sorted(frame for frame in input_dir.glob("*.png") if frame.is_file())
        if not frame_files:
            raise OriginalFramesNotFoundError()

        output_dir.mkdir(parents=True, exist_ok=True)
        total = len(frame_files)
        processed = 0

        for frame in frame_files:
            if cancel_callback and cancel_callback():
                break
            if pause_callback and pause_callback():
                break

            shutil.copy2(frame, output_dir / frame.name)
            processed += 1
            if progress_callback:
                progress_callback(processed, total)

        return processed
