from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
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
from app.services.job_workspace_service import prepare_job_workspace
from app.services.video_encoding_service import (
    build_enhancement_video_filters,
    build_video_encoding_command,
    encode_video_for_job,
    parse_ffmpeg_encoding_progress_line,
    resolve_encoding_fps,
)
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


class FakeEncodingPopen:
    def __init__(
        self,
        command: list[str],
        *,
        lines: list[str] | None = None,
        returncode: int = 0,
        stderr_text: str = "",
        output_bytes: bytes | None = None,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_bytes is not None:
            output_path.write_bytes(output_bytes)
        self.stdout = FakeStdout(lines or [])
        self.stderr = FakeStderr(stderr_text)

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class FakeExtractionPopen:
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

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


@pytest.fixture
def encoding_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "encoding.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
        # These tests inspect pipeline intermediates after completion.
        cleanup_temp_on_success=False,
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
        json={"name": "Encoding Project", "video_asset_id": video_asset_id},
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


def _prepare_enhanced_frames(job_id: str, settings: Settings, total: int = 2) -> dict:
    workspace = prepare_job_workspace(job_id, settings)
    for index in range(total):
        (workspace["enhanced_frames_dir"] / f"frame_{index:08d}.png").write_bytes(b"png")

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        assert job is not None
        job.working_dir = str(workspace["working_dir"])
        job.original_frames_dir = str(workspace["original_frames_dir"])
        job.enhanced_frames_dir = str(workspace["enhanced_frames_dir"])
        job.frames_total = total
        job.extracted_frames = total
        job.enhanced_frames = total
        db.commit()
    finally:
        db.close()
    return workspace


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


def test_build_video_encoding_command_and_parse_progress() -> None:
    command = build_video_encoding_command(
        Path("C:/temp/job/frames/enhanced/frame_%08d.png"),
        Path("C:/temp/job/encoded/video_silent.mp4"),
        23.976,
    )

    assert command[0] == "ffmpeg"
    assert "-framerate" in command
    assert "-i" in command
    assert "libx264" in command
    assert "yuv420p" in command
    assert "+faststart" in command
    assert "pipe:1" in command
    assert parse_ffmpeg_encoding_progress_line("frame=120") == {"frame": "120"}


def test_build_enhancement_video_filters_returns_none_for_default_config() -> None:
    assert build_enhancement_video_filters({}) is None
    assert (
        build_enhancement_video_filters({"denoise": 0, "sharpen": 0, "compression_cleanup": False})
        is None
    )


def test_build_enhancement_video_filters_maps_slider_values() -> None:
    assert build_enhancement_video_filters({"denoise": 50}) == "hqdn3d=4.00"
    assert build_enhancement_video_filters({"sharpen": 100}) == "unsharp=5:5:1.50"
    assert (
        build_enhancement_video_filters({"compression_cleanup": True})
        == "deblock=filter=strong:block=8"
    )


def test_build_enhancement_video_filters_orders_and_ignores_invalid_values() -> None:
    combined = build_enhancement_video_filters(
        {"denoise": 40, "sharpen": 30, "compression_cleanup": True}
    )
    assert combined == "deblock=filter=strong:block=8,hqdn3d=3.20,unsharp=5:5:0.45"
    assert build_enhancement_video_filters({"denoise": "high", "sharpen": 500}) is None
    assert build_enhancement_video_filters({"denoise": True, "compression_cleanup": 1}) is None


def test_build_output_scale_filter_uses_original_dimensions() -> None:
    from app.services.video_encoding_service import (
        build_output_scale_filter,
        combine_video_filters,
    )

    class Video:
        width = 1920
        height = 1080

    video = Video()
    assert (
        build_output_scale_filter({"output_resolution": "2x"}, video, enhanced_scale=1)
        == "scale=3840:2160:flags=lanczos"
    )
    assert (
        build_output_scale_filter({"output_resolution": "original"}, video, enhanced_scale=2)
        == "scale=1920:1080:flags=lanczos"
    )
    # Sin reescalado cuando la resolución pedida coincide con la escala IA.
    assert build_output_scale_filter({"output_resolution": "2x"}, video, enhanced_scale=2) is None
    assert build_output_scale_filter({}, video, enhanced_scale=1) is None
    assert build_output_scale_filter({"output_resolution": "8x"}, video, enhanced_scale=1) is None

    class NoDims:
        width = None
        height = None

    assert (
        build_output_scale_filter({"output_resolution": "2x"}, NoDims(), enhanced_scale=1) is None
    )
    assert combine_video_filters(None, None) is None
    assert combine_video_filters("hqdn3d=4.00", None, "scale=10:10") == "hqdn3d=4.00,scale=10:10"


def test_build_video_encoding_command_inserts_video_filters_before_codec() -> None:
    command = build_video_encoding_command(
        Path("C:/temp/job/frames/enhanced/frame_%08d.png"),
        Path("C:/temp/job/encoded/video_silent.mp4"),
        30.0,
        video_filters="hqdn3d=4.00",
    )

    assert "-vf" in command
    assert command[command.index("-vf") + 1] == "hqdn3d=4.00"
    assert command.index("-vf") < command.index("-c:v")

    plain_command = build_video_encoding_command(
        Path("C:/temp/job/frames/enhanced/frame_%08d.png"),
        Path("C:/temp/job/encoded/video_silent.mp4"),
        30.0,
    )
    assert "-vf" not in plain_command


def test_resolve_encoding_fps_uses_video_fps_and_fallback() -> None:
    class Video:
        fps = 23.976

    class Job:
        id = "job-1"
        video_asset = Video()

    assert resolve_encoding_fps(Job()) == 23.976

    Job.video_asset.fps = None
    assert resolve_encoding_fps(Job()) == 30.0


def test_encode_video_for_job_fails_when_enhanced_frames_are_missing(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_enhanced_frames(job["id"], settings, total=0)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            pytest.raises(Exception) as excinfo,
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert getattr(excinfo.value, "error_code", None) == "enhanced_frames_required"
    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    assert progress_response.json()["status"] == "failed"


def test_encode_video_for_job_fails_when_ffmpeg_is_missing(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_enhanced_frames(job["id"], settings, total=1)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            pytest.raises(Exception) as excinfo,
            patch("app.services.video_encoding_service.shutil.which", return_value=None),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert getattr(excinfo.value, "error_code", None) == "ffmpeg_not_available"


def test_encode_video_for_job_validates_temp_space(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_enhanced_frames(job["id"], settings, total=1)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            pytest.raises(Exception) as excinfo,
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.video_encoding_service.shutil.disk_usage",
                return_value=(1000, 1000, 0),
            ),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert getattr(excinfo.value, "error_code", None) == "insufficient_temp_storage"


def test_encode_video_for_job_updates_progress_and_output_metadata(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_enhanced_frames(job["id"], settings, total=2)
    popen_kwargs: dict[str, object] = {}

    def popen_factory(command, **kwargs):
        popen_kwargs.update(kwargs)
        return FakeEncodingPopen(
            command,
            lines=["frame=1\n", "progress=continue\n", "frame=2\n", "progress=end\n"],
            returncode=0,
            output_bytes=b"mp4",
        )

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.video_encoding_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.video_encoding_service.subprocess.Popen",
                side_effect=popen_factory,
            ),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert popen_kwargs["encoding"] == "utf-8"
    assert popen_kwargs["errors"] == "replace"
    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    summary_response = client.get(f"/api/jobs/{job['id']}/video-encoding")
    encoded_response = client.get(f"/api/jobs/{job['id']}/encoded-video")

    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "running"
    assert progress_response.json()["current_stage"] == "encoding_video"
    assert progress_response.json()["progress_percent"] == 85.0
    assert progress_response.json()["encoded_video_path"] is not None
    assert summary_response.status_code == 200
    assert summary_response.json()["encoding_started_at"] is not None
    assert summary_response.json()["encoding_completed_at"] is not None
    assert summary_response.json()["encoding_codec"] == "h264"
    assert encoded_response.status_code == 200
    assert encoded_response.json()["available"] is True
    assert encoded_response.json()["size_bytes"] == len(b"mp4")


def test_encode_video_for_job_applies_enhancement_filters(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    response = client.post(
        "/api/jobs",
        json={
            "project_id": project["id"],
            "enhancement_config": {
                "denoise": 40,
                "sharpen": 30,
                "compression_cleanup": True,
            },
        },
    )
    assert response.status_code == 201
    job = response.json()["job"]
    _prepare_enhanced_frames(job["id"], settings, total=2)
    captured_commands: list[list[str]] = []

    def popen_factory(command, **kwargs):
        captured_commands.append(command)
        return FakeEncodingPopen(
            command,
            lines=["frame=2\n", "progress=end\n"],
            returncode=0,
            output_bytes=b"mp4",
        )

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.video_encoding_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.video_encoding_service.subprocess.Popen",
                side_effect=popen_factory,
            ),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert len(captured_commands) == 1
    command = captured_commands[0]
    assert "-vf" in command
    # Limpieza y ruido se aplican al extraer (antes de la IA); aquí nitidez, escala y color.
    assert command[command.index("-vf") + 1] == (
        "unsharp=5:5:0.45,scale=3840:2160:flags=lanczos,crop=trunc(iw/2)*2:trunc(ih/2)*2,"
        "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
    )
    assert command[command.index("-colorspace") + 1] == "bt709"
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")
    messages = [item["message"] for item in logs_response.json()["items"]]
    assert "Encoding filters: unsharp=5:5:0.45,scale=3840:2160:flags=lanczos" in messages
    assert "Filters apply to the final video, not to preview frames." in messages


def test_worker_runs_extraction_enhancement_and_encoding(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    def popen_dispatch(command, **kwargs):
        if "-framerate" in command:
            return FakeEncodingPopen(
                command,
                lines=["frame=1\n", "progress=continue\n", "frame=2\n", "progress=end\n"],
                returncode=0,
                output_bytes=b"mp4",
            )
        if "1:a:0?" in command or str(command[-1]).endswith("video_with_audio.mp4"):
            return FakeEncodingPopen(
                command,
                lines=["progress=continue\n", "progress=end\n"],
                returncode=0,
                output_bytes=b"muxed",
            )
        return FakeExtractionPopen(
            command,
            lines=["frame=1\n", "progress=continue\n", "frame=2\n", "progress=end\n"],
            returncode=0,
            frames_to_create=2,
        )

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch("app.services.audio_mux_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.frame_enhancement_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.video_encoding_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.audio_mux_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.export_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_dispatch),
    ):
        process_job_skeleton_sync(job["id"], settings)

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    logs_response = client.get(f"/api/jobs/{job['id']}/logs")
    enhanced_frames_response = client.get(f"/api/jobs/{job['id']}/enhanced-frames")
    encoded_response = client.get(f"/api/jobs/{job['id']}/encoded-video")
    audio_mux_response = client.get(f"/api/jobs/{job['id']}/audio-mux")
    final_export_response = client.get(f"/api/jobs/{job['id']}/final-export")

    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "completed"
    assert progress_response.json()["progress_percent"] == 100.0
    assert progress_response.json()["enhanced_frames"] == 2
    assert encoded_response.json()["available"] is True
    assert enhanced_frames_response.status_code == 200
    assert audio_mux_response.status_code == 200
    assert audio_mux_response.json()["audio_strategy"] == "copy"
    assert final_export_response.status_code == 200
    assert final_export_response.json()["export_id"] is not None
    messages = [item["message"] for item in logs_response.json()["items"]]
    assert "Frame enhancement completed using mock enhancer." in messages
    assert "Video encoding completed." in messages
    assert "Audio mux completed." in messages
    assert "Final export completed." in messages


def test_worker_cleans_temp_after_success_preserving_preview(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'cleanup.sqlite').as_posix()}",
        debug=True,
        cleanup_temp_on_success=True,
        cleanup_keep_preview_frames=1,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        video = _import_video(client, source_file)
        project = _create_project(client, video["id"])
        job = _create_job(client, project["id"])
        _queue_job(client, job["id"])

        def popen_dispatch(command, **kwargs):
            if "-framerate" in command:
                return FakeEncodingPopen(
                    command,
                    lines=["frame=1\n", "progress=continue\n", "frame=2\n", "progress=end\n"],
                    returncode=0,
                    output_bytes=b"mp4",
                )
            if "1:a:0?" in command or str(command[-1]).endswith("video_with_audio.mp4"):
                return FakeEncodingPopen(
                    command,
                    lines=["progress=continue\n", "progress=end\n"],
                    returncode=0,
                    output_bytes=b"muxed",
                )
            return FakeExtractionPopen(
                command,
                lines=["frame=1\n", "progress=continue\n", "frame=2\n", "progress=end\n"],
                returncode=0,
                frames_to_create=2,
            )

        with (
            patch(
                "app.services.frame_extraction_service.shutil.which",
                return_value="C:/ffmpeg.exe",
            ),
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch("app.services.audio_mux_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.frame_extraction_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.frame_enhancement_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.video_encoding_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.audio_mux_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.export_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.frame_extraction_service.subprocess.Popen",
                side_effect=popen_dispatch,
            ),
        ):
            process_job_skeleton_sync(job["id"], settings)

        progress_response = client.get(f"/api/jobs/{job['id']}/progress")
        assert progress_response.json()["status"] == "completed"

        job_temp_dir = Path(settings.storage_path) / "temp" / "jobs" / job["id"]
        original_frames = sorted((job_temp_dir / "frames" / "original").glob("*.png"))
        enhanced_frames = sorted((job_temp_dir / "frames" / "enhanced").glob("*.png"))
        assert [frame.name for frame in original_frames] == ["frame_00000000.png"]
        assert [frame.name for frame in enhanced_frames] == ["frame_00000000.png"]
        assert not (job_temp_dir / "encoded").exists()
        assert not (job_temp_dir / "muxed").exists()

        preview_response = client.get(f"/api/jobs/{job['id']}/preview")
        assert preview_response.status_code == 200
        assert preview_response.json()["comparable_frames_count"] == 1
        assert preview_response.json()["recommended_frame_index"] == 0
        compare_response = client.get(f"/api/jobs/{job['id']}/preview/compare/0")
        assert compare_response.status_code == 200

        final_export_response = client.get(f"/api/jobs/{job['id']}/final-export")
        assert final_export_response.status_code == 200
        assert final_export_response.json()["export_id"] is not None
        logs_response = client.get(f"/api/jobs/{job['id']}/logs")
        assert any(
            item["message"].startswith("Temp cleanup after success completed.")
            for item in logs_response.json()["items"]
        )


def test_worker_marks_job_failed_when_encoding_fails(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _queue_job(client, job["id"])

    def popen_dispatch(command, **kwargs):
        if "-framerate" in command:
            return FakeEncodingPopen(
                command,
                lines=["frame=1\n", "progress=continue\n"],
                returncode=1,
                stderr_text="encode failed",
            )
        return FakeExtractionPopen(
            command,
            lines=["frame=2\n", "progress=end\n"],
            returncode=0,
            frames_to_create=2,
        )

    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.frame_enhancement_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch(
            "app.services.video_encoding_service.shutil.disk_usage",
            return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        ),
        patch("app.services.frame_extraction_service.subprocess.Popen", side_effect=popen_dispatch),
    ):
        process_job_skeleton_sync(job["id"], settings)

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "failed"
    assert progress_response.json()["error_code"] == "video_encoding_failed"


def test_cancel_during_encoding_marks_job_cancelled(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_enhanced_frames(job["id"], settings, total=3)

    process_holder: dict[str, FakeEncodingPopen] = {}
    original_update_job = job_repository.update_job
    cancel_injected = False

    def popen_factory(command, **kwargs):
        process = FakeEncodingPopen(
            command,
            lines=["frame=1\n", "progress=continue\n", "frame=2\n"],
            returncode=0,
            output_bytes=b"partial",
        )
        process_holder["process"] = process
        return process

    def update_job_with_cancellation(db_session, job_obj, data):
        nonlocal cancel_injected
        if "frames_processed" in data and not cancel_injected:
            cancel_injected = True
            data = {
                **data,
                "status": "cancelled",
                "current_stage": "cancelled",
                "cancel_requested": True,
            }
        return original_update_job(db_session, job_obj, data)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.video_encoding_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.video_encoding_service.subprocess.Popen",
                side_effect=popen_factory,
            ),
            patch(
                "app.services.video_encoding_service.job_repository.update_job",
                side_effect=update_job_with_cancellation,
            ),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    assert process_holder["process"].terminated is True
    assert progress_response.json()["status"] == "cancelled"


def test_delete_encoded_video_keeps_frame_directories(encoding_client) -> None:
    client, source_file, settings = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    workspace = _prepare_enhanced_frames(job["id"], settings, total=2)

    def popen_factory(command, **kwargs):
        return FakeEncodingPopen(
            command,
            lines=["frame=2\n", "progress=end\n"],
            returncode=0,
            output_bytes=b"mp4",
        )

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.video_encoding_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.video_encoding_service.shutil.disk_usage",
                return_value=(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
            ),
            patch(
                "app.services.video_encoding_service.subprocess.Popen",
                side_effect=popen_factory,
            ),
        ):
            encode_video_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    _update_job(job["id"], status="completed", current_stage="completed")
    encoded_before = client.get(f"/api/jobs/{job['id']}/encoded-video")
    delete_response = client.delete(f"/api/jobs/{job['id']}/encoded-video")
    encoded_after = client.get(f"/api/jobs/{job['id']}/encoded-video")

    assert encoded_before.status_code == 200
    assert encoded_before.json()["available"] is True
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "job_id": job["id"]}
    assert workspace["enhanced_frames_dir"].exists()
    assert encoded_after.json()["available"] is False


def test_pause_returns_409_during_encoding(encoding_client) -> None:
    client, source_file, _ = encoding_client
    video = _import_video(client, source_file)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _update_job(job["id"], status="running", current_stage="encoding_video")

    response = client.post(f"/api/jobs/{job['id']}/pause")

    assert_error_response(
        response,
        status_code=409,
        error="job_pause_not_supported",
        message="Pausing during processing is not supported yet. Cancel the job instead.",
    )
