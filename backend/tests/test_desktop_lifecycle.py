from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

from app.api import routes_system
from app.core.config import Settings
from app.main import create_app
from app.services import job_recovery_service


def _client(tmp_path: Path, instance_id: str | None) -> TestClient:
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'desktop.sqlite').as_posix()}",
        oroya_instance_id=instance_id,
    )
    return TestClient(create_app(settings))


def test_health_reports_the_instance_started_by_the_desktop_app(tmp_path) -> None:
    with _client(tmp_path, "instance-123") as client:
        payload = client.get("/api/v1/health").json()

    assert payload["instance_id"] == "instance-123"


def test_shutdown_requires_the_matching_instance_header(tmp_path, monkeypatch) -> None:
    requested: list[bool] = []
    monkeypatch.setattr(
        routes_system, "request_shutdown_in_background", lambda: requested.append(True)
    )

    with _client(tmp_path, "instance-123") as client:
        missing = client.post("/api/v1/system/shutdown")
        wrong = client.post("/api/v1/system/shutdown", headers={"X-Oroya-Instance": "other"})
        accepted = client.post(
            "/api/v1/system/shutdown", headers={"X-Oroya-Instance": "instance-123"}
        )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert accepted.status_code == 202
    assert requested == [True]


def test_shutdown_is_not_available_outside_the_desktop_app(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(routes_system, "request_shutdown_in_background", pytest.fail)

    with _client(tmp_path, None) as client:
        response = client.post("/api/v1/system/shutdown", headers={"X-Oroya-Instance": "x"})

    assert response.status_code == 404
    assert response.json()["error"] == "shutdown_not_available"


class _FakeProcess:
    def __init__(self, name: str) -> None:
        self._name = name
        self.terminated = False

    def name(self) -> str:
        return self._name

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> None:
        return None


def test_recovery_only_terminates_orphan_ffmpeg_processes(monkeypatch) -> None:
    processes = {1: _FakeProcess("ffmpeg.exe"), 2: _FakeProcess("chrome.exe")}

    def fake_process(pid: int):
        if pid not in processes:
            raise psutil.NoSuchProcess(pid)
        return processes[pid]

    monkeypatch.setattr(job_recovery_service.psutil, "Process", fake_process)

    assert job_recovery_service.terminate_orphan_process(1) is True
    # El PID guardado ahora es de otro programa: no se toca.
    assert job_recovery_service.terminate_orphan_process(2) is False
    assert job_recovery_service.terminate_orphan_process(3) is False
    assert job_recovery_service.terminate_orphan_process(None) is False
    assert processes[1].terminated and not processes[2].terminated


def test_foreign_host_is_rejected_to_block_dns_rebinding(tmp_path) -> None:
    with _client(tmp_path, None) as client:
        rebinding = client.get("/api/v1/health", headers={"Host": "evil.example:8001"})
        loopback = client.get("/api/v1/health", headers={"Host": "127.0.0.1:51234"})

    assert rebinding.status_code == 403
    assert rebinding.json()["error"] == "forbidden_host"
    assert loopback.status_code == 200


def test_state_changes_from_foreign_origins_are_rejected(tmp_path) -> None:
    with _client(tmp_path, None) as client:
        foreign = client.post(
            "/api/v1/system/ffmpeg/download", headers={"Origin": "https://evil.example"}
        )
        no_origin_cross_site = client.post(
            "/api/v1/system/ffmpeg/download", headers={"Sec-Fetch-Site": "cross-site"}
        )
        # Las lecturas no cambian nada y el navegador ya oculta la respuesta (CORS).
        foreign_read = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
        own_ui = client.post("/api/v1/system/shutdown", headers={"Origin": "http://localhost:4200"})

    assert foreign.status_code == 403
    assert foreign.json()["error"] == "forbidden_origin"
    assert no_origin_cross_site.status_code == 403
    assert foreign_read.status_code == 200
    # Pasa el filtro de origen (llega al endpoint, que responde 404 fuera de escritorio).
    assert own_ui.status_code == 404
