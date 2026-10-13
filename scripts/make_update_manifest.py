"""Build latest.json for tauri-plugin-updater from the signed NSIS installer.

Usage:
  python scripts/make_update_manifest.py --tag v0.4.0 \
      --bundle-dir frontend/src-tauri/target/release/bundle/nsis

The app checks https://github.com/<repo>/releases/latest/download/latest.json, so this file
must be uploaded to every release next to the installer and its .sig.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "joshuacba08/oroya-video"


def github_asset_name(file_name: str) -> str:
    # GitHub sustituye los espacios del nombre del asset por puntos al subirlo.
    return file_name.replace(" ", ".")


def build_manifest(bundle_dir: Path, tag: str, repo: str) -> dict:
    installers = sorted(bundle_dir.glob("*.exe"))
    if len(installers) != 1:
        raise SystemExit(f"Expected one installer in {bundle_dir}, found {len(installers)}")
    installer = installers[0]
    signature_file = installer.with_name(f"{installer.name}.sig")
    if not signature_file.is_file():
        raise SystemExit(
            f"{signature_file.name} not found: the build was not signed "
            "(TAURI_SIGNING_PRIVATE_KEY / TAURI_SIGNING_PRIVATE_KEY_PASSWORD)."
        )

    notes_file = ROOT / "docs" / "releases" / f"{tag}.md"
    notes = notes_file.read_text(encoding="utf-8").strip() if notes_file.is_file() else ""
    url = (
        f"https://github.com/{repo}/releases/download/{quote(tag)}/"
        f"{quote(github_asset_name(installer.name))}"
    )
    platform_entry = {
        "signature": signature_file.read_text(encoding="utf-8").strip(),
        "url": url,
    }
    return {
        "version": tag.removeprefix("v"),
        "notes": notes,
        "pub_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": {
            "windows-x86_64": platform_entry,
            "windows-x86_64-nsis": platform_entry,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = build_manifest(args.bundle_dir, args.tag, args.repo)
    output = args.output or args.bundle_dir / "latest.json"
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{output} -> {manifest['platforms']['windows-x86_64']['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
