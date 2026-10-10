import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.video_probe_service import format_duration, parse_fps
from tests.helpers import assert_error_response

VIDEO_PATH = "sample.mp4"
UNSUPPORTED_VIDEO_PATH = "sample.avi"
VIDEO_SIZE_BYTES = 524288000
VALID_FFPROBE_PAYLOAD = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "24000/1001",
            "pix_fmt": "yuv420p",
            "profile": "High",
            "bit_rate": "7500000",
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "bit_rate": "320000",
        },
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "128.45",
        "bit_rate": "8000000",
    },
}


def _completed_process(
    stdout: str,
    *,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_video_probe_returns_404_when_file_does_not_exist() -> None:
    with (
        patch("app.services.video_probe_service.Path.exists", return_value=False),
        patch("app.services.video_probe_service.Path.is_file", return_value=False),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert_error_response(
        response,
        status_code=404,
        error="video_file_not_found",
        message="Video file was not found.",
    )


def test_video_probe_returns_400_for_unsupported_extension() -> None:
    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": UNSUPPORTED_VIDEO_PATH})

    assert_error_response(
        response,
        status_code=400,
        error="unsupported_video_format",
        message="Only MP4, MOV and MKV files are supported in the MVP.",
    )


def test_video_probe_returns_503_when_ffprobe_is_not_available() -> None:
    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        patch("app.services.tool_detection_service.resolve_tool_path", return_value=None),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert_error_response(
        response,
        status_code=503,
        error="ffprobe_not_available",
        message="FFprobe is required to analyze video files.",
    )


def test_video_probe_returns_422_when_ffprobe_fails() -> None:
    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        patch(
            "app.services.tool_detection_service.resolve_tool_path",
            return_value="ffprobe",
        ),
        patch(
            "app.services.video_probe_service.subprocess.run",
            return_value=_completed_process("", returncode=1, stderr="ffprobe error"),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert_error_response(
        response,
        status_code=422,
        error="video_probe_failed",
        message="The video metadata could not be analyzed.",
    )


def test_video_probe_returns_422_when_ffprobe_output_is_empty() -> None:
    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        patch(
            "app.services.tool_detection_service.resolve_tool_path",
            return_value="ffprobe",
        ),
        patch(
            "app.services.video_probe_service.subprocess.run",
            return_value=_completed_process(None),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert_error_response(
        response,
        status_code=422,
        error="video_probe_failed",
        message="The video metadata could not be analyzed.",
    )


def test_video_probe_returns_422_when_video_stream_is_missing() -> None:
    ffprobe_payload = {
        "streams": [
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
            }
        ],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "10.0"},
    }

    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        patch(
            "app.services.tool_detection_service.resolve_tool_path",
            return_value="ffprobe",
        ),
        patch(
            "app.services.video_probe_service.subprocess.run",
            return_value=_completed_process(json.dumps(ffprobe_payload)),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert_error_response(
        response,
        status_code=422,
        error="video_stream_not_found",
        message="No video stream was detected in the selected file.",
    )


def test_video_probe_returns_metadata_when_ffprobe_succeeds() -> None:
    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        patch(
            "app.services.video_probe_service.Path.stat",
            return_value=SimpleNamespace(st_size=VIDEO_SIZE_BYTES),
        ),
        patch(
            "app.services.tool_detection_service.resolve_tool_path",
            return_value="ffprobe",
        ),
        patch(
            "app.services.video_probe_service.subprocess.run",
            return_value=_completed_process(json.dumps(VALID_FFPROBE_PAYLOAD)),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["file"]["name"] == "sample.mp4"
    assert payload["file"]["extension"] == ".mp4"
    assert payload["file"]["size_bytes"] == VIDEO_SIZE_BYTES
    assert payload["file"]["size_mb"] == 500.0
    assert payload["format"]["duration_seconds"] == 128.45
    assert payload["format"]["duration_label"] == "00:02:08"
    assert payload["video"]["codec"] == "h264"
    assert payload["video"]["fps"] == 23.976
    assert payload["audio"]["available"] is True
    assert payload["warnings"] == []


def test_video_probe_returns_warning_when_audio_stream_is_missing() -> None:
    ffprobe_payload = {
        "streams": [VALID_FFPROBE_PAYLOAD["streams"][0]],
        "format": VALID_FFPROBE_PAYLOAD["format"],
    }

    with (
        patch("app.services.video_probe_service.Path.exists", return_value=True),
        patch("app.services.video_probe_service.Path.is_file", return_value=True),
        patch(
            "app.services.video_probe_service.Path.stat",
            return_value=SimpleNamespace(st_size=VIDEO_SIZE_BYTES),
        ),
        patch(
            "app.services.tool_detection_service.resolve_tool_path",
            return_value="ffprobe",
        ),
        patch(
            "app.services.video_probe_service.subprocess.run",
            return_value=_completed_process(json.dumps(ffprobe_payload)),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/api/videos/probe", json={"file_path": VIDEO_PATH})

    assert response.status_code == 200
    payload = response.json()
    assert payload["audio"]["available"] is False
    assert payload["warnings"] == ["No audio stream detected."]


def test_parse_fps_returns_fractional_value() -> None:
    assert parse_fps("24000/1001") == 23.976


def test_parse_fps_returns_none_for_zero_division() -> None:
    assert parse_fps("0/0") is None


def test_format_duration_returns_hh_mm_ss() -> None:
    assert format_duration(3661) == "01:01:01"
