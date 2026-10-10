from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import FFmpegNotAvailableError, RealESRGANModelLoadFailedError
from app.db import database
from app.db.repositories import job_repository
from app.main import create_app
from app.schemas.video_schema import (
    AudioStreamInfo,
    StreamSummary,
    VideoFileInfo,
    VideoFormatInfo,
    VideoProbeResponse,
    VideoStreamInfo,
)
from app.services.frame_extraction_service import (
    build_frame_extraction_command,
    count_extracted_frames,
    parse_ffmpeg_progress_line,
)
from app.services.job_workspace_service import prepare_job_workspace
from app.workers.job_runner import process_job_skeleton_sync
from tests.helpers import assert_error_response, patch_job_preflight_ready


def _build_probe_response(source_path: Path) -> VideoProbeResponse:
    return VideoProbeResponse(
        valid=True,
        file=VideoFileInfo(
            path=str(source_path.resolve()),
            name=source_path.name,
            extension=source_path.suffix.lower(),
            size_bytes=source_path.stat().st_size,
            size_mb=round(source_path.stat().st_size / (1024**2), 1),
        ),
        format=VideoFormatInfo(
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration_seconds=5.0,
            duration_label="00:00:05",
            bit_rate=8000000,
        ),
        video=VideoStreamInfo(
            codec="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            width=1920,
            height=1080,
            resolution_label="1920x1080",
            fps=24.0,
            pix_fmt="yuv420p",
            profile="High",
            bit_rate=7500000,
        ),
        audio=AudioStreamInfo(
            available=True,
            codec="aac",
            codec_long_name="AAC (Advanced Audio Coding)",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
            bit_rate=320000,
        ),
        streams=[
            StreamSummary(index=0, type="video", codec="h264", width=1920, height=1080),
            StreamSummary(index=1, type="audio", codec="aac"),
        ],
        warnings=[],
    )


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):
        yield from self._lines


class FakeStderr:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def read(self) -> str:
        return self._text


class FakePopen:
    def __init__(
        self,
        command: list[str],
        *,
        lines: list[str] | None = None,
        returncode: int = 0,
        stderr_text: str = "",
        frames_to_create: int = 0,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        output_pattern = Path(command[-1])
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        for index in range(frames_to_create):
            (output_pattern.parent / f"frame_{index:08d}.png").write_bytes(b"png")
        self.stdout = FakeStdout(lines or [])
        self.stderr = FakeStderr(stderr_text)

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


@pytest.fixture
def frame_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "frames.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file, settings


def _import_video(client: TestClient, source_file: Path) -> dict:
    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file),
    ):
        response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    assert response.status_code == 201
    return response.json()["video"]


def _create_project(client: TestClient, video_asset_id: str) -> dict:
    response = client.post(
        "/api/projects",
        json={"name": "Frame Project", "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(client: TestClient, project_id: str) -> dict:
    response = client.post("/api/jobs", json={"project_id": project_id})
    assert response.status_code == 201
    return response.json()["job"]


def _queue_job(client: TestClient, job_id: str) -> None:
    with (
        patch_job_preflight_ready(),
        patch("app.services.job_service.job_queue.enqueue", new_callable=AsyncMock),
    ):
        response = client.post(f"/api/jobs/{job_id}/start")

    assert response.status_code == 200


def _update_job(job_id: str, **changes) -> None:
    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        assert job is not None
        for key, value in changes.items():
            setattr(job, key, value)
        db.commit()
    finally:
        db.close()


def test_build_frame_extraction_command_contains_expected_arguments() -> None:
    command = build_frame_extraction_command(
        Path("C:/videos/input.mp4"),
        Path("C:/temp/job/frames/original"),
    )

    assert command[0] == "ffmpeg"
    assert "-i" in command
    assert "pipe:1" in command
    assert str(Path("C:/temp/job/frames/original") / "frame_%08d.png") in command


def test_parse_progress_line_and_count_extracted_frames(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_00000000.png").write_bytes(b"png")
    (frames_dir / "frame_00000001.png").write_bytes(b"png")
    (frames_dir / "ignore.txt").write_text("x", encoding="utf-8")

    assert parse_ffmpeg_progress_line("frame=120") == {"frame": "120"}
    assert count_extracted_frames(frames_dir) == 2


def test_prepare_job_workspace_creates_expected_directories(tmp_path: Path) -> None:
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'workspace.sqlite').as_posix()}",
        debug=True,
    )

    workspace = prepare_job_workspace("job-123", settings)

    assert workspace["working_dir"].exists()
    assert workspace["original_frames_dir"].exists()
    assert workspace["enhanced_frames_dir"].exists()
    assert workspace["logs_dir"].exists()
    assert (workspace["working_dir"] / "metadata.json").exists()


def test_start_job_returns_503_when_ffmpeg_is_missing(frame_client) -> None:
    client, source_file, _ = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])

    with (
        patch(
            "app.services.job_preflight_service.validate_ffmpeg_available",
            side_effect=FFmpegNotAvailableError(),
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
        response = client.post(f"/api/jobs/{job['id']}/start")

    payload = assert_error_response(
        response,
        status_code=409,
        error="job_preflight_failed",
        message="Job preflight checks failed.",
    )
    assert payload["details"]["checks"]["ffmpeg_available"] is False


def test_start_job_returns_400_when_temp_storage_is_insufficient(frame_client) -> None:
    client, source_file, _ = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])

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
            return_value=(50 * 1024**3, 49 * 1024**3, 1),
        ),
    ):
        response = client.post(f"/api/jobs/{job['id']}/start")

    payload = assert_error_response(
        response,
        status_code=409,
        error="job_preflight_failed",
        message="Job preflight checks failed.",
    )
    assert payload["details"]["checks"]["free_disk_space_ok"] is False


def test_worker_extracts_frames_and_updates_progress(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    process_holder: dict[str, FakePopen] = {}
    popen_kwargs: dict[str, object] = {}

    def popen_factory(command, **kwargs):
        popen_kwargs.update(kwargs)
        process = FakePopen(
            command,
            lines=["frame=1\n", "progress=continue\n", "frame=3\n", "progress=end\n"],
            returncode=0,
            frames_to_create=3,
        )
        process_holder["process"] = process
        return process

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_factory),
        patch("app.workers.job_runner.enhance_frames_for_job"),
        patch("app.workers.job_runner.encode_video_for_job"),
        patch("app.workers.job_runner.mux_audio_for_job"),
        patch("app.workers.job_runner.create_final_export_for_job", return_value=None),
    ):
        process_job_skeleton_sync(job["id"], settings)

    assert popen_kwargs["encoding"] == "utf-8"
    assert popen_kwargs["errors"] == "replace"
    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    frames_response = client.get(f"/api/jobs/{job['id']}/frames")
    summary_response = client.get(f"/api/jobs/{job['id']}/frame-extraction")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")

    assert process_holder["process"].terminated is False
    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "running"
    assert progress_response.json()["current_stage"] == "extracting_frames"
    assert progress_response.json()["progress_percent"] == 25.0
    assert progress_response.json()["frames_processed"] == 3
    assert progress_response.json()["extracted_frames"] == 3
    assert progress_response.json()["working_dir"] is not None
    assert progress_response.json()["original_frames_dir"] is not None
    assert frames_response.status_code == 200
    assert frames_response.json()["total"] == 3
    assert len(frames_response.json()["items"]) == 3
    assert summary_response.status_code == 200
    assert summary_response.json()["frame_file_pattern"] == "frame_%08d.png"
    assert summary_response.json()["frame_format"] == "png"
    assert summary_response.json()["extracted_frames"] == 3
    assert summary_response.json()["extraction_started_at"] is not None
    assert summary_response.json()["extraction_completed_at"] is not None
    assert logs_response.status_code == 200
    messages = [item["message"] for item in logs_response.json()["items"]]
    assert "Job picked by worker." in messages
    assert "Job workspace prepared." in messages
    assert "Frame extraction started." in messages
    assert "Frame extraction completed." in messages


def test_worker_marks_job_failed_when_ffmpeg_returns_error(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    def popen_factory(command, **kwargs):
        return FakePopen(
            command,
            lines=["frame=1\n", "progress=continue\n"],
            returncode=1,
            stderr_text="ffmpeg failed",
        )

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_factory),
        patch("app.workers.job_runner.enhance_frames_for_job"),
        patch("app.workers.job_runner.encode_video_for_job"),
    ):
        process_job_skeleton_sync(job["id"], settings)

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")

    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "failed"
    assert progress_response.json()["current_stage"] == "failed"
    assert progress_response.json()["error_code"] == "frame_extraction_failed"
    assert progress_response.json()["error_message"] == "ffmpeg failed"
    assert any(
        item["message"] == "Frame extraction failed: ffmpeg failed"
        for item in logs_response.json()["items"]
    )


def test_worker_marks_job_failed_when_unexpected_exception_occurs(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    decode_error = UnicodeDecodeError(
        "cp932",
        b"\xef",
        0,
        1,
        "illegal multibyte sequence",
    )

    with patch("app.workers.job_runner.extract_frames_for_job", side_effect=decode_error):
        process_job_skeleton_sync(job["id"], settings)

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")

    assert progress_response.status_code == 200
    payload = progress_response.json()
    assert payload["status"] == "failed"
    assert payload["current_stage"] == "failed"
    assert payload["error_code"] == "unknown_error"
    assert payload["error_message"].startswith("Unexpected worker error: UnicodeDecodeError")
    assert any(
        item["message"].startswith("Unexpected worker error: UnicodeDecodeError")
        for item in logs_response.json()["items"]
    )


def test_worker_terminates_ffmpeg_when_job_is_cancelled(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    process_holder: dict[str, FakePopen] = {}
    original_update_job = job_repository.update_job
    cancel_injected = False

    def popen_factory(command, **kwargs):
        process = FakePopen(
            command,
            lines=["frame=1\n", "progress=continue\n", "frame=2\n"],
            returncode=0,
            frames_to_create=2,
        )
        process_holder["process"] = process
        return process

    def update_job_with_cancellation(db, job_obj, data):
        nonlocal cancel_injected
        if "frames_processed" in data and not cancel_injected:
            cancel_injected = True
            data = {
                **data,
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancel_requested": True,
            }
        return original_update_job(db, job_obj, data)

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_factory),
        patch(
            "app.services.frame_extraction_service.job_repository.update_job",
            side_effect=update_job_with_cancellation,
        ),
        patch("app.workers.job_runner.enhance_frames_for_job"),
        patch("app.workers.job_runner.encode_video_for_job"),
        patch("app.workers.job_runner.mux_audio_for_job"),
        patch("app.workers.job_runner.create_final_export_for_job"),
    ):
        process_job_skeleton_sync(job["id"], settings)

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")

    assert process_holder["process"].terminated is True
    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "cancelled"
    assert progress_response.json()["current_stage"] == "cancelled"
    assert any(
        item["message"] == "Frame extraction cancelled by user."
        for item in logs_response.json()["items"]
    )


def test_cancel_from_api_that_kills_ffmpeg_leaves_job_cancelled(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    class KilledStdout:
        """The API cancel kills ffmpeg: stdout just ends and the exit code is non-zero."""

        def __iter__(self):
            response = client.post(f"/api/jobs/{job['id']}/cancel")
            assert response.status_code == 200
            yield from ()

    def popen_factory(command, **kwargs):
        process = FakePopen(command, returncode=1, stderr_text="Exiting normally, received signal")
        process.stdout = KilledStdout()
        return process

    enhance_mock = patch("app.workers.job_runner.enhance_frames_for_job")
    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_factory),
        enhance_mock as enhance,
    ):
        process_job_skeleton_sync(job["id"], settings)

    payload = client.get(f"/api/jobs/{job['id']}/progress").json()
    assert payload["status"] == "cancelled"
    assert payload["error_code"] is None
    assert not enhance.called


def test_shutdown_killing_ffmpeg_leaves_job_for_startup_recovery(frame_client) -> None:
    from app.services import process_registry_service

    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    class ShutdownStdout:
        def __iter__(self):
            process_registry_service.request_shutdown()
            yield from ()

    def popen_factory(command, **kwargs):
        process = FakePopen(command, returncode=1, stderr_text="killed")
        process.stdout = ShutdownStdout()
        return process

    try:
        with (
            patch(
                "app.services.frame_extraction_service.shutil.which",
                return_value="C:/ffmpeg.exe",
            ),
            patch(
                "app.services.frame_extraction_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch(
                "app.services.frame_extraction_service.subprocess.Popen",
                side_effect=popen_factory,
            ),
            patch("app.workers.job_runner.enhance_frames_for_job") as enhance,
        ):
            process_job_skeleton_sync(job["id"], settings)
    finally:
        process_registry_service.clear_shutdown()

    payload = client.get(f"/api/jobs/{job['id']}/progress").json()
    assert payload["status"] == "running"
    assert payload["error_code"] is None
    assert not enhance.called


def test_worker_marks_job_failed_when_stage_raises_without_marking_it(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    with (
        patch("app.workers.job_runner.extract_frames_for_job"),
        patch(
            "app.workers.job_runner.enhance_frames_for_job",
            side_effect=RealESRGANModelLoadFailedError(),
        ),
    ):
        process_job_skeleton_sync(job["id"], settings)

    payload = client.get(f"/api/jobs/{job['id']}/progress").json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == "realesrgan_model_load_failed"
    assert client.get(f"/api/projects/{project['id']}").json()["project"]["status"] == (
        "failed"
    )


def test_worker_skips_job_paused_while_queued(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])
    assert client.post(f"/api/jobs/{job['id']}/pause").status_code == 200

    with patch("app.workers.job_runner.extract_frames_for_job") as extract:
        process_job_skeleton_sync(job["id"], settings)

    assert not extract.called
    assert client.get(f"/api/jobs/{job['id']}/progress").json()["status"] == "paused"


def test_worker_does_not_rerun_a_job_dequeued_twice(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    with (
        patch("app.workers.job_runner.extract_frames_for_job") as extract,
        patch("app.workers.job_runner.enhance_frames_for_job"),
        patch("app.workers.job_runner.encode_video_for_job"),
        patch("app.workers.job_runner.mux_audio_for_job"),
        patch("app.workers.job_runner.create_final_export_for_job"),
        patch("app.workers.job_runner.cleanup_job_temp_after_success"),
    ):
        process_job_skeleton_sync(job["id"], settings)
        process_job_skeleton_sync(job["id"], settings)

    assert extract.call_count == 1
    assert client.get(f"/api/jobs/{job['id']}/progress").json()["status"] == "completed"


def test_pause_returns_409_during_frame_extraction(frame_client) -> None:
    client, source_file, _ = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _update_job(job["id"], status="running", current_stage="extracting_frames")

    response = client.post(f"/api/jobs/{job['id']}/pause")

    assert_error_response(
        response,
        status_code=409,
        error="job_pause_not_supported",
        message="Pausing during processing is not supported yet. Cancel the job instead.",
    )


def test_delete_job_frames_cleans_up_extracted_files(frame_client) -> None:
    client, source_file, settings = frame_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    def popen_factory(command, **kwargs):
        return FakePopen(
            command,
            lines=["frame=2\n", "progress=end\n"],
            returncode=0,
            frames_to_create=2,
        )

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_factory),
        patch("app.workers.job_runner.enhance_frames_for_job"),
        patch("app.workers.job_runner.encode_video_for_job"),
        patch("app.workers.job_runner.mux_audio_for_job"),
        patch("app.workers.job_runner.create_final_export_for_job"),
    ):
        process_job_skeleton_sync(job["id"], settings)

    summary_before = client.get(f"/api/jobs/{job['id']}/frame-extraction")

    assert summary_before.status_code == 200
    original_frames_dir = summary_before.json()["original_frames_dir"]
    assert original_frames_dir is not None
    assert Path(original_frames_dir).exists()
    _update_job(job["id"], status="completed", current_stage="completed")

    delete_response = client.delete(f"/api/jobs/{job['id']}/frames")
    summary_after = client.get(f"/api/jobs/{job['id']}/frame-extraction")
    frames_response = client.get(f"/api/jobs/{job['id']}/frames")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "job_id": job["id"]}
    assert summary_after.status_code == 200
    assert summary_after.json()["original_frames_dir"] is None
    assert summary_after.json()["enhanced_frames_dir"] is None
    assert summary_after.json()["extracted_frames"] == 0
    assert not Path(original_frames_dir).exists()
    assert frames_response.status_code == 404
