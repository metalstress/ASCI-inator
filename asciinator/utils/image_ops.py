from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def clamp01(x: np.ndarray | float) -> np.ndarray | float:
    return np.clip(x, 0.0, 1.0)


def to_grayscale(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (y / 255.0).astype(np.float32)


def resize_to_char_grid(
    img_gray: np.ndarray,
    cell_w: int,
    cell_h: int,
    cols: int | None = None,
    rows: int | None = None,
    max_cols: int = 260,
    max_rows: int = 180,
) -> tuple[np.ndarray, int, int]:
    h, w = img_gray.shape
    if cols is None:
        cols = min(max_cols, max(16, w // max(6, cell_w)))
    if rows is None:
        rows = min(max_rows, max(8, h // max(8, cell_h)))
    cols = max(8, int(cols))
    rows = max(8, int(rows))
    pil = (
        Image.fromarray((img_gray * 255).astype(np.uint8))
        .convert("L")
        .resize((cols, rows), Image.BICUBIC)
    )
    grid = np.array(pil, dtype=np.float32) / 255.0
    return grid, cols, rows


def build_ascii_image_color(
    grid_gray: np.ndarray,
    ramp: Sequence[str] | str,
    font_pil: ImageFont.FreeTypeFont,
    cell_w: int,
    cell_h: int,
    color_stops: Sequence[Tuple[int, int, int]],
    invert: bool = False,
    gap_x: int = 0,
    gap_y: int = 0,
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    glyph_cache: dict | None = None,
):
    rows, cols = grid_gray.shape
    W = cols * cell_w + max(0, cols - 1) * gap_x
    H = rows * cell_h + max(0, rows - 1) * gap_y
    img = Image.new("RGB", (max(1, int(W)), max(1, int(H))), color=bg_color)

    n = len(ramp) - 1

    if glyph_cache is not None:
        for y in range(rows):
            row_vals = grid_gray[y]
            for x in range(cols):
                v = float(row_vals[x])
                v_for_char = 1.0 - v if invert else v
                idx = int(v_for_char * n + 0.5)
                ch = ramp[idx]

                t = v
                seg = int(min(3, math.floor(t * 4.0)))
                seg_t0 = seg * 0.25
                local_t = (t - seg_t0) / 0.25
                c1 = color_stops[seg]
                c2 = color_stops[seg + 1]
                color = (
                    int(c1[0] + (c2[0] - c1[0]) * local_t),
                    int(c1[1] + (c2[1] - c1[1]) * local_t),
                    int(c1[2] + (c2[2] - c1[2]) * local_t),
                )

                cache_key = (ch, color)
                if cache_key not in glyph_cache:
                    glyph_img = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
                    glyph_draw = ImageDraw.Draw(glyph_img)
                    glyph_draw.text((0, 0), ch, fill=color, font=font_pil, anchor="lt")
                    glyph_cache[cache_key] = glyph_img

                pos_x = x * (cell_w + gap_x)
                pos_y = y * (cell_h + gap_y)
                img.paste(glyph_cache[cache_key], (pos_x, pos_y), glyph_cache[cache_key])
    else:
        draw = ImageDraw.Draw(img)
        for y in range(rows):
            row_vals = grid_gray[y]
            for x in range(cols):
                v = float(row_vals[x])
                v_for_char = 1.0 - v if invert else v
                idx = int(v_for_char * n + 0.5)
                ch = ramp[idx]
                t = v
                seg = int(min(3, math.floor(t * 4.0)))
                seg_t0 = seg * 0.25
                local_t = (t - seg_t0) / 0.25
                c1 = color_stops[seg]
                c2 = color_stops[seg + 1]
                color = (
                    int(c1[0] + (c2[0] - c1[0]) * local_t),
                    int(c1[1] + (c2[1] - c1[1]) * local_t),
                    int(c1[2] + (c2[2] - c1[2]) * local_t),
                )
                draw.text((x * (cell_w + gap_x), y * (cell_h + gap_y)), ch, fill=color, font=font_pil, anchor="lt")

    return img


