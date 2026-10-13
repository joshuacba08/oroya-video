"""Check that every place that declares the app version agrees (and matches the tag).

Usage: python scripts/check_versions.py [--tag vX.Y.Z]
In GitHub Actions the tag is taken from GITHUB_REF_NAME when it starts with "v".
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _regex(path: str, pattern: str) -> str:
    match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit(f"Version not found in {path}")
    return match.group(1)


def _cargo_lock_version() -> str:
    text = (ROOT / "frontend/src-tauri/Cargo.lock").read_text(encoding="utf-8")
    match = re.search(r'name = "oroya-video"\nversion = "([^"]+)"', text)
    if not match:
        raise SystemExit("oroya-video not found in Cargo.lock")
    return match.group(1)


def collect_versions() -> dict[str, str]:
    return {
        "backend/app/version.py": _regex("backend/app/version.py", r'__version__ = "([^"]+)"'),
        "backend/pyproject.toml": tomllib.loads(
            (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"],
        "frontend/package.json": json.loads(
            (ROOT / "frontend/package.json").read_text(encoding="utf-8")
        )["version"],
        "frontend/src-tauri/tauri.conf.json": json.loads(
            (ROOT / "frontend/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
        )["version"],
        "frontend/src-tauri/Cargo.toml": tomllib.loads(
            (ROOT / "frontend/src-tauri/Cargo.toml").read_text(encoding="utf-8")
        )["package"]["version"],
        "frontend/src-tauri/Cargo.lock": _cargo_lock_version(),
        "frontend/src/app/core/app-version.ts": _regex(
            "frontend/src/app/core/app-version.ts", r"APP_VERSION = '([^']+)'"
        ),
        "shared/api/openapi.json": json.loads(
            (ROOT / "shared/api/openapi.json").read_text(encoding="utf-8")
        )["info"]["version"],
    }


def main() -> int:
    tag = None
    if "--tag" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1]
    elif os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME")

    versions = collect_versions()
    distinct = set(versions.values())
    for path, version in versions.items():
        print(f"{version:>10}  {path}")
    if len(distinct) != 1:
        print("ERROR: the version is not the same everywhere.", file=sys.stderr)
        return 1
    if tag and tag.removeprefix("v") != distinct.pop():
        print(f"ERROR: tag {tag} does not match the app version.", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
