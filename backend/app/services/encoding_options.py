"""Video encoder choice for exports (REQ-040): codec, quality, GPU encoding and 10-bit.

`export_config.encoding = {codec, quality, hardware, ten_bit}`. The same arguments are used
for every streaming segment (so `concat -c copy` keeps working) and by the classic encoder.
"""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass

CODECS = ("h264", "h265")
QUALITIES = ("high", "balanced", "small")
DEFAULT_QUALITY = "high"
# CRF de x264/x265 y CQ de NVENC por calidad (más bajo = más calidad y más tamaño).
SOFTWARE_CRF = {"high": 16, "balanced": 20, "small": 24}
NVENC_CQ = {"high": 18, "balanced": 22, "small": 26}
SOFTWARE_ENCODERS = {"h264": "libx264", "h265": "libx265"}
NVENC_ENCODERS = {"h264": "h264_nvenc", "h265": "hevc_nvenc"}


@dataclass(frozen=True, slots=True)
class EncodingChoice:
    codec: str = "h264"
    quality: str = DEFAULT_QUALITY
    hardware: bool = False
    ten_bit: bool = False

    @property
    def uses_ten_bit(self) -> bool:
        # 10 bits solo en H.265: H.264 High 10 casi no se reproduce en ningún sitio.
        return self.ten_bit and self.codec == "h265"


def resolve_encoding(export_config: dict) -> EncodingChoice:
    encoding = export_config.get("encoding")
    encoding = encoding if isinstance(encoding, dict) else {}
    codec = encoding.get("codec") or export_config.get("codec") or "h264"
    quality = encoding.get("quality")
    return EncodingChoice(
        codec=codec if codec in CODECS else "h264",
        quality=quality if quality in QUALITIES else DEFAULT_QUALITY,
        hardware=encoding.get("hardware") is True,
        ten_bit=encoding.get("ten_bit") is True,
    )


@dataclass(frozen=True, slots=True)
class EncoderArgs:
    args: list[str]
    pix_fmt: str
    encoder: str
    hardware: bool


# NVENC rechaza fotogramas pequeños ("Frame Dimension less than the minimum"): por debajo de
# esto se codifica en la CPU.
HARDWARE_MIN_WIDTH = 256
HARDWARE_MIN_HEIGHT = 144


def hardware_fits(width: int | None, height: int | None) -> bool:
    return bool(width and height) and width >= HARDWARE_MIN_WIDTH and height >= HARDWARE_MIN_HEIGHT


def build_video_codec_args(choice: EncodingChoice, hardware_available: bool) -> EncoderArgs:
    """ffmpeg output arguments (codec, quality, pixel format, tag) for the choice."""
    use_hardware = choice.hardware and hardware_available
    ten_bit = choice.uses_ten_bit
    if use_hardware:
        encoder = NVENC_ENCODERS[choice.codec]
        pix_fmt = "p010le" if ten_bit else "yuv420p"
        args = ["-c:v", encoder, "-preset", "p5", "-tune", "hq", "-rc", "vbr"]
        args += ["-cq", str(NVENC_CQ[choice.quality]), "-b:v", "0"]
    else:
        encoder = SOFTWARE_ENCODERS[choice.codec]
        pix_fmt = "yuv420p10le" if ten_bit else "yuv420p"
        args = ["-c:v", encoder, "-preset", "medium", "-crf", str(SOFTWARE_CRF[choice.quality])]
        # Hilos limitados (REQ-042): con todos los núcleos, x264/x265 dejaba sin CPU al lanzador
        # de kernels de la IA (433 → 303 ms por fotograma con RealPLKSR) y el codificador sigue
        # yendo muy por delante de la IA.
        threads = encoder_threads()
        if choice.codec == "h265":
            args += ["-x265-params", f"log-level=error:pools={threads}"]
        else:
            args += ["-threads", str(threads)]
    if choice.codec == "h265":
        # "hvc1": la etiqueta que esperan Windows y Apple para HEVC en MP4.
        args += ["-tag:v", "hvc1"]
    return EncoderArgs([*args, "-pix_fmt", pix_fmt], pix_fmt, encoder, use_hardware)


def encoder_threads() -> int:
    return max(2, (os.cpu_count() or 8) // 4)


_hardware_cache: dict[str, dict[str, bool]] = {}
_hardware_lock = threading.Lock()


def detect_hardware_encoders(ffmpeg_path: str | None) -> dict[str, bool]:
    """Which NVENC encoders really work here: one test frame each, cached per ffmpeg.

    Being listed by `ffmpeg -encoders` is not enough (no NVIDIA GPU, old driver…).
    """
    if not ffmpeg_path:
        return dict.fromkeys(CODECS, False)
    with _hardware_lock:
        cached = _hardware_cache.get(ffmpeg_path)
        if cached is not None:
            return dict(cached)
    result: dict[str, bool] = {}
    for codec, encoder in NVENC_ENCODERS.items():
        command = [
            ffmpeg_path,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=256x256:d=0.1",
            "-frames:v",
            "1",
            "-c:v",
            encoder,
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=30, check=False)
            result[codec] = completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            result[codec] = False
    with _hardware_lock:
        _hardware_cache[ffmpeg_path] = result
    return dict(result)


def clear_hardware_cache() -> None:
    with _hardware_lock:
        _hardware_cache.clear()
