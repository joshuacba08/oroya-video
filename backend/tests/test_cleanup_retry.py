import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import cleanup_service


def test_locked_files_are_retried_before_failing(tmp_path: Path) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_00000001.png").write_bytes(b"png")
    real_rmtree = shutil.rmtree
    attempts = []

    def rmtree(path, *args, **kwargs):
        attempts.append(path)
        if len(attempts) < 3:
            raise PermissionError("[WinError 32] in use")
        return real_rmtree(path, *args, **kwargs)

    deleted: list[str] = []
    with (
        patch.object(cleanup_service.shutil, "rmtree", rmtree),
        patch.object(cleanup_service.time, "sleep"),
    ):
        freed = cleanup_service._delete_path_if_requested(
            frames, enabled=True, deleted_paths=deleted
        )

    assert len(attempts) == 3
    assert freed == 3
    assert deleted == [str(frames)]
    assert not frames.exists()


def test_a_file_that_stays_locked_still_fails(tmp_path: Path) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    with (
        patch.object(cleanup_service.shutil, "rmtree", side_effect=PermissionError("locked")),
        patch.object(cleanup_service.time, "sleep"),
        pytest.raises(PermissionError),
    ):
        cleanup_service._delete_path_if_requested(frames, enabled=True, deleted_paths=[])
