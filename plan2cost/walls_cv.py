"""Walls from a raster plan by classical image processing, with the scale taken from the PDF.

A cut wall is drawn as two thin parallel face lines one wall thickness apart. We find the long straight horizontal and vertical runs, pair
runs of the right spacing that overlap, and merge collinear pieces across openings (the QS convention: full runs, openings ignored). All
lengths are in millimetres from the fitted scale; no model is involved at this stage. The model's job comes later, on the walls this
finds that are ambiguous."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Wall:
    orient: str  # "h" or "v"
    centre_mm: float  # position across the wall (y for "h", x for "v"), from the sheet origin
    start_mm: float
    end_mm: float
    thickness_mm: float

    @property
    def length_mm(self) -> float:
        return self.end_mm - self.start_mm


MIN_FACE_PX = 3  # a cut-wall face is drawn heavy; grid, dimension and extension lines are 1 to 2 px
MAX_FACE_PX = 7  # a face line plus a grid or extension line drawn alongside it is still one face


def _runs(mask: np.ndarray, orient: str, min_len_px: int) -> list[tuple[int, int, int]]:
    """Straight dark runs as (across_px, start_px, end_px), one per face line."""
    k = (min_len_px, 1) if orient == "h" else (1, min_len_px)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
    n, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if orient == "h" and MIN_FACE_PX <= h <= MAX_FACE_PX:
            out.append((int(y + h / 2), x, x + w))
        elif orient == "v" and MIN_FACE_PX <= w <= MAX_FACE_PX:
            out.append((int(x + w / 2), y, y + h))
    return out


THICKNESS_WINDOWS_MM = {100: (85, 135), 150: (135, 185), 230: (195, 270)}  # nominal block thickness -> accepted face spacing


def _nominal(spacing_mm: float, windows: dict[int, tuple[int, int]]) -> int | None:
    return next((n for n, (lo, hi) in windows.items() if lo <= spacing_mm <= hi), None)


def find_walls(gray: np.ndarray, mm_per_px: float, region_px: tuple[int, int, int, int], windows: dict[int, tuple[int, int]] | None = None,
               min_run_mm: float = 800, bridge_mm: float = 2400, dark: int = 140) -> list[Wall]:
    windows = windows or THICKNESS_WINDOWS_MM
    x0, y0, x1, y1 = region_px
    mask = np.zeros_like(gray, dtype=np.uint8)
    mask[y0:y1, x0:x1] = (gray[y0:y1, x0:x1] < dark).astype(np.uint8)
    max_gap = max(hi for _, hi in windows.values()) / mm_per_px
    min_len = max(8, int(min_run_mm / mm_per_px))
    pieces: list[Wall] = []
    for orient in ("h", "v"):
        runs = sorted(_runs(mask, orient, min_len))
        used: set[int] = set()
        cands = []
        for i, (a, s1, e1) in enumerate(runs):
            for j in range(i + 1, len(runs)):
                b, s2, e2 = runs[j]
                if b - a > max_gap:
                    break
                lo, hi = max(s1, s2), min(e1, e2)
                nominal = _nominal((b - a) * mm_per_px, windows)
                if nominal and hi - lo >= min_len:
                    cands.append(((hi - lo), i, j, nominal, lo, hi, (a + b) / 2, (b - a)))
        for length, i, j, nominal, lo, hi, centre, gap in sorted(cands, reverse=True):  # the longest overlaps claim their faces first
            if i in used or j in used:
                continue
            used.update((i, j))
            pieces.append(Wall(orient, centre * mm_per_px, lo * mm_per_px, hi * mm_per_px, float(nominal)))
    return _merge(pieces, bridge_mm)


def _merge(pieces: list[Wall], bridge_mm: float, tol_mm: float = 60) -> list[Wall]:
    """Collinear pieces (same orientation and centre line) are one run when the gap between them is an opening."""
    merged: list[Wall] = []
    for p in sorted(pieces, key=lambda w: (w.orient, round(w.centre_mm / tol_mm), w.start_mm)):
        last = merged[-1] if merged else None
        if last and last.orient == p.orient and abs(last.centre_mm - p.centre_mm) <= tol_mm and p.start_mm - last.end_mm <= bridge_mm:
            last.end_mm = max(last.end_mm, p.end_mm)
            last.thickness_mm = (last.thickness_mm + p.thickness_mm) / 2
        else:
            merged.append(Wall(p.orient, p.centre_mm, p.start_mm, p.end_mm, p.thickness_mm))
    return merged


def girth_by_thickness(walls: list[Wall], classes_mm=(100, 150, 230)) -> dict[int, float]:
    """Total centre-line length per nominal thickness class (nearest class), in metres."""
    out: dict[int, float] = {}
    for w in walls:
        c = min(classes_mm, key=lambda c: abs(c - w.thickness_mm))
        out[c] = out.get(c, 0.0) + w.length_mm / 1000
    return {c: round(v, 2) for c, v in sorted(out.items())}
