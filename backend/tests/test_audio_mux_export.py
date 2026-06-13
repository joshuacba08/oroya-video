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
from app.services.audio_mux_service import (
    build_audio_aac_mux_command,
    build_audio_copy_mux_command,
    build_no_audio_mux_command,
    mux_audio_for_job,
)
from app.services.export_service import create_final_export_for_job
from app.services.job_workspace_service import prepare_job_workspace


def _build_probe_response(source_path: Path, *, has_audio: bool = True) -> VideoProbeResponse:
    audio_info = AudioStreamInfo(
        available=has_audio,
        codec="aac" if has_audio else None,
        codec_long_name="AAC (Advanced Audio Coding)" if has_audio else None,
        sample_rate=48000 if has_audio else None,
        channels=2 if has_audio else None,
        channel_layout="stereo" if has_audio else None,
        bit_rate=320000 if has_audio else None,
    )
    streams = [StreamSummary(index=0, type="video", codec="h264", width=1920, height=1080)]
    if has_audio:
        streams.append(StreamSummary(index=1, type="audio", codec="aac"))

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
        audio=audio_info,
        streams=streams,
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


@pytest.fixture
def export_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")

    storage_path = tmp_path / "storage"
    db_path = tmp_path / "export.sqlite"
    settings = Settings(
        storage_path=str(storage_path),
        database_url=f"sqlite:///{db_path.as_posix()}",
        debug=True,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        yield client, source_file, settings


def _import_video(client: TestClient, source_file: Path, *, has_audio: bool = True) -> dict:
    with patch(
        "app.services.video_probe_service.probe_video",
        return_value=_build_probe_response(source_file, has_audio=has_audio),
    ):
        response = client.post(
            "/api/videos/import",
            json={"file_path": str(source_file), "source_mode": "reference"},
        )

    assert response.status_code == 201
    return response.json()["video"]


def _create_project(client: TestClient, video_asset_id: str, name: str = "Export Project") -> dict:
    response = client.post(
        "/api/projects",
        json={"name": name, "video_asset_id": video_asset_id},
    )
    assert response.status_code == 201
    return response.json()["project"]


def _create_job(client: TestClient, project_id: str) -> dict:
    response = client.post("/api/jobs", json={"project_id": project_id})
    assert response.status_code == 201
    return response.json()["job"]


def _queue_job(client: TestClient, job_id: str) -> None:
    with (
        patch("app.services.frame_extraction_service.shutil.which", return_value="C:/ffmpeg.exe"),
        patch(
            "app.services.frame_extraction_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ),
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


def _prepare_encoded_video(job_id: str, settings: Settings, *, size_bytes: bytes = b"mp4") -> Path:
    workspace = prepare_job_workspace(job_id, settings)
    encoded_path = workspace["encoded_dir"] / "video_silent.mp4"
    encoded_path.write_bytes(size_bytes)
    _update_job(
        job_id,
        working_dir=str(workspace["working_dir"]),
        original_frames_dir=str(workspace["original_frames_dir"]),
        enhanced_frames_dir=str(workspace["enhanced_frames_dir"]),
        encoded_dir=str(workspace["encoded_dir"]),
        encoded_video_path=str(encoded_path),
        encoded_video_file_name=encoded_path.name,
        encoded_video_size_bytes=len(size_bytes),
        encoding_codec="h264",
        encoding_format="mp4",
        encoding_fps=24.0,
        progress_percent=85.0,
        status="running",
        current_stage="encoding_video",
    )
    return encoded_path


def _prepare_muxed_video(job_id: str, settings: Settings, *, size_bytes: bytes = b"muxed") -> Path:
    workspace = prepare_job_workspace(job_id, settings)
    muxed_path = workspace["muxed_dir"] / "video_with_audio.mp4"
    muxed_path.write_bytes(size_bytes)
    _update_job(
        job_id,
        working_dir=str(workspace["working_dir"]),
        muxed_video_path=str(muxed_path),
        muxed_video_file_name=muxed_path.name,
        muxed_video_size_bytes=len(size_bytes),
        audio_strategy="copy",
        audio_codec="aac",
        progress_percent=97.0,
        status="running",
        current_stage="muxing_audio",
    )
    return muxed_path


def test_build_audio_mux_commands_include_expected_arguments() -> None:
    silent_video_path = Path("C:/temp/job/encoded/video_silent.mp4")
    original_video_path = Path("C:/videos/source.mp4")
    output_path = Path("C:/temp/job/muxed/video_with_audio.mp4")

    copy_command = build_audio_copy_mux_command(silent_video_path, original_video_path, output_path)
    aac_command = build_audio_aac_mux_command(silent_video_path, original_video_path, output_path)
    no_audio_command = build_no_audio_mux_command(silent_video_path, output_path)

    assert copy_command[0] == "ffmpeg"
    assert "-map" in copy_command
    assert "0:v:0" in copy_command
    assert "1:a:0?" in copy_command
    assert copy_command.count("-c:v") == 1
    assert "copy" in copy_command
    assert "-shortest" in copy_command
    assert "+faststart" in copy_command
    assert "aac" in aac_command
    assert "-b:a" in aac_command
    assert "1:a:0?" not in no_audio_command[no_audio_command.index("-map") + 1 :]


def test_mux_audio_for_job_uses_copy_strategy_when_audio_exists(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_encoded_video(job["id"], settings)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.audio_mux_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.audio_mux_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch(
                "app.services.audio_mux_service.subprocess.Popen",
                side_effect=lambda command, **kwargs: FakePopen(
                    command,
                    lines=["progress=continue\n", "progress=end\n"],
                    output_bytes=b"muxed",
                ),
            ),
        ):
            mux_audio_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    response = client.get(f"/api/jobs/{job['id']}/audio-mux")
    muxed_response = client.get(f"/api/jobs/{job['id']}/muxed-video")

    assert response.status_code == 200
    assert response.json()["audio_strategy"] == "copy"
    assert response.json()["muxed_video_path"] is not None
    assert muxed_response.status_code == 200
    assert muxed_response.json()["available"] is True
    assert muxed_response.json()["audio_strategy"] == "copy"


def test_mux_audio_for_job_falls_back_to_aac_when_copy_fails(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_encoded_video(job["id"], settings)

    calls = {"count": 0}

    def popen_factory(command, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakePopen(command, returncode=1, stderr_text="copy failed")
        return FakePopen(
            command,
            lines=["progress=continue\n", "progress=end\n"],
            output_bytes=b"muxed-aac",
        )

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.audio_mux_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.audio_mux_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch("app.services.audio_mux_service.subprocess.Popen", side_effect=popen_factory),
        ):
            mux_audio_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    response = client.get(f"/api/jobs/{job['id']}/audio-mux")
    assert response.status_code == 200
    assert response.json()["audio_strategy"] == "transcode_aac"
    assert response.json()["audio_codec"] == "aac"


def test_mux_audio_for_job_uses_none_strategy_when_video_has_no_audio(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=False)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_encoded_video(job["id"], settings)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch("app.services.audio_mux_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.audio_mux_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch(
                "app.services.audio_mux_service.subprocess.Popen",
                side_effect=lambda command, **kwargs: FakePopen(
                    command,
                    lines=["progress=end\n"],
                    output_bytes=b"muxed-no-audio",
                ),
            ),
        ):
            mux_audio_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    response = client.get(f"/api/jobs/{job['id']}/audio-mux")
    muxed_response = client.get(f"/api/jobs/{job['id']}/muxed-video")
    assert response.status_code == 200
    assert response.json()["audio_strategy"] == "none"
    assert response.json()["audio_codec"] is None
    assert muxed_response.json()["has_audio"] is False


def test_create_final_export_for_job_creates_export_record_and_job_fields(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"], name="Anime Episode 01")
    job = _create_job(client, project["id"])
    _prepare_muxed_video(job["id"], settings)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with patch(
            "app.services.export_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ):
            export_asset = create_final_export_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    assert export_asset is not None
    final_export_response = client.get(f"/api/jobs/{job['id']}/final-export")
    exports_response = client.get("/api/exports")

    assert final_export_response.status_code == 200
    assert final_export_response.json()["export_id"] == export_asset.id
    assert final_export_response.json()["final_export_file_name"].endswith(".mp4")
    assert exports_response.status_code == 200
    assert exports_response.json()["total"] == 1
    assert exports_response.json()["items"][0]["id"] == export_asset.id


def test_export_endpoints_support_detail_delete_open_and_job_summary(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_muxed_video(job["id"], settings)

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with patch(
            "app.services.export_service.shutil.disk_usage",
            return_value=(1000, 100, 900),
        ):
            export_asset = create_final_export_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    detail_response = client.get(f"/api/exports/{export_asset.id}")
    job_summary_response = client.get(f"/api/jobs/{job['id']}/final-export")
    open_response = client.post(f"/api/exports/{export_asset.id}/open")
    open_folder_response = client.post(f"/api/exports/{export_asset.id}/open-folder")
    delete_response = client.delete(f"/api/exports/{export_asset.id}?delete_file=true")
    missing_response = client.get(f"/api/exports/{export_asset.id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == export_asset.id
    assert job_summary_response.status_code == 200
    assert job_summary_response.json()["export_id"] == export_asset.id
    assert open_response.status_code == 200
    assert open_response.json()["available"] is True
    assert open_folder_response.status_code == 200
    assert open_folder_response.json()["available"] is True
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert delete_response.json()["file_deleted"] is True
    assert missing_response.status_code == 404


def test_delete_muxed_video_route_clears_only_muxed_artifact(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_muxed_video(job["id"], settings)
    _update_job(job["id"], status="completed", current_stage="completed")

    response = client.delete(f"/api/jobs/{job['id']}/muxed-video")
    muxed_response = client.get(f"/api/jobs/{job['id']}/muxed-video")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "job_id": job["id"]}
    assert muxed_response.status_code == 200
    assert muxed_response.json()["available"] is False


def test_cancel_during_mux_marks_job_cancelled(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    _prepare_encoded_video(job["id"], settings)

    process_holder: dict[str, FakePopen] = {}
    original_update_job = job_repository.update_job
    cancel_injected = False

    def popen_factory(command, **kwargs):
        process = FakePopen(
            command,
            lines=["progress=continue\n", "progress=end\n"],
            output_bytes=b"partial-muxed",
        )
        process_holder["process"] = process
        return process

    def update_job_with_cancellation(db_session, job_obj, data):
        nonlocal cancel_injected
        if "progress_percent" in data and not cancel_injected:
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
            patch("app.services.audio_mux_service.shutil.which", return_value="C:/ffmpeg.exe"),
            patch(
                "app.services.audio_mux_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch("app.services.audio_mux_service.subprocess.Popen", side_effect=popen_factory),
            patch(
                "app.services.audio_mux_service.job_repository.update_job",
                side_effect=update_job_with_cancellation,
            ),
        ):
            mux_audio_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    assert process_holder["process"].terminated is True
    assert progress_response.json()["status"] == "cancelled"


def test_cancel_during_export_marks_job_cancelled(export_client) -> None:
    client, source_file, settings = export_client
    video = _import_video(client, source_file, has_audio=True)
    project = _create_project(client, video["id"])
    job = _create_job(client, project["id"])
    muxed_path = _prepare_muxed_video(job["id"], settings)

    def copy_with_cancel(source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        assert database.SessionLocal is not None
        db_inner = database.SessionLocal()
        try:
            job_inner = job_repository.get_job_by_id(db_inner, job["id"])
            assert job_inner is not None
            job_inner.cancel_requested = True
            db_inner.commit()
        finally:
            db_inner.close()
        return destination

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        with (
            patch(
                "app.services.export_service.shutil.disk_usage",
                return_value=(1000, 100, 900),
            ),
            patch(
                "app.services.export_service.copy_muxed_video_to_exports",
                side_effect=copy_with_cancel,
            ),
        ):
            create_final_export_for_job(db, job["id"], settings=settings)
    finally:
        db.close()

    progress_response = client.get(f"/api/jobs/{job['id']}/progress")
    assert muxed_path.exists()
    assert progress_response.status_code == 200
    assert progress_response.json()["status"] == "cancelled"
