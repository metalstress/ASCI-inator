from __future__ import annotations

import os
from PySide6.QtGui import QIcon


def load_icon(icon_name: str, size: int = 24):
    """Load icon from local `icons/` directory near project root."""
    # Start from this file, try to find nearest icons/ upwards
    here = os.path.abspath(os.path.dirname(__file__))
    candidates = [
        os.path.join(here, "..", "..", "icons"),
        os.path.join(here, "..", "icons"),
        os.path.join(here, "icons"),
        os.path.join(os.getcwd(), "icons"),
    ]
    icons_dir = None
    for d in candidates:
        p = os.path.abspath(d)
        if os.path.isdir(p):
            icons_dir = p
            break
    if not icons_dir:
        return None

    try:
        present = {fn.lower(): os.path.join(icons_dir, fn) for fn in os.listdir(icons_dir)}
    except Exception:
        return None

    for name in (f"{icon_name}.svg", f"{icon_name}.svg.svg", f"{icon_name}.png"):
        p = present.get(name.lower())
        if p and os.path.exists(p):
            return QIcon(p)
    return None


