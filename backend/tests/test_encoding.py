import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.encoding_options import (
    EncodingChoice,
    build_video_codec_args,
    detect_hardware_encoders,
    resolve_encoding,
)
from app.workers.job_runner import process_job_skeleton_sync
from tests.test_frame_extraction import _update_job
from tests.test_projects import _create_project, _import_video
from tests.test_streaming_pipeline import (  # noqa: F401
    _job,
    _queued_job,
    needs_ffmpeg,
    stream_client,
)


def test_quality_maps_to_crf_and_cq() -> None:
    software = build_video_codec_args(EncodingChoice("h264", "balanced"), hardware_available=True)
    assert software.args[:2] == ["-c:v", "libx264"]
    assert software.args[software.args.index("-crf") + 1] == "20"

    nvenc = build_video_codec_args(
        EncodingChoice("h265", "small", hardware=True, ten_bit=True), hardware_available=True
    )
    assert nvenc.encoder == "hevc_nvenc"
    assert nvenc.args[nvenc.args.index("-cq") + 1] == "26"
    assert nvenc.pix_fmt == "p010le"
    assert nvenc.args[nvenc.args.index("-tag:v") + 1] == "hvc1"


def test_gpu_falls_back_to_cpu_and_ten_bit_is_h265_only() -> None:
    fallback = build_video_codec_args(
        EncodingChoice("h264", hardware=True, ten_bit=True), hardware_available=False
    )
    assert fallback.encoder == "libx264"
    assert fallback.pix_fmt == "yuv420p"  # H.264 de 10 bits apenas se reproduce: se ignora.
    assert not fallback.hardware


def test_encoding_is_read_from_the_export_config() -> None:
    assert resolve_encoding({"codec": "h264"}) == EncodingChoice()
    assert resolve_encoding(
        {"codec": "h264", "encoding": {"codec": "h265", "quality": "small", "ten_bit": True}}
    ) == EncodingChoice("h265", "small", False, True)
    assert resolve_encoding({"encoding": {"codec": "vp9", "quality": "x"}}) == EncodingChoice()


def test_encoding_settings_are_validated(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'enc.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]

        def patch_export(**values):
            return client.patch(f"/api/v1/projects/{project_id}", json={"export_config": values})

        bad_codec = patch_export(encoding={"codec": "vp9"})
        bad_flag = patch_export(encoding={"hardware": "yes"})
        valid = patch_export(
            codec="h265", encoding={"codec": "h265", "quality": "balanced", "ten_bit": True}
        )

    assert bad_codec.status_code == 400
    assert bad_flag.status_code == 400
    assert valid.status_code == 200
    assert valid.json()["project"]["export_config"]["encoding"]["quality"] == "balanced"


def test_encoders_endpoint_reports_gpu_encoders(tmp_path) -> None:
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'e.sqlite').as_posix()}",
    )
    with (
        patch(
            "app.api.routes_system.detect_hardware_encoders",
            return_value={"h264": True, "h265": False},
        ),
        TestClient(create_app(settings)) as client,
    ):
        response = client.get("/api/v1/system/encoders")

    assert response.status_code == 200
    assert response.json() == {"hardware": {"h264": True, "h265": False}}


def _stream_info(path: Path) -> dict:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,profile,pix_fmt,codec_tag_string", "-of", "json", str(path)],
        capture_output=True, check=True, text=True,
    ).stdout  # fmt: skip
    return json.loads(output)["streams"][0]


def _set_encoding(job_id: str, encoding: dict) -> None:
    config = json.loads(_job(job_id).export_config_json)
    config["encoding"] = encoding
    config["codec"] = encoding["codec"]
    _update_job(job_id, export_config_json=json.dumps(config))


@needs_ffmpeg
def test_h265_ten_bit_export(stream_client) -> None:  # noqa: F811
    client, clip, settings = stream_client
    job_id = _queued_job(client, clip)
    _set_encoding(job_id, {"codec": "h265", "quality": "high", "ten_bit": True})

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    info = _stream_info(Path(job.final_export_path))
    assert (info["codec_name"], info["profile"], info["pix_fmt"], info["codec_tag_string"]) == (
        "hevc",
        "Main 10",
        "yuv420p10le",
        "hvc1",
    )
    assert job.encoding_codec == "h265"


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None
    or not detect_hardware_encoders(shutil.which("ffmpeg")).get("h264"),
    reason="NVENC no disponible",
)
def test_gpu_encoded_export(stream_client, tmp_path) -> None:  # noqa: F811
    client, _, settings = stream_client
    clip = tmp_path / "big.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=size=320x240:rate=10:duration=2", "-pix_fmt", "yuv420p", str(clip)],
        check=True,
    )  # fmt: skip
    job_id = _queued_job(client, clip)
    _set_encoding(job_id, {"codec": "h264", "quality": "balanced", "hardware": True})

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    assert _stream_info(Path(job.final_export_path))["codec_name"] == "h264"
    logs = [log for log in _job_logs(job_id) if "GPU encoding is not available" in log]
    assert not logs


def _job_logs(job_id: str) -> list[str]:
    from app.db import database
    from app.db.repositories import job_repository

    db = database.SessionLocal()
    try:
        return [
            log.message for log in job_repository.list_job_logs(db, job_id, limit=500, offset=0)
        ]
    finally:
        db.close()


def test_small_outputs_are_encoded_on_the_cpu() -> None:
    from app.services.encoding_options import hardware_fits

    assert not hardware_fits(128, 96)
    assert hardware_fits(1280, 960)
