import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.workers.job_runner import process_job_skeleton_sync
from app.workers.queue import PRIORITY_PREVIEW, JobQueue
from tests.helpers import patch_job_preflight_ready
from tests.test_streaming_pipeline import _job, needs_ffmpeg, stream_client  # noqa: F401


def test_previews_go_ahead_of_waiting_exports() -> None:
    async def order() -> list[str]:
        queue = JobQueue()
        await queue.enqueue("export-1")
        await queue.enqueue("export-2")
        await queue.enqueue("preview", priority=PRIORITY_PREVIEW)
        return [await queue.dequeue() for _ in range(3)]

    assert asyncio.run(order()) == ["preview", "export-1", "export-2"]


def _project(client, clip: Path) -> str:
    video = client.post(
        "/api/videos/import", json={"file_path": str(clip), "source_mode": "reference"}
    ).json()["video"]
    return client.post(
        "/api/projects", json={"name": "clip.mp4", "video_asset_id": video["id"]}
    ).json()["project"]["id"]


def _request_preview(client, project_id: str, start: float = 1.0) -> str:
    with (
        patch_job_preflight_ready(),
        patch("app.services.preview_clip_service.job_queue.enqueue", new_callable=AsyncMock),
    ):
        response = client.post(
            f"/api/v1/projects/{project_id}/preview-clip",
            json={"start_seconds": start, "duration_seconds": 1},
        )
    assert response.status_code == 202, response.text
    return response.json()["job"]["id"]


def _duration(path: bytes, tmp: Path) -> float:
    target = tmp / "clip.mp4"
    target.write_bytes(path)
    output = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(target)],
        capture_output=True, check=True, text=True,
    ).stdout  # fmt: skip
    return float(output.strip())


@needs_ffmpeg
def test_motion_preview_is_processed_and_served(stream_client, tmp_path) -> None:  # noqa: F811
    client, clip, settings = stream_client
    project_id = _project(client, clip)
    job_id = _request_preview(client, project_id)

    # Mientras espera no aparece en la cola ni como último trabajo del proyecto.
    assert client.get("/api/v1/queue").json()["total"] == 0
    assert client.get(f"/api/v1/projects/{project_id}/workspace").json()["latest_job"] is None

    process_job_skeleton_sync(job_id, settings)

    job = _job(job_id)
    assert job.status == "completed", job.error_message
    assert job.final_export_path is None  # sin exportación
    enhanced = client.get(f"/api/v1/jobs/{job_id}/preview-clip/enhanced")
    original = client.get(f"/api/v1/jobs/{job_id}/preview-clip/original")
    assert enhanced.status_code == original.status_code == 200
    assert enhanced.headers["content-type"] == "video/mp4"
    assert abs(_duration(enhanced.content, tmp_path) - 1) < 0.15
    assert abs(_duration(original.content, tmp_path) - 1) < 0.15
    assert client.get("/api/v1/exports").json()["total"] == 0

    # Una nueva vista previa sustituye a la anterior (y borra sus archivos).
    second = _request_preview(client, project_id, start=0.5)
    assert _job(job_id) is None
    assert _job(second) is not None
    assert not Path(job.working_dir).exists()


@needs_ffmpeg
def test_unknown_preview_variants_are_rejected(stream_client) -> None:  # noqa: F811
    client, _, _ = stream_client
    assert client.get("/api/v1/jobs/missing/preview-clip/enhanced").status_code == 404
