from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch


def assert_error_response(
    response,
    *,
    status_code: int,
    error: str,
    message: str,
    details: dict | None = None,
) -> dict:
    payload = response.json()
    assert response.status_code == status_code
    assert payload["error"] == error
    assert payload["message"] == message
    assert isinstance(payload["details"], dict)
    if details is not None:
        assert payload["details"] == details
    assert payload["request_id"].startswith("req_")
    assert payload["timestamp"].endswith("Z")
    return payload


@contextmanager
def patch_job_preflight_ready() -> Iterator[None]:
    with (
        patch(
            "app.services.job_preflight_service.validate_ffmpeg_available",
            return_value="C:/ffmpeg.exe",
        ),
        patch(
            "app.services.job_preflight_service._get_ffprobe_path",
            return_value="C:/ffprobe.exe",
        ),
        patch(
            "app.services.job_preflight_service.shutil.disk_usage",
            return_value=(50 * 1024**3, 10 * 1024**3, 20 * 1024**3),
        ),
    ):
        yield
