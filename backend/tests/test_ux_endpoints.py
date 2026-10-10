import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import database
from app.db.repositories import ai_model_repository
from app.main import create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'ux.sqlite').as_posix()}",
    )


def test_storage_open_reveals_only_known_folders(tmp_path: Path, _no_desktop_open) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post("/api/v1/system/storage/open", params={"target": "exports"})
        invalid = client.post("/api/v1/system/storage/open", params={"target": "../.."})

    assert response.status_code == 200
    assert response.json()["opened"] is True
    assert Path(response.json()["path"]) == (tmp_path / "storage" / "exports").resolve()
    assert _no_desktop_open == [("reveal", response.json()["path"])]
    assert invalid.status_code == 422


def test_models_expose_quality_and_speed_tiers(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        items = client.get("/api/v1/models").json()["items"]

    tiers = {item["slug"]: item["metadata"] for item in items}
    assert tiers["realesrgan-x4"]["quality_tier"] == "very_high"
    assert tiers["realesrgan-general"]["speed_tier"] == "fast"


def test_seed_adds_tiers_to_models_from_older_versions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)):
        db = database.SessionLocal()
        try:
            model = ai_model_repository.get_ai_model_by_slug(db, "realesrgan-x2")
            model.metadata_json = json.dumps({"custom": 1})
            db.commit()
        finally:
            db.close()

    with TestClient(create_app(settings)) as client:
        x2 = next(
            item
            for item in client.get("/api/v1/models").json()["items"]
            if item["slug"] == "realesrgan-x2"
        )

    assert x2["metadata"] == {"custom": 1, "quality_tier": "high", "speed_tier": "medium"}


def test_job_events_stream_sends_progress_and_closes_on_terminal_state(tmp_path: Path) -> None:
    from tests.test_projects import _create_project, _import_video

    source_file = tmp_path / "sample.mp4"
    source_file.write_bytes(b"fake-video-content")
    with TestClient(create_app(_settings(tmp_path))) as client:
        project_id = _create_project(client, _import_video(client, source_file)["id"])["project"][
            "id"
        ]
        job_id = client.post("/api/jobs", json={"project_id": project_id}).json()["job"]["id"]
        db = database.SessionLocal()
        try:
            from app.db.repositories import job_repository

            job = job_repository.get_job_by_id(db, job_id)
            job_repository.update_job(db, job, {"status": "completed", "progress_percent": 100.0})
            db.commit()
        finally:
            db.close()

        with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())

        missing = client.get("/api/v1/jobs/missing-job/events")

    events = [line for line in body.splitlines() if line.startswith("data: ")]
    assert len(events) == 1
    payload = json.loads(events[0].removeprefix("data: "))
    assert payload["job_id"] == job_id
    assert payload["status"] == "completed"
    assert missing.status_code == 404
