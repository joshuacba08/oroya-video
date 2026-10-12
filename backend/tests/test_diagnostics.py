import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes_system
from app.core.config import Settings
from app.core.paths import get_logs_path
from app.main import create_app
from app.middleware.access_log import _is_polling
from app.services import audit_log_service


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'diag.sqlite').as_posix()}",
    )


def test_diagnostics_bundle_has_logs_system_and_jobs_without_the_home_path(
    tmp_path, _no_desktop_open
) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        logs_dir = get_logs_path(settings)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "backend-process.log").write_text(
            f"Traceback in {Path.home() / 'Videos' / 'clip.mp4'}", encoding="utf-8"
        )
        response = client.post("/api/v1/system/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"].startswith("oroya-diagnostico-")
    assert ("reveal", payload["path"]) in _no_desktop_open
    with zipfile.ZipFile(payload["path"]) as archive:
        names = set(archive.namelist())
        system = json.loads(archive.read("system.json"))
        process_log = archive.read("logs/backend-process.log").decode("utf-8")
    assert {"system.json", "jobs.json", "logs/backend-process.log"} <= names
    assert system["app"]["version"]
    assert system["database"]["integrity"] == "ok"
    assert str(Path.home()) not in process_log
    assert "~" in process_log


def test_client_errors_are_logged_with_a_rate_limit(tmp_path, monkeypatch) -> None:
    recorded: list[tuple] = []
    monkeypatch.setattr(routes_system, "CLIENT_LOG_LIMIT", 2)
    monkeypatch.setattr(routes_system.frontend_logger, "error", lambda *args: recorded.append(args))
    routes_system._client_log_times.clear()
    with TestClient(create_app(_settings(tmp_path))) as client:
        statuses = [
            client.post(
                "/api/v1/system/client-log",
                json={"message": f"boom {index}", "url": "/projects"},
            ).status_code
            for index in range(4)
        ]

    assert statuses == [204, 204, 204, 204]
    assert len(recorded) == 2
    assert "boom 0" in recorded[0]
    routes_system._client_log_times.clear()


def test_logs_folder_can_be_opened(tmp_path, _no_desktop_open) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/system/storage/open", params={"target": "logs"})

    assert response.status_code == 200
    assert response.json()["path"] == str(get_logs_path(settings))


def test_polling_requests_are_not_logged_at_info_level() -> None:
    assert _is_polling("GET", "/api/v1/queue")
    assert _is_polling("GET", "/api/v1/jobs/abc/progress")
    assert not _is_polling("POST", "/api/v1/queue")
    assert not _is_polling("GET", "/api/v1/projects")


def test_audit_log_rotates_when_it_grows_too_large(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(audit_log_service, "AUDIT_LOG_MAX_BYTES", 100)
    for index in range(5):
        audit_log_service.record_audit_event(
            "job_started", "job", f"job-{index}", "x" * 40, settings=settings
        )

    audit_path = audit_log_service.get_audit_log_file_path(settings)
    assert audit_path.with_name(f"{audit_path.name}.1").exists()
    assert audit_path.stat().st_size < 300
