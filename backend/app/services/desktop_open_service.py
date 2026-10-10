"""Open local files and folders with the OS default handler.

The backend always runs on the user's machine (dev server or Tauri sidecar), so it
can open exports directly. This works the same from the browser and the desktop app.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


def open_file(path: Path) -> bool:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as error:
        logger.warning("Could not open %s: %s", path, error)
        return False
    return True


def reveal_in_folder(path: Path) -> bool:
    """Open the containing folder, selecting the file when the platform allows it."""
    try:
        if sys.platform == "win32":
            if path.is_file():
                subprocess.Popen(["explorer", f"/select,{path}"])
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
    except OSError as error:
        logger.warning("Could not reveal %s: %s", path, error)
        return False
    return True
