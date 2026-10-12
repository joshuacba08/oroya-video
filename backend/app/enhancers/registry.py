from __future__ import annotations

from pathlib import Path

from app.core.errors import FrameEnhancerNotFoundError
from app.enhancers.base import FrameEnhancer
from app.enhancers.mock_enhancer import MockFrameEnhancer
from app.enhancers.realesrgan_enhancer import RealESRGANFrameEnhancer


def get_frame_enhancer(engine: str, **kwargs) -> FrameEnhancer:
    normalized_engine = engine.strip().lower()
    if normalized_engine == "mock":
        return MockFrameEnhancer(kwargs.get("frame_delay_ms", 0) / 1000)
    if normalized_engine == "realesrgan":
        return RealESRGANFrameEnhancer(
            model_path=Path(kwargs.get("model_path", "__missing_realesrgan_model__.pth")),
            model_slug=kwargs.get("model_slug", "realesrgan-x2"),
            device=kwargs.get("device", "cpu"),
            scale=kwargs.get("scale"),
            tile_size=kwargs.get("tile_size", 0),
            tile_pad=kwargs.get("tile_pad", 10),
            pre_pad=kwargs.get("pre_pad", 0),
            half_precision=kwargs.get("half_precision", False),
            max_failed_frames=kwargs.get("max_failed_frames", 0),
            clear_cuda_cache=kwargs.get("clear_cuda_cache", True),
        )
    raise FrameEnhancerNotFoundError()
