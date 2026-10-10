from fastapi.testclient import TestClient

from app.core.paths import get_logs_path
from app.main import app


def test_health_endpoint_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "Oroya Video Backend"


def test_version_endpoint_returns_configured_version() -> None:
    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"
    assert response.json()["environment"] == "development"


def test_startup_creates_log_file() -> None:
    with TestClient(app):
        log_path = get_logs_path() / "backend.log"

    assert log_path.exists()
