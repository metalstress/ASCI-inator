import numpy as np
from PIL import Image, ImageDraw, ImageFont


def build_glyph_atlas(font_pil: ImageFont.ImageFont, ramp: str, cell_w: int, cell_h: int):
    """Build a monochrome glyph atlas for the given font and ramp.

    Returns (atlas_img: PIL.Image 'L', tiles_x: int, tiles_y: int).
    """
    if not ramp or len(ramp) < 2:
        ramp = " .:-=+*#%@"
    n = len(ramp)
    # Create square-ish grid
    tiles_x = int(np.ceil(np.sqrt(n)))
    tiles_y = int(np.ceil(n / tiles_x))
    atlas_w = tiles_x * cell_w
    atlas_h = tiles_y * cell_h
    atlas = Image.new('L', (atlas_w, atlas_h), color=0)
    draw = ImageDraw.Draw(atlas)

    # Center each glyph in its tile
    for idx, ch in enumerate(ramp):
        tx = idx % tiles_x
        ty = idx // tiles_x
        x0 = tx * cell_w
        y0 = ty * cell_h
        # Measure and center
        try:
            bbox = font_pil.getbbox(ch)
            gw = bbox[2] - bbox[0]
            gh = bbox[3] - bbox[1]
        except Exception:
            gw, gh = cell_w, cell_h
        ox = x0 + max(0, (cell_w - gw) // 2)
        oy = y0 + max(0, (cell_h - gh) // 2)
        draw.text((ox, oy), ch, fill=255, font=font_pil)

    return atlas, tiles_x, tiles_y


