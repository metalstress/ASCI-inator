from __future__ import annotations

import math
import numpy as np

from .waves import WaveParams, apply_waves_time


def render_morph(base_gray: np.ndarray, target_gray: np.ndarray | None, t: float, params: WaveParams) -> np.ndarray:
    if target_gray is None or target_gray.shape != base_gray.shape:
        return apply_waves_time(base_gray, t, params)
    f = 0.5 + 0.5 * math.sin(t * 0.8)
    out = (1 - f) * base_gray + f * target_gray
    return np.clip(out, 0.0, 1.0)


