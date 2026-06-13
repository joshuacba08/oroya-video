from __future__ import annotations


def calculate_average_ms(total_ms: float, count: int) -> int | None:
    if count <= 0:
        return None
    return round(total_ms / count)
