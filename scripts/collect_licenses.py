"""Collect the license texts that ship with the installer.

Writes into ``frontend/src-tauri/resources/licenses/`` (installed as ``licenses/`` next to the
app):

- ``LICENSE.txt``, ``NOTICE.txt``, ``THIRD_PARTY_NOTICES.md``: Oroya Video's own terms.
- ``rust-crates.txt``: every crate linked into the Windows executable, with its license files.
- ``npm-packages.txt``: every production npm package bundled into the UI (fonts included).
- ``native-libraries.txt``: libraries inside the bundled CPython that its LICENSE.txt omits.

The Python packages of the bundled runtime keep their own license files in
``backend/python/Lib/site-packages/*.dist-info`` and CPython's in ``backend/python/LICENSE.txt``.

Usage: python scripts/collect_licenses.py [output_dir]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
TAURI = FRONTEND / "src-tauri"
DEFAULT_OUTPUT = TAURI / "resources" / "licenses"
TARGET = "x86_64-pc-windows-msvc"

LICENSE_FILE_PREFIXES = ("license", "licence", "copying", "notice", "unlicense", "ofl")
SEPARATOR = "=" * 78

# CPython's LICENSE.txt covers Python itself and code compiled into it, but not these DLLs
# that python-build-standalone ships in DLLs/.
NATIVE_LIBRARIES = """\
Native libraries included in the bundled CPython runtime (backend/python/DLLs)
==============================================================================

CPython itself is under the PSF License: see backend/python/LICENSE.txt.

OpenSSL 3 (libssl-3-x64.dll, libcrypto-3-x64.dll)
  https://www.openssl.org - Apache License 2.0 (same text as LICENSE.txt in this folder).
  Copyright (c) 1998-2025 The OpenSSL Project Authors.
  Copyright (c) 1995-1998 Eric A. Young, Tim J. Hudson.

libffi (libffi-8.dll)
  https://sourceware.org/libffi/ - MIT License.
  Copyright (c) 1996-2024 Anthony Green, Red Hat, Inc and others.

  Permission is hereby granted, free of charge, to any person obtaining a copy of this
  software and associated documentation files (the "Software"), to deal in the Software
  without restriction, including without limitation the rights to use, copy, modify, merge,
  publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
  to whom the Software is furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all copies or
  substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
  INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
  PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
  FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
  OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
  DEALINGS IN THE SOFTWARE.

zlib (zlib1.dll)
  https://zlib.net - zlib License.
  Copyright (C) 1995-2024 Jean-loup Gailly and Mark Adler.

  This software is provided 'as-is', without any express or implied warranty. In no event
  will the authors be held liable for any damages arising from the use of this software.

  Permission is granted to anyone to use this software for any purpose, including commercial
  applications, and to alter it and redistribute it freely, subject to the following
  restrictions:

  1. The origin of this software must not be misrepresented; you must not claim that you
     wrote the original software. If you use this software in a product, an acknowledgment
     in the product documentation would be appreciated but is not required.
  2. Altered source versions must be plainly marked as such, and must not be misrepresented
     as being the original software.
  3. This notice may not be removed or altered from any source distribution.

SQLite (sqlite3.dll)
  https://sqlite.org - Public domain.

Tcl/Tk (tcl86t.dll, tk86t.dll)
  https://www.tcl.tk - Tcl/Tk License (BSD-style); full text in
  backend/python/tcl/tcl8.6/license.terms and backend/python/tcl/tk8.6/license.terms.
"""


def _license_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name.lower().startswith(LICENSE_FILE_PREFIXES)
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _entry(
    title: str,
    details: Iterable[str],
    files: list[Path],
    fallback: str,
    seen_texts: dict[str, str],
) -> str:
    """One package; a license text identical to an earlier one is referenced, not repeated."""
    lines = [SEPARATOR, title, *details, SEPARATOR, ""]
    if files:
        for path in files:
            text = _read(path)
            if text in seen_texts:
                lines += [f"--- {path.name}: same text as in {seen_texts[text]} ---", ""]
            else:
                seen_texts[text] = f"{title} ({path.name})"
                lines += [f"--- {path.name} ---", text, ""]
    else:
        lines += [fallback, ""]
    return "\n".join(lines)


def _rust_packages() -> list[dict]:
    """Crates linked into the Windows build (normal dependencies only, no dev/build)."""
    raw = subprocess.run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--locked",
            "--filter-platform",
            TARGET,
        ],
        cwd=TAURI,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    metadata = json.loads(raw)
    packages = {package["id"]: package for package in metadata["packages"]}
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    root = metadata["resolve"]["root"]

    seen: set[str] = set()
    pending = [root]
    while pending:
        package_id = pending.pop()
        if package_id in seen:
            continue
        seen.add(package_id)
        for dep in nodes[package_id]["deps"]:
            if any(kind["kind"] is None for kind in dep["dep_kinds"]):
                pending.append(dep["pkg"])
    seen.discard(root)
    return sorted((packages[pid] for pid in seen), key=lambda p: (p["name"], p["version"]))


def _rust_section() -> str:
    parts = [
        "Rust crates compiled into the Oroya Video executable",
        "(Windows x86_64, runtime dependencies only).",
        "",
    ]
    seen_texts: dict[str, str] = {}
    for package in _rust_packages():
        crate_dir = Path(package["manifest_path"]).parent
        files = _license_files(crate_dir)
        if package.get("license_file"):
            extra = crate_dir / package["license_file"]
            if extra.is_file() and extra not in files:
                files.append(extra)
        license_id = package.get("license") or "see license file"
        # Enlace al código fuente publicado: MPL-2.0 exige indicar dónde obtenerlo.
        details = [
            f"License: {license_id}",
            f"Source: https://crates.io/crates/{package['name']}/{package['version']}",
        ]
        if package.get("repository"):
            details.append(f"Repository: {package['repository']}")
        parts.append(
            _entry(
                f"{package['name']} {package['version']}",
                details,
                files,
                f"No license file in the published crate; it is distributed under {license_id} "
                "(standard text at https://spdx.org/licenses/).",
                seen_texts,
            )
        )
    return "\n".join(parts)


def _npm_section() -> str:
    pnpm = shutil.which("pnpm") or "pnpm"
    raw = subprocess.run(
        [pnpm, "licenses", "list", "--prod", "--json"],
        cwd=FRONTEND,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    by_license: dict[str, list[dict]] = json.loads(raw)
    packages = sorted(
        (
            (package["name"], version, license_id, Path(path), package.get("homepage"))
            for license_id, items in by_license.items()
            for package in items
            for version, path in zip(package["versions"], package["paths"], strict=False)
        ),
        key=lambda item: (item[0], item[1]),
    )
    parts = ["npm packages bundled into the Oroya Video interface (fonts included).", ""]
    seen_texts: dict[str, str] = {}
    for name, version, license_id, path, homepage in packages:
        details = [f"License: {license_id}"]
        if homepage:
            details.append(f"Source: {homepage}")
        parts.append(
            _entry(
                f"{name} {version}",
                details,
                _license_files(path),
                f"No license file in the published package; it is distributed under "
                f"{license_id} (standard text at https://spdx.org/licenses/).",
                seen_texts,
            )
        )
    return "\n".join(parts)


def collect(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.iterdir():
        if stale.is_file() and stale.name != "README.txt":
            stale.unlink()

    shutil.copyfile(REPO_ROOT / "LICENSE", output_dir / "LICENSE.txt")
    shutil.copyfile(REPO_ROOT / "NOTICE", output_dir / "NOTICE.txt")
    shutil.copyfile(REPO_ROOT / "THIRD_PARTY_NOTICES.md", output_dir / "THIRD_PARTY_NOTICES.md")
    (output_dir / "native-libraries.txt").write_text(NATIVE_LIBRARIES, encoding="utf-8")
    (output_dir / "rust-crates.txt").write_text(_rust_section(), encoding="utf-8")
    (output_dir / "npm-packages.txt").write_text(_npm_section(), encoding="utf-8")


def main() -> None:
    output_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUTPUT
    collect(output_dir)
    for path in sorted(output_dir.iterdir()):
        print(f"{path.name}: {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
