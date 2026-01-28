from __future__ import annotations

import numpy as np

try:
    from scipy.ndimage import gaussian_filter as _scipy_gaussian_filter  # type: ignore
    SCIPY_AVAILABLE = True
except Exception:  # pragma: no cover
    _scipy_gaussian_filter = None
    SCIPY_AVAILABLE = False


def _gaussian_blur_numpy(img: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return img
    h, w = img.shape
    temp = np.zeros_like(img)
    for y in range(h):
        for x in range(w):
            x0 = max(0, x - radius)
            x1 = min(w - 1, x + radius)
            temp[y, x] = img[y, x0 : x1 + 1].mean()
    out = np.zeros_like(img)
    for x in range(w):
        for y in range(h):
            y0 = max(0, y - radius)
            y1 = min(h - 1, y + radius)
            out[y, x] = temp[y0 : y1 + 1, x].mean()
    return out


def _detect_simple_edges(image: np.ndarray, sensitivity: float = 0.3) -> np.ndarray:
    rows, cols = image.shape
    edges = np.zeros_like(image)
    for i in range(1, rows - 1):
        for j in range(1, cols - 1):
            diff = (
                abs(image[i, j] - image[i - 1, j])
                + abs(image[i, j] - image[i + 1, j])
                + abs(image[i, j] - image[i, j - 1])
                + abs(image[i, j] - image[i, j + 1])
            )
            edges[i, j] = diff / 4.0
    if edges.max() > 0:
        edges = edges / edges.max()
    edges = np.power(edges, 1.0 - sensitivity * 0.5)
    return edges


def _animate_fire_on_edges(
    edges: np.ndarray,
    t: float,
    rows: int,
    cols: int,
    wave_speed: float = 1.0,
    amplitude: float = 0.5,
    layers: int = 3,
) -> np.ndarray:
    y_coords = np.arange(rows)[:, np.newaxis]
    x_coords = np.arange(cols)[np.newaxis, :]
    animation = np.zeros((rows, cols))
    for i in range(layers):
        freq_mult = 2.0 + i * 1.0
        phase_x = 0.1 + i * 0.05
        phase_y = 0.15 - i * 0.05
        weight = 1.0 / (i + 1)
        wave = np.sin(t * freq_mult * wave_speed + x_coords * phase_x + y_coords * phase_y)
        animation += wave * weight
    animation = (animation / layers) * amplitude * 0.5 + 0.5
    animation = np.clip(animation, 0.0, 1.0)
    fire = edges * animation
    fire = np.power(fire, 0.6)
    return fire


def render_contourswim(
    base_gray: np.ndarray,
    t: float,
    *,
    edge_sensitivity: float,
    edge_blur: int,
    wave_speed: float,
    amplitude: float,
    layers: int,
    glow: float,
) -> np.ndarray:
    if base_gray is None:
        return base_gray
    base_image = base_gray.copy()
    rows, cols = base_image.shape
    edges = _detect_simple_edges(base_image, edge_sensitivity)
    if edge_blur > 0:
        blur_amount = max(1, int(edge_blur))
        if SCIPY_AVAILABLE:
            edges = _scipy_gaussian_filter(edges, sigma=blur_amount)  # type: ignore
        else:
            edges = _gaussian_blur_numpy(edges, blur_amount)
    effect = _animate_fire_on_edges(edges, t, rows, cols, wave_speed, amplitude, layers)
    result = base_image.copy()
    threshold = 0.1 * (1.0 - edge_sensitivity * 0.5)
    effect_mask = edges > threshold
    result[effect_mask] = np.clip(result[effect_mask] + effect[effect_mask] * glow, 0.0, 1.0)
    return result


