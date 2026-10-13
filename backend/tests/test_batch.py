from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.main import create_app
from app.services import job_recovery_service, settings_service
from tests.helpers import patch_job_preflight_ready
from tests.test_jobs import _create_project, _import_video, _update_job


@pytest.fixture
def jobs_client(tmp_path: Path):
    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'batch.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        yield client, source_file, settings


def _queue_batch(client, project_ids: list[str], **configs):
    # El worker no procesa nada en estos tests: solo interesa el orden de la cola.
    with (
        patch_job_preflight_ready(),
        patch("app.workers.job_runner.process_job_skeleton_sync"),
    ):
        return client.post("/api/v1/jobs/batch", json={"project_ids": project_ids, **configs})


def test_batch_queues_projects_in_order_with_the_same_settings(jobs_client) -> None:
    client, source_file, _ = jobs_client
    video = _import_video(client, source_file)
    projects = [_create_project(client, video["id"], name=f"Clip {index}") for index in range(3)]
    project_ids = [project["id"] for project in projects]

    response = _queue_batch(
        client,
        [*project_ids, project_ids[0]],  # un duplicado no se encola dos veces
        enhancement_config={"scale": "4x"},
        export_config={"keep_audio": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["queued_job_ids"]) == 3
    assert payload["skipped"] == []
    jobs = [
        client.get(f"/api/v1/jobs/{job_id}").json()["job"] for job_id in payload["queued_job_ids"]
    ]
    assert [job["project_id"] for job in jobs] == project_ids
    assert all(job["enhancement_config"]["scale"] == "4x" for job in jobs)
    assert all(job["export_config"]["keep_audio"] is False for job in jobs)

    queue = client.get("/api/v1/queue").json()["items"]
    queued = [item for item in queue if item["status"] == "queued"]
    assert [item["job_id"] for item in queued] == payload["queued_job_ids"]
    assert [item["queue_position"] for item in queued] == [1, 2, 3]


def test_batch_skips_projects_that_cannot_be_queued(jobs_client) -> None:
    client, source_file, _ = jobs_client
    project = _create_project(client, _import_video(client, source_file)["id"])

    response = _queue_batch(client, ["missing-project", project["id"]])

    payload = response.json()
    assert len(payload["queued_job_ids"]) == 1
    assert payload["skipped"][0]["project_id"] == "missing-project"
    assert payload["skipped"][0]["error_code"] == "project_not_found"


def test_new_projects_start_from_the_last_batch_settings(jobs_client) -> None:
    client, source_file, settings = jobs_client
    video = _import_video(client, source_file)
    first = _create_project(client, video["id"], name="First")

    _queue_batch(
        client,
        [first["id"]],
        enhancement_config={"scale": "4x"},
        export_config={"keep_audio": False, "file_name": "only for this one"},
    )
    later = _create_project(client, video["id"], name="Later")

    assert later["enhancement_config"]["scale"] == "4x"
    assert later["export_config"]["keep_audio"] is False
    # El nombre de archivo es propio de cada proyecto: no se hereda.
    assert later["export_config"].get("file_name") in (None, "")
    saved = settings_service.get_processing_defaults(settings)
    assert "file_name" not in saved["export_config"]


def test_starting_a_single_video_also_becomes_the_new_default(jobs_client, tmp_path) -> None:
    client, source_file, settings = jobs_client
    video = _import_video(client, source_file)
    first = _create_project(client, video["id"], name="First")
    job = client.post(
        "/api/jobs",
        json={
            "project_id": first["id"],
            "enhancement_config": {"scale": "4x"},
            "export_config": {"keep_audio": False, "output_dir": str(tmp_path / "only-here")},
        },
    ).json()["job"]
    with (
        patch_job_preflight_ready(),
        patch("app.services.job_service.job_queue.enqueue"),
    ):
        assert client.post(f"/api/jobs/{job['id']}/start").status_code == 200

    later = _create_project(client, video["id"], name="Later")

    assert later["enhancement_config"]["scale"] == "4x"
    assert later["export_config"]["keep_audio"] is False
    # La carpeta elegida para un proyecto no se hereda.
    assert later["export_config"].get("output_dir") in (None, "")


def test_waiting_jobs_are_kept_for_the_queue_after_a_restart(jobs_client) -> None:
    client, source_file, settings = jobs_client
    video = _import_video(client, source_file)
    project_ids = [_create_project(client, video["id"], name=f"P{i}")["id"] for i in range(3)]
    job_ids = _queue_batch(client, project_ids).json()["queued_job_ids"]
    _update_job(job_ids[0], status="running")

    assert database.SessionLocal is not None
    db = database.SessionLocal()
    try:
        job_recovery_service.recover_interrupted_jobs_on_startup(db, settings)
        waiting = job_recovery_service.get_waiting_job_ids(db)
    finally:
        db.close()

    # El que estaba en marcha queda interrumpido (reanudable); los que esperaban, en cola.
    assert waiting == job_ids[1:]
    assert client.get(f"/api/v1/jobs/{job_ids[0]}").json()["job"]["status"] == "interrupted"
