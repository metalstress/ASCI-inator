from __future__ import annotations

import functools
from typing import Tuple

import numpy as np

try:
    from scipy import ndimage as ndi  # type: ignore
    SCIPY = True
except Exception:  # pragma: no cover
    SCIPY = False


def _sobel_edges(gray: np.ndarray) -> np.ndarray:
    if SCIPY:
        gx = ndi.sobel(gray, axis=1)
        gy = ndi.sobel(gray, axis=0)
    else:
        # simple finite differences
        gx = np.zeros_like(gray)
        gy = np.zeros_like(gray)
        gx[:, 1:-1] = (gray[:, 2:] - gray[:, :-2]) * 0.5
        gy[1:-1, :] = (gray[2:, :] - gray[:-2, :]) * 0.5
    mag = np.hypot(gx, gy)
    if mag.max() > 0:
        mag = mag / mag.max()
    return (mag > 0.2).astype(np.float32)


def _edt(mask: np.ndarray) -> np.ndarray:
    if SCIPY:
        return ndi.distance_transform_edt(1.0 - mask)
    # Fallback: Manhattan distance approximation
    h, w = mask.shape
    dist = np.full((h, w), 1e9, dtype=np.float32)
    zeros = np.argwhere(mask > 0.5)
    if zeros.size == 0:
        return dist * 0
    for y in range(h):
        for x in range(w):
            d = np.abs(zeros[:, 0] - y) + np.abs(zeros[:, 1] - x)
            dist[y, x] = float(np.min(d))
    return dist


@functools.lru_cache(maxsize=16)
def get_edge_data(key: Tuple[int, int, int], gray_bytes: bytes) -> Tuple[np.ndarray, np.ndarray]:
    h, w, _ = key  # key carries shape and maybe seed
    gray = np.frombuffer(gray_bytes, dtype=np.float32).reshape(h, w)
    edges = _sobel_edges(gray)
    dist = _edt(edges)
    return edges, dist


