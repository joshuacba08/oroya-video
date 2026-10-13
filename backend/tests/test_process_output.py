import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.errors import FFmpegStalledError, InsufficientTempStorageError
from app.services.frame_extraction_service import (
    ensure_temp_storage_capacity,
    estimate_png_frames_bytes,
)
from app.utils.process_output import StderrDrain, is_disk_full, watch_process_output


def test_stderr_drain_prevents_pipe_deadlock_with_large_stderr() -> None:
    # Writes far more than the OS pipe buffer to stderr before finishing stdout.
    script = "import sys\nsys.stderr.write('w' * 1_000_000)\nsys.stderr.flush()\nprint('frame=1')\n"
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        text=True,
    )
    drain = StderrDrain(process.stderr)

    stdout_lines = [line.strip() for line in process.stdout]  # type: ignore[union-attr]
    return_code = process.wait(timeout=20)

    assert stdout_lines == ["frame=1"]
    assert return_code == 0
    assert len(drain.text()) == 1_000_000


def test_stderr_drain_handles_missing_stream() -> None:
    assert StderrDrain(None).text() == ""


def _blocking_stream(first_lines: list[str]):
    """stdout that writes some lines and then hangs, like a stuck ffmpeg."""
    yield from first_lines
    threading.Event().wait()


def test_watch_process_output_yields_lines_and_ends_at_eof() -> None:
    lines = list(watch_process_output(iter(["frame=1\n", "progress=end\n"]), 5))

    assert lines == ["frame=1\n", "progress=end\n"]


def test_watch_process_output_ticks_while_silent_and_detects_a_stall() -> None:
    seen: list[str | None] = []

    with pytest.raises(FFmpegStalledError):
        for item in watch_process_output(
            _blocking_stream(["frame=1\n"]), stall_timeout_seconds=0.3, tick_seconds=0.05
        ):
            seen.append(item)

    assert seen[0] == "frame=1\n"
    assert None in seen


def test_disk_full_is_detected_from_ffmpeg_output() -> None:
    assert is_disk_full("av_interleaved_write_frame(): No space left on device")
    assert is_disk_full("There is not enough space on the disk.")
    assert not is_disk_full("Invalid data found when processing input")
    assert not is_disk_full(None)


def test_extraction_estimate_uses_resolution_and_frame_count() -> None:
    video = SimpleNamespace(
        duration_seconds=60.0, fps=30.0, width=1920, height=1080, file_size_bytes=50 * 1024**2
    )
    needed = estimate_png_frames_bytes(1800, 1920, 1080)

    with patch(
        "app.services.frame_extraction_service.shutil.disk_usage",
        return_value=(0, 0, needed),
    ):
        with pytest.raises(InsufficientTempStorageError, match="GB are needed"):
            ensure_temp_storage_capacity(video, Settings())
    with patch(
        "app.services.frame_extraction_service.shutil.disk_usage",
        return_value=(0, 0, needed + 1024**3),
    ):
        ensure_temp_storage_capacity(video, Settings())
