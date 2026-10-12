import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.paths import get_job_export_path, get_job_working_path
from app.db import database
from app.db.repositories import job_repository
from app.main import create_app
from app.services.cleanup_service import start_startup_temp_cleanup
from tests.test_projects import _create_project, _import_video


@pytest.fixture
def cleanup_env(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'cleanup.sqlite').as_posix()}",
        debug=True,
    )
    with TestClient(create_app(settings)) as client:
        yield client, source_file, settings


def _create_job_with_files(client: TestClient, project_id: str, settings: Settings) -> str:
    job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]
    working = get_job_working_path(job_id, settings)
    (working / "frames").mkdir(parents=True)
    (working / "frames" / "frame_00000000.png").write_bytes(b"png")
    export_dir = get_job_export_path(project_id, job_id, settings)
    export_dir.mkdir(parents=True)
    (export_dir / "out.mp4").write_bytes(b"mp4")
    return job_id


def _set_status(job_id: str, status: str) -> None:
    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job_repository.update_job(db, job_repository.get_job_by_id(db, job_id), {"status": status})
        db.commit()
    finally:
        db.close()


def test_delete_job_removes_temp_and_export_files(cleanup_env) -> None:
    client, source_file, settings = cleanup_env
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    job_id = _create_job_with_files(client, project_id, settings)

    assert client.delete(f"/api/jobs/{job_id}").status_code == 200

    assert not get_job_working_path(job_id, settings).exists()
    assert not get_job_export_path(project_id, job_id, settings).exists()


def test_delete_project_removes_files_of_all_its_jobs(cleanup_env) -> None:
    client, source_file, settings = cleanup_env
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    job_ids = [_create_job_with_files(client, project_id, settings) for _ in range(2)]

    assert client.delete(f"/api/projects/{project_id}").status_code == 200

    for job_id in job_ids:
        assert not get_job_working_path(job_id, settings).exists()
        assert not get_job_export_path(project_id, job_id, settings).exists()
    assert source_file.exists()


def test_temp_cleanup_skips_paused_jobs(cleanup_env) -> None:
    client, source_file, settings = cleanup_env
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    paused_job = _create_job_with_files(client, project_id, settings)
    failed_job = _create_job_with_files(client, project_id, settings)
    _set_status(paused_job, "paused")
    _set_status(failed_job, "failed")

    response = client.post("/api/v1/system/cleanup/temp", json={"older_than_hours": 0})

    assert response.status_code == 200
    assert get_job_working_path(paused_job, settings).exists()
    assert not get_job_working_path(failed_job, settings).exists()


def test_startup_cleanup_applies_temp_max_age_but_keeps_interrupted_jobs(cleanup_env) -> None:
    client, source_file, settings = cleanup_env
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    old_job = _create_job_with_files(client, project_id, settings)
    interrupted_job = _create_job_with_files(client, project_id, settings)
    recent_job = _create_job_with_files(client, project_id, settings)
    _set_status(old_job, "completed")
    _set_status(interrupted_job, "interrupted")
    _set_status(recent_job, "completed")
    old = time.time() - (settings.cleanup_temp_older_than_hours + 1) * 3600
    for job_id in (old_job, interrupted_job):
        os.utime(get_job_working_path(job_id, settings), (old, old))

    start_startup_temp_cleanup(settings).join(timeout=10)

    assert not get_job_working_path(old_job, settings).exists()
    assert get_job_working_path(interrupted_job, settings).exists()
    assert get_job_working_path(recent_job, settings).exists()
    # Las exportaciones no son temporales.
    assert get_job_export_path(project_id, old_job, settings).exists()


def test_workspace_opens_when_preview_frames_were_deleted(cleanup_env) -> None:
    client, source_file, settings = cleanup_env
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]
    missing_dir = get_job_working_path(job_id, settings) / "frames"
    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job_repository.update_job(
            db,
            job_repository.get_job_by_id(db, job_id),
            {
                "status": "completed",
                "original_frames_dir": str(missing_dir / "original"),
                "enhanced_frames_dir": str(missing_dir / "enhanced"),
                "enhanced_frames": 10,
            },
        )
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/projects/{project_id}/workspace")

    assert response.status_code == 200
    assert response.json()["preview"]["available"] is False


def test_originals_are_trimmed_right_after_enhancement(cleanup_env) -> None:
    from app.core.paths import get_job_original_frames_path
    from app.services.cleanup_service import trim_original_frames_after_enhancement

    client, source_file, settings = cleanup_env
    project_id = _create_project(client, _import_video(client, source_file)["id"])["project"]["id"]
    job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]
    originals = get_job_original_frames_path(job_id, settings)
    originals.mkdir(parents=True)
    for index in range(30):
        (originals / f"frame_{index:08d}.png").write_bytes(b"png")

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        trim_original_frames_after_enhancement(db, job_id, settings)
    finally:
        db.close()

    kept = sorted(path.name for path in originals.iterdir())
    assert len(kept) == settings.cleanup_keep_preview_frames
    assert kept[0] == "frame_00000000.png"


def test_originals_are_kept_when_cleanup_on_success_is_disabled(tmp_path: Path) -> None:
    from app.services.cleanup_service import trim_original_frames_after_enhancement

    settings = Settings(storage_path=str(tmp_path / "s"), cleanup_temp_on_success=False)
    assert trim_original_frames_after_enhancement(None, "any-job", settings) == 0  # type: ignore[arg-type]
