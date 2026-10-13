import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.enhancers.rife_interpolator import (
    InterpolationSchedule,
    resolve_output_fps,
    source_fps_fraction,
)
from app.enhancers.stream import Frame, InterpolationStage
from app.main import create_app
from app.services.export_service import _export_label
from app.services.streaming_pipeline_service import SEGMENTS_DIR_NAME, list_completed_segments
from app.workers.job_runner import process_job_skeleton_sync
from tests.test_frame_extraction import _update_job
from tests.test_projects import _create_project, _import_video
from tests.test_streaming_pipeline import (
    CLIP_FPS,
    CLIP_SECONDS,
    _duration,
    _interrupt_at,
    _job,
    _queued_job,
    needs_ffmpeg,
    stream_client,  # noqa: F401 - fixture
)

# --- Calendario de fotogramas -------------------------------------------------------------------


def test_24_to_60_fps_places_frames_at_the_right_timesteps() -> None:
    schedule = InterpolationSchedule(Fraction(24), Fraction(60))

    assert schedule.timesteps(0) == [0.0, 0.4, 0.8]
    assert schedule.timesteps(1) == [pytest.approx(0.2), pytest.approx(0.6)]
    # 2,5 fotogramas de salida por cada uno de entrada: 24 → 60 exactos.
    assert sum(len(schedule.timesteps(i)) for i in range(24)) == 60
    assert schedule.total_outputs(24) == 60


def test_double_rate_inserts_one_frame_in_the_middle() -> None:
    schedule = InterpolationSchedule(Fraction(25), resolve_output_fps(25.0, "2x"))

    assert [schedule.timesteps(i) for i in range(3)] == [[0.0, 0.5]] * 3


def test_ntsc_rates_are_exact_fractions() -> None:
    assert source_fps_fraction(23.976) == Fraction(24000, 1001)
    assert source_fps_fraction(29.97) == Fraction(30000, 1001)
    assert source_fps_fraction(25.0) == Fraction(25)
    assert resolve_output_fps(23.976, "2x") == Fraction(48000, 1001)
    assert resolve_output_fps(23.976, 60) == Fraction(60)
    with pytest.raises(ValueError):
        InterpolationSchedule(Fraction(60), Fraction(50))


# --- Etapa de interpolación ---------------------------------------------------------------------


class _BlendInterpolator:
    """Stand-in for RIFE: each in-between frame is labelled with its pair and timestep."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, bytes, list[float]]] = []

    def interpolate(self, first: Frame, second: Frame, timesteps: list[float]) -> list[Frame]:
        self.calls.append((first.data, second.data, timesteps))
        return [Frame(f"{first.data.decode()}~{t:g}".encode(), 1, 1) for t in timesteps]


def _frame(label: str) -> Frame:
    return Frame(label.encode(), 1, 1)


def test_stage_completes_each_frame_when_the_next_arrives() -> None:
    interpolator = _BlendInterpolator()
    stage = InterpolationStage(
        interpolator, InterpolationSchedule(Fraction(24), Fraction(60)), lambda a, b: False
    )

    assert stage.push(0, _frame("a")) == (None, [])
    completed, frames = stage.push(1, _frame("b"))
    assert completed == 0
    assert [frame.data for frame in frames] == [b"a", b"a~0.4", b"a~0.8"]
    completed, frames = stage.push(2, _frame("c"))
    assert completed == 1
    assert [frame.data for frame in frames] == [b"b~0.2", b"b~0.6"]
    # El último no tiene siguiente: se repite.
    completed, frames = stage.flush()
    assert completed == 2
    assert [frame.data for frame in frames] == [b"c", b"c", b"c"]
    assert stage.flush() == (None, [])


def test_scene_changes_repeat_the_previous_frame_instead_of_blending() -> None:
    interpolator = _BlendInterpolator()
    stage = InterpolationStage(
        interpolator, InterpolationSchedule(Fraction(25), Fraction(50)), lambda a, b: True
    )

    stage.push(0, _frame("a"))
    _, frames = stage.push(1, _frame("b"))

    assert [frame.data for frame in frames] == [b"a", b"a"]
    assert interpolator.calls == []
    assert stage.scene_changes == 1


def test_scene_change_detection_compares_small_gray_frames() -> None:
    np = pytest.importorskip("numpy")
    from app.enhancers.rife_interpolator import is_scene_change

    dark = np.zeros((72, 128, 3), dtype=np.uint8)
    darker_noise = dark.copy()
    darker_noise[::7, ::5] = 30
    bright = np.full((72, 128, 3), 220, dtype=np.uint8)

    def as_frame(pixels) -> Frame:
        return Frame(pixels.tobytes(), 128, 72)

    assert not is_scene_change(as_frame(dark), as_frame(darker_noise))
    assert is_scene_change(as_frame(dark), as_frame(bright))


# --- Pipeline por streaming con interpolación -------------------------------------------------


class _RepeatInterpolator:
    """Real-sized stand-in for RIFE (no torch in CI): repeats the first frame."""

    def load_model(self) -> None:
        pass

    def interpolate(self, first: Frame, second: Frame, timesteps: list[float]) -> list[Frame]:
        return [first for _ in timesteps]


def _fake_stage(db, job, settings, source_fps):
    from app.services.interpolation_service import resolve_job_output_fps

    output_fps = resolve_job_output_fps(job, source_fps)
    if output_fps is None:
        return None, None
    schedule = InterpolationSchedule(source_fps_fraction(source_fps), output_fps)
    return InterpolationStage(_RepeatInterpolator(), schedule, lambda a, b: False), output_fps


def _frame_count(path: Path) -> int:
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1",
         str(path)],
        capture_output=True, check=True, text=True,
    ).stdout  # fmt: skip
    return int(output.strip())


@needs_ffmpeg
def test_streaming_doubles_the_frame_rate_and_keeps_the_duration(stream_client) -> None:  # noqa: F811
    client, clip, settings = stream_client
    job_id = _queued_job(client, clip)
    _set_interpolation(job_id, "2x")

    with patch("app.services.streaming_pipeline_service.build_interpolation_stage", _fake_stage):
        process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    assert job.encoding_fps == pytest.approx(2 * CLIP_FPS)
    export = Path(job.final_export_path)
    assert _frame_count(export) == 2 * CLIP_FPS * CLIP_SECONDS
    assert abs(_duration(export) - CLIP_SECONDS) < 0.15
    assert export.name == "clip (Oroya 2x 20fps).mp4"


@needs_ffmpeg
def test_interpolated_job_resumes_without_losing_or_repeating_frames(stream_client) -> None:  # noqa: F811
    client, clip, settings = stream_client
    settings.mock_enhancer_frame_delay_ms = 40
    job_id = _queued_job(client, clip)
    _set_interpolation(job_id, "2x")

    with (
        patch("app.services.streaming_pipeline_service.build_interpolation_stage", _fake_stage),
        patch("app.enhancers.stream.PassthroughProcessor._job_id", job_id, create=True),
    ):
        with _interrupt_at(9, pause_requested=True):
            process_job_skeleton_sync(job_id, settings)
        assert _job(job_id).status == "paused"
        _update_job(job_id, status="queued", pause_requested=False)
        process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    segments_dir = Path(job.encoded_dir) / SEGMENTS_DIR_NAME
    assert list_completed_segments(segments_dir)[-1].end_frame == CLIP_FPS * CLIP_SECONDS
    assert _frame_count(Path(job.final_export_path)) == 2 * CLIP_FPS * CLIP_SECONDS


def _set_interpolation(job_id: str, target) -> None:
    import json

    job = _job(job_id)
    config = json.loads(job.enhancement_config_json)
    config["interpolation"] = {"enabled": True, "target_fps": target}
    _update_job(job_id, enhancement_config_json=json.dumps(config))


# --- Validación y preflight ---------------------------------------------------------------------


def test_interpolation_settings_are_validated_against_the_video(tmp_path) -> None:
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake-video-content")
    settings = Settings(
        storage_path=str(tmp_path / "storage"),
        database_url=f"sqlite:///{(tmp_path / 'rife.sqlite').as_posix()}",
    )
    with TestClient(create_app(settings)) as client:
        project_id = _create_project(client, _import_video(client, source)["id"])["project"]["id"]

        def patch_interpolation(value):
            return client.patch(
                f"/api/v1/projects/{project_id}",
                json={"enhancement_config": {"interpolation": value}},
            )

        # El video de prueba es de 23,976 fps.
        not_higher = patch_interpolation({"enabled": True, "target_fps": 24})
        unknown = patch_interpolation({"enabled": True, "target_fps": 120})
        bad_shape = patch_interpolation({"on": True})
        valid = patch_interpolation({"enabled": True, "target_fps": 60})
        double = patch_interpolation({"enabled": True, "target_fps": "2x"})

    assert not_higher.status_code == 400
    assert unknown.status_code == 400
    assert bad_shape.status_code == 400
    assert valid.status_code == 200
    assert double.json()["project"]["enhancement_config"]["interpolation"]["target_fps"] == "2x"


def test_export_name_shows_the_real_frame_rate() -> None:
    job = SimpleNamespace(
        enhancement_config_json='{"scale": "2x", "interpolation": {"enabled": true, '
        '"target_fps": "2x"}}',
        encoding_fps=47.952,
    )

    assert _export_label(job) == "Oroya 2x 48fps"


# --- Modelo real (solo con torch y los pesos disponibles) ------------------------------------


def _rife_weights() -> Path | None:
    candidates = [
        os.environ.get("OROYA_RIFE_WEIGHTS"),
        str(Path(__file__).parents[1] / "storage" / "models" / "rife" / "flownet_v4.25.pkl"),
    ]
    return next((Path(c) for c in candidates if c and Path(c).is_file()), None)


def test_real_rife_model_interpolates_between_two_frames() -> None:
    torch = pytest.importorskip("torch")
    np = pytest.importorskip("numpy")
    weights = _rife_weights()
    if weights is None:
        pytest.skip("RIFE weights not available (set OROYA_RIFE_WEIGHTS)")
    from app.enhancers.rife_interpolator import RIFEInterpolator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    interpolator = RIFEInterpolator(model_path=weights, device=device, half_precision=True)
    # Un cuadro claro que se desplaza 16 px a la derecha.
    first = np.zeros((96, 160, 3), dtype=np.uint8)
    second = np.zeros((96, 160, 3), dtype=np.uint8)
    first[32:64, 40:72] = 230
    second[32:64, 56:88] = 230

    (middle,) = interpolator.interpolate(
        Frame(first.tobytes(), 160, 96), Frame(second.tobytes(), 160, 96), [0.5]
    )

    pixels = np.frombuffer(middle.data, dtype=np.uint8).reshape(96, 160, 3)
    columns = np.nonzero(pixels[48, :, 0] > 128)[0]
    # A mitad de camino el cuadro está hacia x = 48..80 (centro ~64).
    assert abs(columns.mean() - 63.5) < 4


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg no disponible")
def test_stage_requires_the_model_when_interpolation_is_on(stream_client) -> None:  # noqa: F811
    client, clip, settings = stream_client
    job_id = _queued_job(client, clip)
    _set_interpolation(job_id, 60)

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "failed"
    assert job.error_code == "frame_interpolation_not_available"
