"""Line work from a raster plan (a scan or an image export), as the same kind of line objects the vector route reads from a PDF. Straight
runs of dark pixels, found with morphology, carry their position, extent and thickness; nothing here knows a scale or a drawing style."""
from collections import Counter

import cv2
import numpy as np

from plan2cost.vector_walls import Line


def vectorise(gray: np.ndarray, dark: int = 150, min_len_px: int = 40, max_w_px: int = 80) -> list[Line]:
    """Axis-aligned runs of ink at least `min_len_px` long. Units are pixels; `w` is the run's thickness in pixels (a hairline is 1 to 3,
    a solid wall drawn as a bar is many times that)."""
    mask = (gray < dark).astype(np.uint8)
    lines: list[Line] = []
    for orient in ("h", "v"):
        k = (min_len_px, 1) if orient == "h" else (1, min_len_px)
        opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
        n, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
        for i in range(1, n):
            x, y, w, h, _a = stats[i]
            if orient == "h" and h <= max_w_px:
                lines.append(Line("h", y + h / 2, float(x), float(x + w), float(h)))
            elif orient == "v" and w <= max_w_px:
                lines.append(Line("v", x + w / 2, float(y), float(y + h), float(w)))
    return lines


def bar_width_px(lines: list[Line], min_len_px: float = 120, min_w_px: float = 6) -> list[tuple[int, int]]:
    """Histogram of the thickness of long runs that are thicker than a drawn line: (width_px, how much length carries it)."""
    c: Counter = Counter()
    for l in lines:
        if l.length >= min_len_px and l.w >= min_w_px:
            c[round(l.w)] += int(l.length)
    return sorted(c.items(), key=lambda kv: -kv[1])
