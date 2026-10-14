"""Colour handling for decode (YUV → RGB) and encode (RGB → YUV) (REQ-038).

Without explicit settings, swscale converts RGB → YUV with the BT.601 matrix and the output
is untagged; players then decode an HD output as BT.709 and the tones shift (skin turns
warmer, reds and greens drift). The app now decodes with the source's own matrix and range,
and always encodes HD-style BT.709, tagged, limited range.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Nombres de ffprobe → nombres de la opción in_color_matrix del filtro scale.
_MATRIX_BY_COLOR_SPACE = {
    "bt709": "bt709",
    "smpte170m": "bt601",
    "bt470bg": "bt601",
    "fcc": "fcc",
    "smpte240m": "smpte240m",
    "bt2020nc": "bt2020",
    "bt2020c": "bt2020",
}
# Por debajo de esta altura, un video sin etiquetar es SD (BT.601); por encima, HD (BT.709).
HD_MIN_HEIGHT = 720

OUTPUT_COLOR_ARGS = [
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
]


@dataclass(frozen=True, slots=True)
class SourceColor:
    matrix: str = "bt601"
    full_range: bool = False

    @property
    def range_name(self) -> str:
        return "pc" if self.full_range else "tv"


def source_color_from_tags(
    color_space: str | None, color_range: str | None, height: int | None
) -> SourceColor:
    matrix = _MATRIX_BY_COLOR_SPACE.get((color_space or "").lower())
    if matrix is None:
        matrix = "bt709" if (height or 0) >= HD_MIN_HEIGHT else "bt601"
    return SourceColor(matrix=matrix, full_range=(color_range or "").lower() in {"pc", "jpeg"})


def probe_source_color(
    ffprobe_path: str | None, input_path: Path, height: int | None
) -> SourceColor:
    """Matrix and range of the first video stream; SD/HD defaults when untagged or unknown."""
    if not ffprobe_path:
        return source_color_from_tags(None, None, height)
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=color_space,color_range,height",
        "-of",
        "json",
        str(input_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        stream = (json.loads(result.stdout or "{}").get("streams") or [{}])[0]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        stream = {}
    return source_color_from_tags(
        stream.get("color_space"), stream.get("color_range"), stream.get("height") or height
    )


def source_color_for_video(
    video_asset, input_path: Path, ffprobe_path: str | None = None, *, probe: bool = True
) -> SourceColor:
    """Colour of an imported video: from its stored tags, or probed when they are missing."""
    height = getattr(video_asset, "height", None)
    color_space = getattr(video_asset, "color_space", None)
    if color_space or not probe:
        return source_color_from_tags(
            color_space, getattr(video_asset, "color_range", None), height
        )
    return probe_source_color(ffprobe_path, input_path, height)


def decode_color_filter(source: SourceColor) -> str:
    """YUV → RGB with the source's matrix and range (last filter of the decoder)."""
    return f"scale=in_color_matrix={source.matrix}:in_range={source.range_name}"


def encode_color_filter(pix_fmt: str = "yuv420p") -> str:
    """RGB → YUV with BT.709, limited range (last filter of the encoder).

    `setparams` tags the frames themselves: recent ffmpeg takes primaries and transfer from
    the frames, not from the -color_* options, and they would end up "unknown".
    """
    return f"scale=out_color_matrix=bt709:out_range=tv,format={pix_fmt},{BT709_FRAME_PARAMS}"


BT709_FRAME_PARAMS = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
