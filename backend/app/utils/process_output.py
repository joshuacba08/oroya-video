from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterator
from typing import IO

from app.core.errors import FFmpegStalledError


class StderrDrain:
    """Read a subprocess stderr pipe in the background.

    ffmpeg reports progress on stdout while stderr carries warnings. If stderr is only
    read after stdout ends and ffmpeg fills the OS pipe buffer (~4 KB on Windows),
    both processes block forever. Draining it concurrently avoids that deadlock.
    """

    def __init__(self, stream: IO[str] | None) -> None:
        self._stream = stream
        self._text = ""
        self._thread: threading.Thread | None = None
        if stream is not None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            output = self._stream.read() or ""  # type: ignore[union-attr]
        except (OSError, ValueError):
            output = ""
        # Las tuberías binarias (pipeline por streaming) devuelven bytes.
        self._text = output.decode("utf-8", "replace") if isinstance(output, bytes) else output

    def text(self, timeout: float = 5.0) -> str:
        if self._thread is not None:
            self._thread.join(timeout)
        return self._text.strip()


_END = object()


def watch_process_output(
    stream: IO[str] | None,
    stall_timeout_seconds: float,
    tick_seconds: float = 1.0,
) -> Iterator[str | None]:
    """Yield the lines of a subprocess stdout, read in the background.

    ffmpeg with `-progress` writes a block every ~0.5 s, so long silence means it hung.
    - Yields `None` after each `tick_seconds` without output, so the caller can check
      cancellation without waiting for the next line.
    - Raises `FFmpegStalledError` after `stall_timeout_seconds` without any output.
    """
    if stream is None:
        return
    lines: queue.Queue[object] = queue.Queue()

    def read() -> None:
        try:
            for line in stream:
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(_END)

    threading.Thread(target=read, daemon=True, name="process-output").start()
    last_output = time.monotonic()
    while True:
        try:
            item = lines.get(timeout=tick_seconds)
        except queue.Empty:
            if time.monotonic() - last_output >= stall_timeout_seconds:
                raise FFmpegStalledError() from None
            yield None
            continue
        if item is _END:
            return
        last_output = time.monotonic()
        yield item  # type: ignore[misc]


DISK_FULL_MARKERS = ("no space left on device", "not enough space on the disk")


def is_disk_full(stderr_text: str | None) -> bool:
    text = (stderr_text or "").lower()
    return any(marker in text for marker in DISK_FULL_MARKERS)


def stop_process_quietly(process) -> None:
    try:
        process.kill()
        process.wait(timeout=5)
    except Exception:  # noqa: BLE001 - el proceso ya pudo haber terminado
        pass
