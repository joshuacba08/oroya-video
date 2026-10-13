"""Temporal stability (REQ-041): calm the frame-to-frame "boiling" of AI-generated texture.

Real-ESRGAN, RealPLKSR and GFPGAN process every frame on its own, so the detail they invent
changes slightly from one frame to the next and the video shimmers even at 60 fps. Each output
frame is blended with the previous stabilized one, warped to the current position with optical
flow, only where that warp is reliable:

1. Dense optical flow (OpenCV DIS) between the previous and current *source* frames, in grey at
   source resolution (a few ms per frame).
2. Reliability: how well the previous source frame, warped with that flow, matches the current
   one. Occlusions, fast motion and lighting changes get a low weight, so nothing ghosts.
3. The flow is scaled to the output size and warps the previous stabilized output; the current
   output moves towards it by `alpha × weight`. Scene changes reset the history.
"""

from __future__ import annotations

from typing import Any

# Mezcla máxima con el fotograma anterior (a estabilidad 100). Más alto deja estelas.
MAX_ALPHA = 0.8
# Error (0-255, en gris) a partir del cual el fotograma anterior no se usa en ese punto.
RELIABILITY_THRESHOLD = 10.0
# Diferencia media en gris (0-1) que se considera cambio de escena: se reinicia la historia.
SCENE_CHANGE_THRESHOLD = 0.15


class TemporalStabilizer:
    def __init__(self, strength: float) -> None:
        import cv2

        self.alpha = min(max(strength, 0.0), 1.0) * MAX_ALPHA
        self._cv2 = cv2
        self._flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self._grids: dict[tuple[int, int], tuple[Any, Any]] = {}
        self.reset()

    def reset(self) -> None:
        self._previous_gray: Any | None = None
        self._previous_output: Any | None = None
        self.resets = 0

    def _grid(self, height: int, width: int) -> tuple[Any, Any]:
        import numpy as np

        # Solo hay dos tamaños por job (origen y salida): la caché no crece.
        key = (height, width)
        if key not in self._grids:
            self._grids[key] = tuple(
                np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
            )
        return self._grids[key]

    def _remember(self, gray: Any, output: Any) -> Any:
        self._previous_gray = gray
        self._previous_output = output
        return output

    def apply(self, source: Any, output: Any) -> Any:
        """`source`: BGR frame at source size; `output`: processed BGR frame (any size)."""
        import numpy as np

        cv2 = self._cv2
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        previous_gray, previous_output = self._previous_gray, self._previous_output
        if (
            self.alpha <= 0
            or previous_gray is None
            or previous_gray.shape != gray.shape
            or previous_output.shape != output.shape
            or float(cv2.absdiff(gray, previous_gray).mean()) / 255.0 > SCENE_CHANGE_THRESHOLD
        ):
            if previous_gray is not None:
                self.resets += 1
            return self._remember(gray, output)

        # Flujo "hacia atrás": para cada píxel actual, dónde estaba en el fotograma anterior.
        flow = self._flow.calc(gray, previous_gray, None)
        height, width = gray.shape
        grid_x, grid_y = self._grid(height, width)
        warped_gray = cv2.remap(
            previous_gray,
            grid_x + flow[..., 0],
            grid_y + flow[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        error = cv2.GaussianBlur(cv2.absdiff(gray, warped_gray).astype(np.float32), (5, 5), 0)
        weight = np.clip(1.0 - error / RELIABILITY_THRESHOLD, 0.0, 1.0) * self.alpha

        out_height, out_width = output.shape[:2]
        if (out_height, out_width) != (height, width):
            flow = cv2.resize(flow, (out_width, out_height), interpolation=cv2.INTER_LINEAR)
            flow[..., 0] *= out_width / width
            flow[..., 1] *= out_height / height
            weight = cv2.resize(weight, (out_width, out_height), interpolation=cv2.INTER_LINEAR)
        out_grid_x, out_grid_y = self._grid(out_height, out_width)
        warped_output = cv2.remap(
            previous_output,
            out_grid_x + flow[..., 0],
            out_grid_y + flow[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        current = output.astype(np.float32)
        blended = current + weight[..., None] * (warped_output.astype(np.float32) - current)
        stabilized = np.clip(blended + 0.5, 0, 255).astype(np.uint8)
        return self._remember(gray, stabilized)
