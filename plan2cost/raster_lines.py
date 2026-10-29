"""Line work from a raster plan (a scan or an image export), as the same kind of line objects the vector route reads from a PDF. Straight
runs of dark pixels, found with morphology, carry their position, extent and thickness; nothing here knows a scale or a drawing style."""
import collections
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


def vectorise_multi(gray: np.ndarray, dark: int = 150, kernels: tuple[int, ...] = (30, 60, 120, 240), max_w_px: int = 110) -> list[Line]:
    """Line work at every thickness. A thick bar joined to other bars fuses with them unless the opening kernel is clearly longer than the
    bar is wide, so each kernel length only contributes the runs thin enough for it (thickness at most 40 percent of the kernel); the same
    run found at several kernel lengths is kept once."""
    found: list[Line] = []
    for k in kernels:
        for l in vectorise(gray, dark=dark, min_len_px=k, max_w_px=max_w_px):
            if l.w <= 0.4 * k or (k == kernels[0] and l.w <= 0.4 * k):
                found.append(l)
    found.sort(key=lambda l: -l.length)
    out: list[Line] = []
    index: dict[tuple, list[Line]] = {}
    for l in found:
        key = (l.orient, round(l.pos / 8))
        dup = any(abs(o.pos - l.pos) <= max(2.0, 0.5 * min(o.w, l.w)) and min(o.b, l.b) - max(o.a, l.a) >= 0.6 * l.length and abs(o.w - l.w) <= 0.5 * max(o.w, l.w)
                  for kk in ((key[0], key[1] - 1), key, (key[0], key[1] + 1)) for o in index.get(kk, []))
        if not dup:
            out.append(l)
            index.setdefault(key, []).append(l)
    return out


def bar_widths(gray: np.ndarray, dark: int = 150, min_px: int = 9, max_px: int = 110) -> collections.Counter:
    """Widths of the solid bands on the page: opening with a square kernel removes lines and text and keeps anything at least `min_px` thick;
    the distance transform along the ridge of what remains gives each band's width, whatever its length or how it joins other bands.
    Returns width (px) -> amount of ridge (length) at that width."""
    mask = (gray < dark).astype(np.uint8)
    thick = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (min_px, min_px)))
    dt = cv2.distanceTransform(thick, cv2.DIST_L2, 5)
    ridge = (dt > 0) & (dt >= cv2.dilate(dt, np.ones((5, 5), np.uint8)) - 1e-3)
    widths = np.round(2 * dt[ridge]).astype(int)
    c: collections.Counter = collections.Counter(int(w) for w in widths if min_px <= w <= max_px)
    return c


def bar_lines(gray: np.ndarray, bar_px: float, dark: int = 150) -> list[Line]:
    """Bars of roughly this width and the thinner partition bars beside them (down to about 45 percent of it), as lines carrying their
    measured thickness. A square opening keeps only what is thick; runs are then read along each direction with a kernel just longer than the
    bar is wide, so a bar joined to others does not fuse with them."""
    mask = (gray < dark).astype(np.uint8)
    k = max(5, int(0.45 * bar_px))
    thick = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    lines = []
    for orient in ("h", "v"):
        kern = (int(1.5 * bar_px), 1) if orient == "h" else (1, int(1.5 * bar_px))
        opened = cv2.morphologyEx(thick, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kern))
        n, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
        for i in range(1, n):
            x, y, w, h, _a = stats[i]
            if orient == "h" and h < 1.8 * bar_px and w > 1.2 * h:
                lines.append(Line("h", y + h / 2, float(x), float(x + w), float(h)))
            elif orient == "v" and w < 1.8 * bar_px and h > 1.2 * w:
                lines.append(Line("v", x + w / 2, float(y), float(y + h), float(w)))
    return lines
