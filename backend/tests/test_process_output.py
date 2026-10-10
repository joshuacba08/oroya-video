import subprocess
import sys

from app.utils.process_output import StderrDrain


def test_stderr_drain_prevents_pipe_deadlock_with_large_stderr() -> None:
    # Writes far more than the OS pipe buffer to stderr before finishing stdout.
    script = "import sys\nsys.stderr.write('w' * 1_000_000)\nsys.stderr.flush()\nprint('frame=1')\n"
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        text=True,
    )
    drain = StderrDrain(process.stderr)

    stdout_lines = [line.strip() for line in process.stdout]  # type: ignore[union-attr]
    return_code = process.wait(timeout=20)

    assert stdout_lines == ["frame=1"]
    assert return_code == 0
    assert len(drain.text()) == 1_000_000


def test_stderr_drain_handles_missing_stream() -> None:
    assert StderrDrain(None).text() == ""
