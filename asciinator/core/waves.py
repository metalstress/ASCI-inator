from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class WaveParams:
    freq_x: float = 0.8
    freq_y: float = 0.6
    speed_x: float = 1.2
    speed_y: float = -0.9
    amplitude: float = 0.25
    contrast: float = 1.0


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def apply_waves_time(base_gray: np.ndarray, t: float, params: WaveParams) -> np.ndarray:
    rows, cols = base_gray.shape
    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float32)
    x = xx / max(1, cols)
    y = yy / max(1, rows)
    A = 1.0 - base_gray
    phase_x = 2 * math.pi * (params.freq_x * x + 0.1) + t * params.speed_x
    phase_y = 2 * math.pi * (params.freq_y * y + 0.3) + t * params.speed_y
    W = np.sin(phase_x) * A + np.sin(phase_y) * (1.0 - A * 0.5)
    phase_xy = 2 * math.pi * (0.35 * (x + y)) + t * 0.7
    W += 0.6 * np.sin(phase_xy) * (0.5 + 0.5 * np.sin(phase_x) * np.sin(phase_y))
    out = base_gray + params.amplitude * W
    if params.contrast != 1.0:
        mid = 0.5
        out = clamp01((out - mid) * params.contrast + mid)
    return clamp01(out)


