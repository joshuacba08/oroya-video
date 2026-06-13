from __future__ import annotations

from pathlib import Path

from app.core.errors import PreviewFrameAccessDeniedError, PreviewFrameNotFoundError

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def validate_input_image_path(path: Path) -> Path:
    resolved_path = path.expanduser().resolve()
    if resolved_path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise PreviewFrameAccessDeniedError()
    if not resolved_path.exists() or not resolved_path.is_file():
        raise PreviewFrameNotFoundError()
    return resolved_path
