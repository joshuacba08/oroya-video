import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.enhancers.spandrel_enhancer import SpandrelFrameEnhancer
from app.main import create_app
from app.services.ai_model_service import DEFAULT_MODELS
from app.services.model_download_service import MODEL_DOWNLOAD_SOURCES
from tests.test_projects import _create_project, _import_video

SPANDREL_SLUGS = {"realplksr-real-2x", "realplksr-4x", "span-anime-2x", "deh264-1x"}


def test_spandrel_models_are_registered_with_pinned_downloads() -> None:
    models = {model["slug"]: model for model in DEFAULT_MODELS}
    for slug in SPANDREL_SLUGS:
        assert models[slug]["model_type"] == "spandrel"
        assert models[slug]["relative_path"].startswith("spandrel/")
        source = MODEL_DOWNLOAD_SOURCES[slug]
        assert source["url"].startswith("https://github.com/Phhofm/models/releases/download/")
        assert len(source["sha256"]) == 64
    # La limpieza no es un modelo de escalado: no se ofrece como tal en la UI.
    assert models["deh264-1x"]["category"] == "compression_cleanup"


def test_tiled_inference_matches_the_whole_image() -> None:
    torch = pytest.importorskip("torch")
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")

    enhancer = SpandrelFrameEnhancer(
        model_path=Path("unused"),
        model_slug="test",
        device="cpu",
        scale=2,
        half_precision=False,
    )
    # "Modelo" determinista 2x: vecino más cercano. Con solape, los tiles deben coincidir.
    enhancer._model = lambda tensor: torch.nn.functional.interpolate(
        tensor, scale_factor=2, mode="nearest"
    )
    enhancer._torch, enhancer._dtype, enhancer.native_scale = torch, torch.float32, 2
    import cv2

    enhancer._cv2 = cv2
    image = np.random.default_rng(1).integers(0, 255, (70, 90, 3), dtype=np.uint8)

    whole = enhancer.enhance_image(image)
    enhancer.tile_size = 32
    tiled = enhancer.enhance_image(image)

    assert whole.shape == (140, 180, 3)
    assert np.array_equal(whole, tiled)


def test_requested_scale_differs_from_the_model_scale() -> None:
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    enhancer = SpandrelFrameEnhancer(
        model_path=Path("unused"), model_slug="t", device="cpu", scale=2, half_precision=False
    )
    enhancer._cv2, enhancer.native_scale = cv2, 4
    source = np.zeros((10, 20, 3), dtype=np.uint8)
    four_x = np.zeros((40, 80, 3), dtype=np.uint8)

    assert enhancer.resize_to_output(four_x, source=source).shape == (20, 40, 3)


def test_jobs_with_spandrel_models_get_the_spandrel_enhancer(tmp_path) -> None:
    from app.services import realesrgan_service

    model = SimpleNamespace(slug="realplksr-real-2x", model_type="spandrel", scale_factor=2)
    job = SimpleNamespace(
        enhancement_config_json='{"model_id": "realplksr-real-2x", "scale": "2x"}',
        ai_model_slug="realplksr-real-2x",
        working_dir=str(tmp_path),
    )
    settings = Settings(storage_path=str(tmp_path / "storage"))
    with (
        patch.object(realesrgan_service, "_get_model_or_raise", return_value=model),
        patch.object(
            realesrgan_service, "resolve_realesrgan_model_path", return_value=tmp_path / "m.pth"
        ),
        patch.object(realesrgan_service, "_resolve_runtime_device", return_value=("cpu", [], True)),
    ):
        enhancer = realesrgan_service.get_streaming_enhancer(None, job, settings)

    assert isinstance(enhancer, SpandrelFrameEnhancer)
    assert enhancer.scale == 2


def test_ai_cleanup_is_validated(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'sp.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]

        def patch_config(value):
            return client.patch(
                f"/api/v1/projects/{project_id}",
                json={"enhancement_config": {"ai_cleanup": value}},
            )

        assert patch_config({"enabled": "yes"}).status_code == 400
        assert patch_config({"enabled": True}).status_code == 200


def _real_model(name: str) -> Path | None:
    folder = os.environ.get("OROYA_SPANDREL_MODELS")
    path = Path(folder) / name if folder else None
    return path if path and path.is_file() else None


@pytest.mark.parametrize(
    ("file", "scale"),
    [("2xHFA2k_LUDVAE_SPAN.safetensors", 2), ("1xDeH264_realplksr.safetensors", 1)],
)
def test_real_spandrel_models_enhance_a_frame(file, scale) -> None:
    torch = pytest.importorskip("torch")
    np = pytest.importorskip("numpy")
    pytest.importorskip("spandrel")
    path = _real_model(file)
    if path is None:
        pytest.skip("spandrel models not available (set OROYA_SPANDREL_MODELS)")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    enhancer = SpandrelFrameEnhancer(
        model_path=path, model_slug=file, device=device, scale=scale, half_precision=True
    )
    image = np.full((48, 64, 3), 128, dtype=np.uint8)
    image[10:30, 10:40] = (40, 160, 220)

    result = enhancer.enhance_image(image)

    assert result.shape == (48 * scale, 64 * scale, 3)
    # El color se conserva (BGR ↔ RGB bien convertidos).
    center = result[20 * scale, 25 * scale].astype(int)
    assert abs(center[0] - 40) < 25 and abs(center[2] - 220) < 25


def test_preflight_rejects_spandrel_models_in_the_classic_pipeline(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'pf.sqlite').as_posix()}",
        pipeline_mode="legacy",
    )
    with TestClient(create_app(settings)) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]
        job = client.post(
            "/api/jobs",
            json={"project_id": project_id, "enhancement_config": {"model_id": "span-anime-2x"}},
        ).json()["job"]
        preflight = client.get(f"/api/v1/jobs/{job['id']}/preflight").json()

    assert not preflight["ready"]
    assert any("streaming pipeline" in error for error in preflight["errors"])
