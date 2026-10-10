from __future__ import annotations

import threading
from typing import IO


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
            self._text = self._stream.read() or ""  # type: ignore[union-attr]
        except (OSError, ValueError):
            self._text = ""

    def text(self, timeout: float = 5.0) -> str:
        if self._thread is not None:
            self._thread.join(timeout)
        return self._text.strip()
