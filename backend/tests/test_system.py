from fastapi.testclient import TestClient

from app.main import app


def test_system_info_endpoint_returns_expected_sections() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/info")

    assert response.status_code == 200
    payload = response.json()
    assert "os" in payload
    assert "python" in payload
    assert "memory" in payload


def test_system_tools_endpoint_returns_expected_sections() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/tools")

    assert response.status_code == 200
    payload = response.json()
    assert "ffmpeg" in payload
    assert "ffprobe" in payload
    assert "nvidia_smi" in payload


def test_system_gpu_endpoint_returns_expected_sections() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/gpu")

    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "gpus" in payload


def test_system_storage_endpoint_returns_expected_sections() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/storage")

    assert response.status_code == 200
    payload = response.json()
    assert "paths" in payload
    assert "disk" in payload


def test_system_requirements_endpoint_returns_expected_sections() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/requirements")

    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "minimum" in payload
    assert "recommended" in payload
    assert "warnings" in payload
