from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.errors import CUDAOutOfMemoryError
from app.enhancers.realesrgan_enhancer import RealESRGANFrameEnhancer
from app.services import realesrgan_service


def _enhancer(tile_size: int = 0, device: str = "cuda") -> RealESRGANFrameEnhancer:
    enhancer = RealESRGANFrameEnhancer(
        model_path=Path("model.pth"),
        model_slug="realesrgan-x2",
        device=device,
        scale=2,
        tile_size=tile_size,
        tile_pad=10,
        pre_pad=0,
        half_precision=True,
    )
    enhancer._upsampler = SimpleNamespace(tile_size=tile_size)
    return enhancer


def test_oom_retries_with_smaller_tiles_until_it_fits(tmp_path: Path) -> None:
    enhancer = _enhancer(tile_size=0)
    attempts: list[int] = []

    def fake_enhance(frame, output_path):
        attempts.append(enhancer._upsampler.tile_size)
        if enhancer._upsampler.tile_size != 256:
            raise CUDAOutOfMemoryError()
        return output_path, 10

    with (
        patch.object(enhancer, "enhance_single_frame", side_effect=fake_enhance),
        patch("app.enhancers.realesrgan_enhancer.clear_cuda_cache_if_available"),
    ):
        enhancer._enhance_with_oom_fallback(tmp_path / "f.png", tmp_path / "o.png")

    assert attempts == [0, 512, 256]
    assert enhancer.tile_size == 256
    assert enhancer.tile_fallbacks == 2


def test_oom_is_raised_when_smallest_tile_still_fails(tmp_path: Path) -> None:
    enhancer = _enhancer(tile_size=128)

    with (
        patch.object(enhancer, "enhance_single_frame", side_effect=CUDAOutOfMemoryError()),
        patch("app.enhancers.realesrgan_enhancer.clear_cuda_cache_if_available"),
        pytest.raises(CUDAOutOfMemoryError),
    ):
        enhancer._enhance_with_oom_fallback(tmp_path / "f.png", tmp_path / "o.png")


def test_resumed_frames_do_not_lower_the_average_frame_time(tmp_path: Path) -> None:
    input_dir = tmp_path / "original"
    output_dir = tmp_path / "enhanced"
    input_dir.mkdir()
    output_dir.mkdir()
    for index in range(1, 5):
        (input_dir / f"frame_{index:06d}.png").write_bytes(b"png")
    # Dos frames ya mejorados antes de pausar: se saltan sin tiempo de proceso.
    for index in (1, 2):
        (output_dir / f"frame_{index:06d}.png").write_bytes(b"done")
    enhancer = _enhancer()

    with (
        patch.object(enhancer, "load_model"),
        patch.object(enhancer, "enhance_single_frame", side_effect=lambda frame, out: (out, 100)),
    ):
        enhancer.enhance_frames(input_dir, output_dir)

    assert enhancer.completed_frames == 4
    assert enhancer.timed_frames == 2
    assert enhancer.average_frame_time_ms == 100


def test_oom_on_cpu_is_not_retried(tmp_path: Path) -> None:
    enhancer = _enhancer(tile_size=0, device="cpu")

    with (
        patch.object(enhancer, "enhance_single_frame", side_effect=CUDAOutOfMemoryError()),
        patch("app.enhancers.realesrgan_enhancer.clear_cuda_cache_if_available"),
        pytest.raises(CUDAOutOfMemoryError),
    ):
        enhancer._enhance_with_oom_fallback(tmp_path / "f.png", tmp_path / "o.png")
    assert enhancer.tile_fallbacks == 0


def _context(tmp_path: Path, slug: str = "realesrgan-x2") -> realesrgan_service.RealESRGANContext:
    return realesrgan_service.RealESRGANContext(
        model_slug=slug,
        model_path=tmp_path / f"{slug}.pth",
        device="cuda",
        scale=2,
        tile_size=0,
        tile_pad=10,
        pre_pad=0,
        half_precision=True,
        input_dir=tmp_path / "in",
        output_dir=tmp_path / "out",
        total_frames=10,
    )


def test_loaded_model_is_reused_across_jobs_and_replaced_on_change(tmp_path: Path) -> None:
    settings = Settings()
    with patch.object(realesrgan_service, "clear_cuda_cache_if_available"):
        first = realesrgan_service._get_enhancer(_context(tmp_path), settings)
        first.processed_frames = 42
        again = realesrgan_service._get_enhancer(_context(tmp_path), settings)
        other = realesrgan_service._get_enhancer(_context(tmp_path, "realesrgan-x4"), settings)

    assert again is first
    assert again.processed_frames == 0  # counters reset for the new job
    assert other is not first
    assert len(realesrgan_service._enhancer_cache) == 1


def _job(**fields) -> SimpleNamespace:
    defaults = dict(
        status="running",
        current_stage="enhancing_frames",
        frames_total=1000,
        frames_processed=0,
        realesrgan_frames_total=1000,
        realesrgan_frames_processed=0,
        realesrgan_average_frame_time_ms=None,
        elapsed_time_seconds=0,
        progress_percent=25.0,
    )
    return SimpleNamespace(**{**defaults, **fields})


def test_eta_during_enhancement_uses_average_frame_time() -> None:
    from app.services.job_contract_service import estimate_remaining_seconds

    job = _job(realesrgan_frames_processed=400, realesrgan_average_frame_time_ms=150)

    # 600 frames * 0.15 s + encode guess (1000 / 60 + 3 s of mux).
    assert estimate_remaining_seconds(job) == 90 + 16 + 3


def test_eta_extrapolates_encoding_progress_and_is_none_when_unknown() -> None:
    from app.services.job_contract_service import estimate_remaining_seconds
    from app.services.pipeline_progress import ENCODING_PROGRESS_END, ENCODING_PROGRESS_START

    halfway = (ENCODING_PROGRESS_START + ENCODING_PROGRESS_END) / 2
    encoding = _job(
        current_stage="encoding_video", progress_percent=halfway, elapsed_time_seconds=40
    )
    assert estimate_remaining_seconds(encoding) == 40 + 3

    assert estimate_remaining_seconds(_job(current_stage="extracting_frames")) is None
    assert estimate_remaining_seconds(_job(status="paused")) is None
