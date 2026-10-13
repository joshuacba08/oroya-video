import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.db.repositories import job_repository
from app.enhancers.stream import PassthroughProcessor
from app.main import create_app
from app.services import process_registry_service
from app.services.streaming_pipeline_service import (
    SEGMENTS_DIR_NAME,
    build_decoder_command,
    list_completed_segments,
    preview_sample_indexes,
    segment_file_name,
)
from app.utils.png import encode_png_rgb, read_png_size
from app.workers.job_runner import process_job_skeleton_sync, resolve_pipeline_mode
from tests.test_frame_extraction import _queue_job, _update_job

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe no disponibles",
)

CLIP_SECONDS = 3
CLIP_FPS = 10


# --- Piezas sueltas ---------------------------------------------------------------------------


def test_only_contiguous_finished_segments_count(tmp_path: Path) -> None:
    for index, start, count in [(0, 0, 8), (1, 8, 8), (3, 24, 6)]:
        (tmp_path / segment_file_name(index, start, count)).write_bytes(b"x")
    (tmp_path / "seg_00002.part.mp4").write_bytes(b"half-written")

    segments = list_completed_segments(tmp_path)

    # El tramo 2 nunca terminó: el 3 se rehace también.
    assert [(s.index, s.start_frame, s.frame_count) for s in segments] == [(0, 0, 8), (1, 8, 8)]
    assert segments[-1].end_frame == 16


def test_preview_samples_cover_the_whole_video() -> None:
    assert preview_sample_indexes(30, 4) == {0, 10, 19, 29}
    assert preview_sample_indexes(3, 24) == {0, 1, 2}
    assert preview_sample_indexes(0, 24) == set()


def test_decoder_seeks_before_the_input_and_outputs_constant_rate_raw_frames() -> None:
    command = build_decoder_command(Path("in.mp4"), 23.976, start_seconds=12.5, duration_seconds=4)

    assert command[command.index("-ss") + 1] == "12.500"
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-vf") + 1] == "fps=23.976"
    assert command[-4:] == ["rawvideo", "-pix_fmt", "rgb24", "pipe:1"]


def test_png_encoder_writes_a_valid_header() -> None:
    png = encode_png_rgb(bytes(range(12)) * 2, 4, 2)

    assert read_png_size(png) == (4, 2)
    with pytest.raises(ValueError):
        encode_png_rgb(b"short", 4, 2)


def test_cancel_stops_every_process_of_the_job() -> None:
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    decoder = subprocess.Popen(sleeper)
    encoder = subprocess.Popen(sleeper)
    process_registry_service.register_process("job-1", decoder.pid, "ffmpeg_decode", decoder)
    process_registry_service.register_process("job-1", encoder.pid, "ffmpeg_encode", encoder)

    assert process_registry_service.terminate_process_for_job("job-1", timeout_seconds=5)

    assert decoder.poll() is not None and encoder.poll() is not None
    assert process_registry_service.get_processes_for_job("job-1") == []


def test_jobs_keep_the_pipeline_they_started_with() -> None:
    settings = SimpleNamespace(pipeline_mode="streaming")

    assert resolve_pipeline_mode(_job_stub(None, None), settings) == "streaming"
    assert resolve_pipeline_mode(_job_stub("legacy", None), settings) == "legacy"
    # Jobs de la 0.4 con fotogramas ya extraídos siguen con el pipeline clásico.
    assert resolve_pipeline_mode(_job_stub(None, "2026-10-01"), settings) == "legacy"


def _job_stub(mode, extraction_started_at) -> SimpleNamespace:
    return SimpleNamespace(pipeline_mode=mode, extraction_started_at=extraction_started_at)


# --- Pipeline completo con ffmpeg real --------------------------------------------------------


def _make_clip(path: Path, seconds: int = CLIP_SECONDS) -> Path:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=size=64x48:rate={CLIP_FPS}:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True,
    )  # fmt: skip
    return path


def _frame_count(path: Path) -> int:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1",
         str(path)],
        capture_output=True, check=True, text=True,
    ).stdout  # fmt: skip
    return int(output.strip())


def _duration(path: Path) -> float:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, check=True, text=True,
    ).stdout  # fmt: skip
    return float(output.strip())


@pytest.fixture
def stream_client(tmp_path: Path):
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'stream.sqlite').as_posix()}",
        exports_dir=str(tmp_path / "exports"),
        pipeline_mode="streaming",
        streaming_segment_frames=8,
        streaming_preview_samples=4,
        cleanup_temp_on_success=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client, _make_clip(tmp_path / "clip.mp4"), settings


def _queued_job(client: TestClient, clip: Path, export_config: dict | None = None) -> str:
    video = client.post(
        "/api/videos/import", json={"file_path": str(clip), "source_mode": "reference"}
    ).json()["video"]
    project = client.post(
        "/api/projects", json={"name": "clip.mp4", "video_asset_id": video["id"]}
    ).json()["project"]
    payload = {"project_id": project["id"]}
    if export_config:
        payload["export_config"] = export_config
    job_id = client.post("/api/jobs", json=payload).json()["job"]["id"]
    _queue_job(client, job_id)
    return job_id


def _job(job_id: str):
    db = database.SessionLocal()
    try:
        return job_repository.get_job_by_id(db, job_id)
    finally:
        db.close()


def _segments(settings: Settings, job_id: str) -> Path:
    return Path(settings.storage_path) / "temp" / "jobs" / job_id / "encoded" / SEGMENTS_DIR_NAME


def _interrupt_at(frame: int, **changes):
    """Mock processor that changes the job (pause, cancel) once `frame` frames went through."""
    original = PassthroughProcessor.process
    seen = {"frames": 0}

    def process(self, data):
        seen["frames"] += 1
        if seen["frames"] == frame:
            _update_job(self._job_id, **changes)
        return original(self, data)

    return patch.object(PassthroughProcessor, "process", process)


@needs_ffmpeg
def test_streaming_processes_in_segments_and_keeps_audio_in_sync(stream_client) -> None:
    client, clip, settings = stream_client
    job_id = _queued_job(client, clip)

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    assert job.pipeline_mode == "streaming"
    assert job.frames_total == CLIP_SECONDS * CLIP_FPS
    assert (job.segments_completed, job.segments_total) == (4, 4)  # 8 + 8 + 8 + 6
    segments_dir = Path(job.encoded_dir) / SEGMENTS_DIR_NAME
    assert sorted(item.name for item in segments_dir.glob("*.mp4")) == [
        segment_file_name(0, 0, 8),
        segment_file_name(1, 8, 8),
        segment_file_name(2, 16, 8),
        segment_file_name(3, 24, 6),
    ]
    export = Path(job.final_export_path)
    assert abs(_duration(export) - CLIP_SECONDS) < 0.15
    # Ni un fotograma perdido al unir los tramos (si no, el audio se desfasa).
    assert _frame_count(export) == CLIP_SECONDS * CLIP_FPS

    # Pares de muestra con su índice real, iguales en original y mejorado.
    originals = {item.name for item in Path(job.original_frames_dir).glob("*.png")}
    enhanced = {item.name for item in Path(job.enhanced_frames_dir).glob("*.png")}
    assert originals == enhanced
    assert {f"frame_{index:08d}.png" for index in (0, 10, 19, 29)} <= originals
    info = client.get(f"/api/v1/jobs/{job_id}/preview").json()
    assert f"frame_{info['recommended_frame_index']:08d}.png" in originals


@needs_ffmpeg
def test_pause_closes_the_segment_and_resume_continues_from_there(stream_client) -> None:
    client, clip, settings = stream_client
    settings.mock_enhancer_frame_delay_ms = 40
    job_id = _queued_job(client, clip)

    with patch.object(PassthroughProcessor, "_job_id", job_id, create=True):
        with _interrupt_at(5, pause_requested=True):
            process_job_skeleton_sync(job_id, settings)

    paused = _job(job_id)
    assert paused.status == "paused"
    done = list_completed_segments(_segments(settings, job_id))
    assert done and done[-1].end_frame < CLIP_SECONDS * CLIP_FPS
    assert not list(_segments(settings, job_id).glob("*.part.mp4"))

    _update_job(job_id, status="queued", pause_requested=False)
    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    segments = list_completed_segments(_segments(settings, job_id))
    assert segments[-1].end_frame == CLIP_SECONDS * CLIP_FPS
    assert abs(_duration(Path(job.final_export_path)) - CLIP_SECONDS) < 0.15


@needs_ffmpeg
def test_cancel_drops_the_segment_in_progress(stream_client) -> None:
    client, clip, settings = stream_client
    settings.mock_enhancer_frame_delay_ms = 40
    job_id = _queued_job(client, clip)

    with patch.object(PassthroughProcessor, "_job_id", job_id, create=True):
        with _interrupt_at(5, status="cancelled", cancel_requested=True):
            process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "cancelled"
    assert job.final_export_path is None
    assert not list(_segments(settings, job_id).glob("*.part.mp4"))
    assert process_registry_service.get_processes_for_job(job_id) == []


@needs_ffmpeg
def test_streaming_processes_only_the_trimmed_fragment(stream_client) -> None:
    client, clip, settings = stream_client
    job_id = _queued_job(client, clip, {"trim": {"start_seconds": 1, "end_seconds": 2}})

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    assert job.frames_total == CLIP_FPS
    assert abs(_duration(Path(job.final_export_path)) - 1) < 0.15
    assert json.loads(job.export_config_json)["trim"] == {"start_seconds": 1, "end_seconds": 2}


@needs_ffmpeg
def test_a_preview_frame_locked_by_the_viewer_does_not_stop_the_job(stream_client) -> None:
    """Windows: deleting the previous live frame while the preview reads it (WinError 32)."""
    client, clip, settings = stream_client
    settings.mock_enhancer_frame_delay_ms = 40
    job_id = _queued_job(client, clip)
    original_unlink = Path.unlink

    def locked_unlink(self, missing_ok=False):
        if self.name.startswith("frame_"):
            raise PermissionError(32, "El proceso no tiene acceso al archivo")
        return original_unlink(self, missing_ok=missing_ok)

    with (
        patch("app.services.streaming_pipeline_service.LIVE_PREVIEW_INTERVAL_SECONDS", 0.05),
        patch.object(Path, "unlink", locked_unlink),
    ):
        process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message


def _make_sync_clip(path: Path, seconds: int = 12) -> Path:
    """A one-frame white flash and a 30 ms beep at the start of every second, 29.97 fps."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=black:s=160x120:r=30000/1001:d={seconds}",
         "-f", "lavfi", "-i",
         f"aevalsrc='if(lt(mod(t,1),0.03),sin(2*PI*1000*t),0)':s=44100:d={seconds}",
         "-vf", "drawbox=c=white:t=fill:enable='lt(mod(t,1),0.033)'",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path


def _flash_times(path: Path) -> list[float]:
    output = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:v:0",
         "-vf", "signalstats,metadata=mode=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr  # fmt: skip
    times: list[float] = []
    pts = 0.0
    for line in output.splitlines():
        if "pts_time:" in line:
            pts = float(line.split("pts_time:")[1].split()[0])
        elif "YAVG=" in line and float(line.split("YAVG=")[1]) > 128:
            if not times or pts - times[-1] > 0.5:
                times.append(pts)
    return times


def _beep_times(path: Path) -> list[float]:
    output = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
         "-af", "silencedetect=n=-30dB:d=0.2", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr  # fmt: skip
    return [float(line.split("silence_end: ")[1].split()[0])
            for line in output.splitlines() if "silence_end" in line]  # fmt: skip


@needs_ffmpeg
@pytest.mark.parametrize("trim", [None, {"start_seconds": 2.5, "end_seconds": 10.5}])
def test_audio_stays_in_sync_with_the_video(stream_client, tmp_path, trim) -> None:
    client, _, settings = stream_client
    clip = _make_sync_clip(tmp_path / "sync.mp4")
    job_id = _queued_job(client, clip, {"trim": trim} if trim else None)

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    export = Path(job.final_export_path)
    flashes, beeps = _flash_times(export), _beep_times(export)
    assert len(flashes) >= 6
    # El pitido del segundo 0 no tiene silencio delante: no se detecta su inicio.
    for flash in [flash for flash in flashes if flash > 0.2]:
        nearest = min(beeps, key=lambda beep: abs(beep - flash))
        assert abs(nearest - flash) < 0.05, (flash, nearest)
