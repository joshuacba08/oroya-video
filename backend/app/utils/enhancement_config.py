from __future__ import annotations

import json


def parse_enhancement_config_json(raw_value: str | None) -> dict[str, object]:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
