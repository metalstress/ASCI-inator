from __future__ import annotations

import math
import numpy as np


class SwarmState:
    """Deprecated: swarm mode removed. Placeholder to avoid import errors."""
    def __init__(self):
        self.particles = None  # type: ignore


def init_particles(state: SwarmState, rows: int, cols: int):
    n = max(100, cols * rows // 8)
    rng = np.random.default_rng()
    x = rng.random(n) * cols
    y = rng.random(n) * rows
    vx = (rng.random(n) - 0.5) * 0.6
    vy = (rng.random(n) - 0.5) * 0.6
    state.particles = [x, y, vx, vy]


def render_swarm(state: SwarmState, base_gray: np.ndarray, t: float) -> np.ndarray:
    return base_gray


