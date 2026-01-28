from __future__ import annotations

import numpy as np

from .waves import WaveParams, apply_waves_time


def render_audio(base_gray, t, params: WaveParams, level_or_bands, gain: float):
    # Accept scalar or 6-band vector
    if isinstance(level_or_bands, (list, tuple, np.ndarray)):
        bands = np.asarray(level_or_bands, dtype=float)
        level = float(np.clip(bands.mean() if bands.size else 0.0, 0.0, 1.0))
    else:
        level = float(level_or_bands)
    speed_boost = 1 + 1.2 * level
    amp = params.amplitude * (1.0 + gain * level)
    p = WaveParams(
        params.freq_x,
        params.freq_y,
        params.speed_x * speed_boost,
        params.speed_y * speed_boost,
        amp,
        params.contrast,
    )
    return apply_waves_time(base_gray, t, p)


