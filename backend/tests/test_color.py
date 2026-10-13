import subprocess
from pathlib import Path

import pytest

from app.services.streaming_pipeline_service import build_decoder_command
from app.utils.color import (
    decode_color_filter,
    encode_color_filter,
    source_color_from_tags,
)
from app.workers.job_runner import process_job_skeleton_sync
from tests.test_streaming_pipeline import (  # noqa: F401
    _job,
    _queued_job,
    needs_ffmpeg,
    stream_client,
)

# Piel, rojo y verde saturados: donde más se nota usar BT.601 en vez de BT.709.
COLORS = {"skin": (200, 140, 110), "red": (200, 30, 40), "green": (40, 180, 60)}


def test_source_tags_map_to_the_decoder_matrix() -> None:
    assert source_color_from_tags("bt709", "tv", 480).matrix == "bt709"
    assert source_color_from_tags("smpte170m", None, 1080).matrix == "bt601"
    # Sin etiqueta: SD → BT.601, HD → BT.709.
    assert source_color_from_tags(None, None, 480).matrix == "bt601"
    assert source_color_from_tags("unknown", None, 1080).matrix == "bt709"
    assert source_color_from_tags("bt709", "pc", 480).full_range
    assert decode_color_filter(source_color_from_tags("bt709", "tv", 480)) == (
        "scale=in_color_matrix=bt709:in_range=tv"
    )
    assert encode_color_filter().startswith(
        "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams="
    )


def test_cleanup_filters_run_in_the_decoder_before_the_ai() -> None:
    command = build_decoder_command(
        Path("in.mp4"),
        25,
        video_filters="deblock=filter=strong:block=8,scale=in_color_matrix=bt601:in_range=tv",
    )

    assert command[command.index("-vf") + 1] == (
        "fps=25,deblock=filter=strong:block=8,scale=in_color_matrix=bt601:in_range=tv"
    )


def _make_color_clip(path: Path) -> Path:
    """Three bars of known RGB colours, encoded as tagged BT.709 like the user's source."""
    bars = "".join(f"[{index}:v]" for index in range(len(COLORS)))  # entradas lavfi, una por color
    inputs: list[str] = []
    for red, green, blue in COLORS.values():
        inputs += [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x{red:02X}{green:02X}{blue:02X}:s=64x96:d=1:r=10",
        ]
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex", f"{bars}hstack=inputs={len(COLORS)},format=gbrp,"
         "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-qp", "0", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv", str(path)],
        check=True,
    )  # fmt: skip
    return path


def _center_colors_as_player(path: Path) -> list[tuple[int, int, int]]:
    """Decode the first frame as a BT.709 player would and sample each bar's centre."""
    output = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
         "-vf", "scale=in_color_matrix=bt709:in_range=tv,format=rgb24",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, check=True, text=True,
    ).stdout.strip()  # fmt: skip
    width, height = (int(value) for value in probe.split(","))
    samples = []
    for index in range(len(COLORS)):
        x = int((index + 0.5) * width / len(COLORS))
        offset = ((height // 2) * width + x) * 3
        samples.append(tuple(output[offset : offset + 3]))
    return samples


@needs_ffmpeg
def test_colours_survive_the_pipeline(stream_client, tmp_path) -> None:  # noqa: F811
    client, _, settings = stream_client
    clip = _make_color_clip(tmp_path / "colors.mp4")
    job_id = _queued_job(client, clip)

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    export = Path(job.final_export_path)
    tags = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=color_space,color_primaries,color_transfer,color_range", "-of", "csv=p=0",
         str(export)],
        capture_output=True, check=True, text=True,
    ).stdout.strip()  # fmt: skip
    assert tags == "tv,bt709,bt709,bt709"
    # Igual que la fuente vista en un reproductor BT.709 (antes la piel se iba ~5 niveles).
    source_colors = _center_colors_as_player(clip)
    for expected, actual in zip(source_colors, _center_colors_as_player(export), strict=True):
        assert max(abs(a - b) for a, b in zip(expected, actual, strict=True)) <= 3, (
            expected,
            actual,
        )


@pytest.mark.parametrize("unused", [None])
def test_color_constants_are_consistent(unused) -> None:
    assert "bt709" in encode_color_filter("yuv420p10le")
