from __future__ import annotations

EXTRACTION_PROGRESS_START = 0.0
EXTRACTION_PROGRESS_END = 25.0
ENHANCEMENT_PROGRESS_START = 25.0
ENHANCEMENT_PROGRESS_END = 60.0
# Restauración facial opcional (GFPGAN); si está desactivada, el progreso salta esta banda.
FACE_RESTORE_PROGRESS_START = 60.0
FACE_RESTORE_PROGRESS_END = 66.0
ENCODING_PROGRESS_START = 66.0
ENCODING_PROGRESS_END = 85.0
MUX_PROGRESS_START = 85.0
MUX_PROGRESS_END = 97.0
EXPORT_PROGRESS_START = 97.0
EXPORT_PROGRESS_END = 100.0


def calculate_stage_progress(
    processed: int,
    total: int | None,
    *,
    start: float,
    end: float,
    clamp_to: float | None = None,
) -> float:
    if not total or total <= 0:
        return round(start, 2)

    stage_progress = min(max(processed / total, 0.0), 1.0)
    global_progress = start + ((end - start) * stage_progress)
    if clamp_to is not None:
        global_progress = min(global_progress, clamp_to)
    return round(global_progress, 2)
