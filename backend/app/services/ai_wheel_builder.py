"""Build an installable wheel of basicsr 1.4.2 (dependency of Real-ESRGAN/GFPGAN).

basicsr is published only as an sdist that no longer installs cleanly:
- `setup_requires=['cython', 'numpy', 'torch']` breaks isolated builds.
- `get_version()` reads the version through `exec()` into `locals()`, which stopped
  working in Python 3.13 (PEP 667), so the build fails on modern Python.
- It depends on `tb-nightly` (TensorBoard), unused for inference.
- `basicsr/data/degradations.py` imports `torchvision.transforms.functional_tensor`,
  removed in torchvision 0.17.

We download the official sdist (pinned SHA256), patch those four points and build a
pure-Python wheel. The installer ships it; the AI install endpoint builds it on demand.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

BASICSR_VERSION = "1.4.2"
BASICSR_SDIST_URL = (
    "https://files.pythonhosted.org/packages/86/41/"
    "00a6b000f222f0fa4c6d9e1d6dcc9811a374cabb8abb9d408b77de39648c/basicsr-1.4.2.tar.gz"
)
BASICSR_SDIST_SHA256 = "b89b595a87ef964cda9913b4d99380ddb6554c965577c0c10cb7b78e31301e87"
BASICSR_WHEEL_GLOB = f"basicsr-{BASICSR_VERSION}-*.whl"

_ORIGINAL_GET_VERSION = """def get_version():
    with open(version_file, 'r') as f:
        exec(compile(f.read(), version_file, 'exec'))
    return locals()['__version__']
"""
_PATCHED_GET_VERSION = """def get_version():
    with open('VERSION', 'r') as f:
        return f.read().strip()
"""
_ORIGINAL_SETUP_REQUIRES = "        setup_requires=['cython', 'numpy', 'torch'],\n"
_ORIGINAL_TV_IMPORT = "from torchvision.transforms.functional_tensor import rgb_to_grayscale"
_PATCHED_TV_IMPORT = "from torchvision.transforms.functional import rgb_to_grayscale"


class BasicsrWheelBuildError(RuntimeError):
    pass


def find_basicsr_wheel(directory: Path) -> Path | None:
    if not directory.is_dir():
        return None
    return next(iter(sorted(directory.glob(BASICSR_WHEEL_GLOB))), None)


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise BasicsrWheelBuildError(f"Unexpected basicsr source layout in {path.name}.")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch_basicsr_source(source_dir: Path) -> None:
    setup_py = source_dir / "setup.py"
    _replace_once(setup_py, _ORIGINAL_GET_VERSION, _PATCHED_GET_VERSION)
    _replace_once(setup_py, _ORIGINAL_SETUP_REQUIRES, "")
    _replace_once(
        source_dir / "basicsr" / "data" / "degradations.py",
        _ORIGINAL_TV_IMPORT,
        _PATCHED_TV_IMPORT,
    )
    requirements = source_dir / "requirements.txt"
    lines = requirements.read_text(encoding="utf-8").splitlines()
    requirements.write_text(
        "\n".join(line for line in lines if line.strip() != "tb-nightly") + "\n",
        encoding="utf-8",
    )


def _download_sdist(destination: Path) -> None:
    request = urllib.request.Request(BASICSR_SDIST_URL, headers={"User-Agent": "oroya-video"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as out:
        while chunk := response.read(1024 * 256):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != BASICSR_SDIST_SHA256:
        raise BasicsrWheelBuildError("basicsr sdist failed the SHA256 integrity check.")


def build_basicsr_wheel(output_dir: Path, python_executable: str = sys.executable) -> Path:
    """Return the path of a basicsr wheel in `output_dir`, building it if needed."""
    existing = find_basicsr_wheel(output_dir)
    if existing is not None:
        return existing

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oroya-basicsr-") as temp_name:
        temp_dir = Path(temp_name)
        archive = temp_dir / "basicsr.tar.gz"
        _download_sdist(archive)
        extract_dir = temp_dir / "src"
        with tarfile.open(archive) as tar:
            tar.extractall(extract_dir, filter="data")
        source_dir = extract_dir / f"basicsr-{BASICSR_VERSION}"
        patch_basicsr_source(source_dir)

        result = subprocess.run(
            [
                python_executable,
                "-m",
                "pip",
                "wheel",
                str(source_dir),
                "--no-deps",
                "--wheel-dir",
                str(output_dir),
                "--disable-pip-version-check",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip()[-500:]
            raise BasicsrWheelBuildError(f"basicsr wheel build failed: {tail}")
        shutil.rmtree(source_dir, ignore_errors=True)

    wheel = find_basicsr_wheel(output_dir)
    if wheel is None:
        raise BasicsrWheelBuildError("basicsr wheel was not produced.")
    logger.info("basicsr wheel built: %s", wheel)
    return wheel
