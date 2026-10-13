import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.enhancers.realesrgan_enhancer import RealESRGANFrameEnhancer
from app.main import create_app
from tests.test_projects import _create_project, _import_video


def test_quality_controls_are_validated(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'quality.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]

        def patch_config(**values):
            return client.patch(
                f"/api/v1/projects/{project_id}", json={"enhancement_config": values}
            )

        too_high = patch_config(ai_strength=120)
        not_int = patch_config(model_denoise=0.5)
        valid = patch_config(ai_strength=70, model_denoise=30)

    assert too_high.status_code == 400
    assert not_int.status_code == 400
    assert valid.status_code == 200
    config = valid.json()["project"]["enhancement_config"]
    assert (config["ai_strength"], config["model_denoise"]) == (70, 30)


def test_ai_strength_blends_with_a_plain_upscale() -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from app.enhancers.stream import blend_with_plain_upscale

    source = np.zeros((4, 4, 3), dtype=np.uint8)
    enhanced = np.full((8, 8, 3), 200, dtype=np.uint8)

    blended = blend_with_plain_upscale(source, enhanced, 0.7)

    assert blended.shape == (8, 8, 3)
    assert int(blended.mean()) == 140


def _fake_realesrgan_modules(captured: dict) -> dict:
    class FakeRealESRGANer:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    modules = {
        "cv2": types.ModuleType("cv2"),
        "basicsr": types.ModuleType("basicsr"),
        "basicsr.archs": types.ModuleType("basicsr.archs"),
        "basicsr.archs.rrdbnet_arch": types.SimpleNamespace(RRDBNet=lambda **_: object()),
        "realesrgan": types.SimpleNamespace(RealESRGANer=FakeRealESRGANer),
        "realesrgan.archs": types.ModuleType("realesrgan.archs"),
        "realesrgan.archs.srvgg_arch": types.SimpleNamespace(SRVGGNetCompact=lambda **_: object()),
    }
    return modules


@pytest.mark.parametrize(("strength", "mixed"), [(0.3, True), (1.0, False), (None, False)])
def test_general_model_mixes_its_denoise_variant(tmp_path: Path, strength, mixed) -> None:
    base = tmp_path / "realesrgan-general.pth"
    wdn = tmp_path / "realesr-general-wdn-x4v3.pth"
    base.write_bytes(b"x")
    wdn.write_bytes(b"x")
    captured: dict = {}
    enhancer = RealESRGANFrameEnhancer(
        model_path=base,
        model_slug="realesrgan-general",
        device="cpu",
        scale=2,
        tile_size=0,
        tile_pad=10,
        pre_pad=0,
        half_precision=False,
        denoise_model_path=wdn,
        denoise_strength=strength,
    )

    with (
        patch.dict(sys.modules, _fake_realesrgan_modules(captured)),
        patch("app.enhancers.realesrgan_enhancer.ensure_torchvision_compat"),
    ):
        enhancer._create_backend()

    if mixed:
        assert captured["model_path"] == [str(base), str(wdn)]
        assert captured["dni_weight"] == pytest.approx([0.3, 0.7])
    else:
        assert captured["model_path"] == str(base)
        assert captured["dni_weight"] is None
