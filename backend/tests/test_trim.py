import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.audio_mux_service import (
    build_audio_aac_mux_command,
    build_audio_copy_mux_command,
)
from app.services.frame_extraction_service import (
    build_frame_extraction_command,
    estimate_total_frames,
)
from app.utils.trim import TrimRange, get_job_trim, parse_trim, trim_input_args
from tests.test_projects import _create_project, _import_video


def _job(trim: dict | None, duration: float = 10.0, fps: float = 30.0) -> SimpleNamespace:
    return SimpleNamespace(
        export_config_json=json.dumps({"trim": trim} if trim is not None else {}),
        video_asset=SimpleNamespace(duration_seconds=duration, fps=fps),
        total_frames=None,
    )


def test_trim_is_clamped_to_the_video_and_ignored_when_it_covers_everything() -> None:
    assert parse_trim({"start_seconds": 2, "end_seconds": 5}, 10) == TrimRange(2.0, 5.0)
    assert parse_trim({"start_seconds": 4}, 10) == TrimRange(4.0, 10.0)
    assert parse_trim({"start_seconds": 4, "end_seconds": 99}, 10) == TrimRange(4.0, 10.0)
    assert parse_trim({"start_seconds": 0, "end_seconds": 10}, 10) is None
    assert parse_trim({}, 10) is None
    assert parse_trim(None, 10) is None
    # Demasiado corto tras ajustar al video: se procesa entero.
    assert parse_trim({"start_seconds": 9.8}, 10) is None


def test_trim_args_seek_before_the_input() -> None:
    assert trim_input_args(TrimRange(1.5, 4.0)) == ["-ss", "1.500", "-t", "2.500"]
    assert trim_input_args(None) == []

    command = build_frame_extraction_command(Path("in.mp4"), Path("out"), trim=TrimRange(1.5, 4.0))
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-t") + 1] == "2.500"


def test_audio_is_cut_at_the_same_points_as_the_video() -> None:
    trim = TrimRange(2.0, 3.0)
    for builder in (build_audio_copy_mux_command, build_audio_aac_mux_command):
        command = builder(Path("silent.mp4"), Path("original.mp4"), Path("out.mp4"), trim)
        original_input = command.index("original.mp4")
        assert command[original_input - 5 : original_input] == ["-ss", "2.000", "-t", "1.000", "-i"]
        # El video mudo (primera entrada) ya está recortado: sin -ss delante.
        assert command.index("-ss") > command.index("silent.mp4")


def test_frame_estimate_uses_the_trimmed_duration() -> None:
    assert estimate_total_frames(_job({"start_seconds": 2, "end_seconds": 4})) == 60
    assert estimate_total_frames(_job(None)) == 300
    assert get_job_trim(_job({"start_seconds": 2, "end_seconds": 4})) == TrimRange(2.0, 4.0)


def test_trim_is_validated_against_the_video(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'trim.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]

        def patch(trim: object):
            return client.patch(
                f"/api/v1/projects/{project_id}", json={"export_config": {"trim": trim}}
            )

        too_short = patch({"start_seconds": 10, "end_seconds": 10.2})
        negative = patch({"start_seconds": -1, "end_seconds": 5})
        unknown_key = patch({"start": 1})
        after_end = patch({"start_seconds": 500})  # el video de prueba dura 128,45 s
        valid = patch({"start_seconds": 10, "end_seconds": 20.5})
        cleared = patch(None)

    assert too_short.status_code == 400
    assert negative.status_code == 400
    assert unknown_key.status_code == 400
    assert after_end.status_code == 400
    assert valid.status_code == 200
    assert valid.json()["project"]["export_config"]["trim"] == {
        "start_seconds": 10,
        "end_seconds": 20.5,
    }
    assert cleared.status_code == 200
    assert cleared.json()["project"]["export_config"].get("trim") is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg no disponible")
def test_ffmpeg_extracts_only_the_trimmed_fragment(tmp_path) -> None:
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc=size=64x48:rate=10:duration=3", "-pix_fmt", "yuv420p", str(clip)],
        check=True,
    )  # fmt: skip
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    command = build_frame_extraction_command(clip, frames_dir, trim=TrimRange(1.0, 2.0))

    result = subprocess.run(command, capture_output=True)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")

    assert len(list(frames_dir.glob("*.png"))) == 10
