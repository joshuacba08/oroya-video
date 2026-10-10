"""Build the patched basicsr wheel shipped with the installer (see ai_wheel_builder)."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from app.services.ai_wheel_builder import build_basicsr_wheel  # noqa: PLC0415

    output_dir = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "build" / "wheels"
    )
    wheel = build_basicsr_wheel(output_dir.resolve())
    print(f"basicsr wheel: {wheel}")


if __name__ == "__main__":
    main()
