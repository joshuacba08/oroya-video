from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from app.main import create_app  # noqa: PLC0415

    output_path = repo_root / "shared" / "api" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = create_app().openapi()
    output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"OpenAPI exported to {output_path}")


if __name__ == "__main__":
    main()
