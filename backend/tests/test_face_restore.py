import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.paths import get_job_working_path
from app.db import database
from app.db.repositories import job_repository
from app.main import create_app
from app.services import download_service, face_restore_service
from tests.test_projects import _create_project, _import_video


@pytest.fixture
def face_env(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'faces.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        yield client, source_file, settings


def _project(client: TestClient, source_file: Path, face_restore: dict | None) -> str:
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    if face_restore is not None:
        response = client.patch(
            f"/api/v1/projects/{project_id}",
            json={"enhancement_config": {"face_restore": face_restore}},
        )
        assert response.status_code == 200, response.text
    return project_id


def _running_job_with_enhanced_frames(client, project_id: str, settings: Settings, frames: int):
    job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]
    enhanced = get_job_working_path(job_id, settings) / "frames" / "enhanced"
    enhanced.mkdir(parents=True)
    for index in range(frames):
        (enhanced / f"frame_{index:08d}.png").write_bytes(b"enhanced")
    db = database.SessionLocal()
    try:
        job = job_repository.get_job_by_id(db, job_id)
        job_repository.update_job(
            db,
            job,
            {
                "status": "running",
                "current_stage": "enhancing_frames",
                "enhanced_frames_dir": str(enhanced),
            },
        )
        db.commit()
    finally:
        db.close()
    return job_id, enhanced


class FakeRestorer:
    """Writes 'restored' frames; optionally triggers a stop after N frames."""

    def __init__(self, stop_after: int | None = None, **kwargs) -> None:
        self.kwargs = kwargs
        self.stop_after = stop_after
        self.processed_frames = 0
        self.faces_restored = 0
        self.average_frame_time_ms = 7

    def restore_frames(self, input_dir, output_dir, progress_callback, stop_callback):
        frames = sorted(input_dir.glob("*.png"))
        output_dir.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames, start=1):
            if self.stop_after is not None and index > self.stop_after:
                break
            (output_dir / frame.name).write_bytes(b"restored")
            self.processed_frames = index
            self.faces_restored += 1
            progress_callback(index, len(frames))
        return self.processed_frames


def _run_restore(settings: Settings, job_id: str, restorer: FakeRestorer, model_path: Path):
    db = database.SessionLocal()
    try:
        with (
            patch.object(face_restore_service, "GFPGANFaceRestorer", return_value=restorer),
            patch.object(
                face_restore_service, "get_face_restore_model_path", return_value=model_path
            ),
            patch.object(face_restore_service, "resolve_ai_device", return_value="cuda"),
        ):
            return face_restore_service.restore_faces_for_job(db, job_id, settings)
    finally:
        db.close()


def test_face_restore_config_is_validated(face_env) -> None:
    client, source_file, _ = face_env
    project_id = _project(client, source_file, {"enabled": True, "strength": 0.7})

    invalid = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"enhancement_config": {"face_restore": {"enabled": True, "strength": 2}}},
    )
    project = client.get(f"/api/v1/projects/{project_id}").json()["project"]

    assert invalid.status_code == 400
    assert project["enhancement_config"]["face_restore"] == {"enabled": True, "strength": 0.7}


def test_restore_replaces_enhanced_frames_only_when_complete(face_env, tmp_path: Path) -> None:
    client, source_file, settings = face_env
    project_id = _project(client, source_file, {"enabled": True, "strength": 0.6})
    job_id, enhanced = _running_job_with_enhanced_frames(client, project_id, settings, 3)
    restorer = FakeRestorer()

    _run_restore(settings, job_id, restorer, tmp_path / "gfpgan.pth")

    assert {path.read_bytes() for path in enhanced.iterdir()} == {b"restored"}
    assert not (enhanced.parent / "faces").exists()
    assert client.get(f"/api/jobs/{job_id}/progress").json()["progress_percent"] == 66.0
    logs = client.get(f"/api/jobs/{job_id}/logs").json()["items"]
    assert any(
        "Face restoration completed: 3 faces in 3 frames" in item["message"] for item in logs
    )


def test_cancelled_restore_leaves_enhanced_frames_untouched(face_env, tmp_path: Path) -> None:
    client, source_file, settings = face_env
    project_id = _project(client, source_file, {"enabled": True, "strength": 0.5})
    job_id, enhanced = _running_job_with_enhanced_frames(client, project_id, settings, 4)

    def cancel_midway(*_args) -> None:
        db = database.SessionLocal()
        try:
            job = job_repository.get_job_by_id(db, job_id)
            job_repository.update_job(db, job, {"status": "cancelled", "cancel_requested": True})
            db.commit()
        finally:
            db.close()

    restorer = FakeRestorer(stop_after=2)
    with patch.object(face_restore_service, "DB_SYNC_INTERVAL_SECONDS", 0):
        cancel_midway()
        _run_restore(settings, job_id, restorer, tmp_path / "gfpgan.pth")

    assert {path.read_bytes() for path in enhanced.iterdir()} == {b"enhanced"}


def test_restore_is_skipped_when_disabled(face_env, tmp_path: Path) -> None:
    client, source_file, settings = face_env
    project_id = _project(client, source_file, None)
    job_id, enhanced = _running_job_with_enhanced_frames(client, project_id, settings, 2)

    with patch.object(face_restore_service, "GFPGANFaceRestorer") as restorer_cls:
        db = database.SessionLocal()
        try:
            face_restore_service.restore_faces_for_job(db, job_id, settings)
        finally:
            db.close()

    assert not restorer_cls.called
    assert {path.read_bytes() for path in enhanced.iterdir()} == {b"enhanced"}


def test_missing_gfpgan_model_fails_job_with_clear_error(face_env) -> None:
    client, source_file, settings = face_env
    project_id = _project(client, source_file, {"enabled": True, "strength": 0.5})
    job_id, _ = _running_job_with_enhanced_frames(client, project_id, settings, 1)

    db = database.SessionLocal()
    try:
        with pytest.raises(face_restore_service.FaceRestoreNotAvailableError):
            face_restore_service.restore_faces_for_job(db, job_id, settings)
    finally:
        db.close()

    progress = client.get(f"/api/jobs/{job_id}/progress").json()
    assert progress["status"] == "failed"
    assert progress["error_code"] == "face_restore_not_available"


def test_gfpgan_counts_as_installed_only_with_facexlib_weights(face_env) -> None:
    client, _, settings = face_env
    models_dir = Path(settings.storage_path) / "models"
    (models_dir / "gfpgan").mkdir(parents=True)
    (models_dir / "gfpgan" / "GFPGANv1.4.pth").write_bytes(b"w")

    def gfpgan_installed() -> bool:
        client.post("/api/v1/models/refresh")
        items = client.get("/api/v1/models").json()["items"]
        return next(item for item in items if item["slug"] == "gfpgan-v1.4")["is_installed"]

    assert gfpgan_installed() is False
    (models_dir / "facexlib").mkdir()
    (models_dir / "facexlib" / "detection_Resnet50_Final.pth").write_bytes(b"d")
    (models_dir / "facexlib" / "parsing_parsenet.pth").write_bytes(b"p")
    assert gfpgan_installed() is True


class _InlineThread(download_service.threading.Thread):
    def start(self) -> None:  # type: ignore[override]
        self.run()


class _FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()


def test_gfpgan_download_fetches_facexlib_weights_too(face_env) -> None:
    client, _, settings = face_env
    payloads = {
        "https://example.test/gfpgan.pth": b"gfpgan",
        "https://example.test/det.pth": b"detection",
        "https://example.test/parse.pth": b"parsing",
    }

    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    source = {
        "url": "https://example.test/gfpgan.pth",
        "sha256": digest(payloads["https://example.test/gfpgan.pth"]),
        "extra_files": [
            {
                "path": "facexlib/detection_Resnet50_Final.pth",
                "url": "https://example.test/det.pth",
                "sha256": digest(b"detection"),
            },
            {
                "path": "facexlib/parsing_parsenet.pth",
                "url": "https://example.test/parse.pth",
                "sha256": digest(b"parsing"),
            },
        ],
    }
    with (
        patch.object(download_service.threading, "Thread", _InlineThread),
        patch.object(
            download_service.urllib.request,
            "urlopen",
            side_effect=lambda request, timeout: _FakeResponse(payloads[request.full_url]),
        ),
        patch.dict(
            "app.services.model_download_service.MODEL_DOWNLOAD_SOURCES",
            {"gfpgan-v1.4": source},
            clear=True,
        ),
    ):
        client.post("/api/v1/models/gfpgan-v1.4/download")
        progress = client.get("/api/v1/models/gfpgan-v1.4/download/progress").json()

    download_service.reset_download_state("model:gfpgan-v1.4")
    models_dir = Path(settings.storage_path) / "models"
    assert progress["status"] == "completed"
    assert (models_dir / "facexlib" / "parsing_parsenet.pth").read_bytes() == b"parsing"
    items = client.get("/api/v1/models").json()["items"]
    gfpgan = next(item for item in items if item["slug"] == "gfpgan-v1.4")
    assert gfpgan["is_installed"] is True
    assert json.dumps(gfpgan["metadata"]).count("facexlib") == 2
