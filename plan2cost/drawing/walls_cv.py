"""Walls from a raster plan by classical image processing, with the scale taken from the PDF.

A cut wall is drawn as two thin parallel face lines one wall thickness apart. We find the long straight horizontal and vertical runs, pair
runs of the right spacing that overlap, and merge collinear pieces across openings (the QS convention: full runs, openings ignored). All
lengths are in millimetres from the fitted scale; no model is involved at this stage. The model's job comes later, on the walls this
finds that are ambiguous."""
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Wall:
    """A wall run in millimetres on the sheet: its direction, its centre line across, its start and end along it, its thickness, and the stretches along it that were bridged (openings, or places the faces were not found)."""
    orient: str  # "h" or "v"
    centre_mm: float  # position across the wall (y for "h", x for "v"), from the sheet origin
    start_mm: float
    end_mm: float
    thickness_mm: float
    gaps: list = field(default_factory=list)  # (start_mm, end_mm) stretches along the run that were bridged: openings, or places the faces were not found

    @property
    def length_mm(self) -> float:
        return self.end_mm - self.start_mm


MIN_FACE_PX = 3  # a cut-wall face is drawn heavy; grid, dimension and extension lines are 1 to 2 px
MAX_FACE_PX = 7  # a face line plus a grid or extension line drawn alongside it is still one face


def _runs(mask: np.ndarray, orient: str, min_len_px: int, min_px: int = MIN_FACE_PX, max_px: int = MAX_FACE_PX) -> list[tuple[int, int, int]]:
    """Straight dark runs as (across_px, start_px, end_px), one per face line."""
    k = (min_len_px, 1) if orient == "h" else (1, min_len_px)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
    n, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if orient == "h" and min_px <= h <= max_px:
            out.append((int(y + h / 2), x, x + w))
        elif orient == "v" and min_px <= w <= max_px:
            out.append((int(x + w / 2), y, y + h))
    return out


THICKNESS_WINDOWS_MM = {100: (85, 135), 150: (135, 185), 230: (195, 270)}  # nominal block thickness -> accepted face spacing


def _nominal(spacing_mm: float, windows: dict[int, tuple[int, int]]) -> int | None:
    return next((n for n, (lo, hi) in windows.items() if lo <= spacing_mm <= hi), None)


def _solid_runs(mask: np.ndarray, orient: str, min_len_px: int, min_w_px: int, max_w_px: int) -> list[tuple[int, int, int, int]]:
    """Walls drawn as one solid band (some plans fill the wall instead of drawing two faces): (across_px, start_px, end_px, width_px)."""
    k = (min_len_px, 1) if orient == "h" else (1, min_len_px)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
    n, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _a = stats[i]
        if orient == "h" and min_w_px <= h <= max_w_px:
            out.append((int(y + h / 2), x, x + w, h))
        elif orient == "v" and min_w_px <= w <= max_w_px:
            out.append((int(x + w / 2), y, y + h, w))
    return out


def find_walls(gray: np.ndarray, mm_per_px: float, region_px: tuple[int, int, int, int], windows: dict[int, tuple[int, int]] | None = None,
               min_run_mm: float = 350, bridge_mm: float = 3600, dark: int = 200) -> list[Wall]:
    """Find the walls in a raster page: horizontal and vertical bands of dark pixels whose width matches a block thickness, merged across gaps up to `bridge_mm`. Returns runs in millimetres."""
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
        # some plans draw one face of a wall heavy and the other thin: pair the heavy faces still unused with a thin line at wall spacing
        thin = sorted(_runs(mask, orient, min_len, 1, MIN_FACE_PX - 1))
        extra = []
        for i, (a, s1, e1) in enumerate(runs):
            if i in used:
                continue
            for t, (b, s2, e2) in enumerate(thin):
                gap = abs(b - a)
                nominal = _nominal(gap * mm_per_px, windows)
                lo, hi = max(s1, s2), min(e1, e2)
                # the thin line must run alongside most of the heavy face, and a 100mm wall is never inferred from a thin line
                if nominal and nominal >= 150 and hi - lo >= min_len and hi - lo >= 0.7 * (e1 - s1):
                    extra.append((hi - lo, i, t, nominal, lo, hi, (a + b) / 2))
        used_thin: set[int] = set()
        for length, i, t, nominal, lo, hi, centre in sorted(extra, reverse=True):
            if i in used or t in used_thin:
                continue
            used.add(i); used_thin.add(t)
            pieces.append(Wall(orient, centre * mm_per_px, lo * mm_per_px, hi * mm_per_px, float(nominal)))
        lo_px, hi_px = min(lo for lo, _ in windows.values()) / mm_per_px * 0.8, max(hi for _, hi in windows.values()) / mm_per_px
        for across, s1, e1, width in _solid_runs(mask, orient, min_len, int(MAX_FACE_PX + 1), int(hi_px)):
            nominal = _nominal(width * mm_per_px * 1.15, windows)  # a drawn band is a little narrower than the wall it stands for
            if nominal and width >= lo_px:
                pieces.append(Wall(orient, across * mm_per_px, s1 * mm_per_px, e1 * mm_per_px, float(nominal)))
    return merge_runs(pieces, bridge_mm)


def merge_runs(pieces: list[Wall], bridge_mm: float, tol_mm: float = 60) -> list[Wall]:
    """Collinear pieces (same orientation, centre lines within `tol_mm`) are one run when the gap between them is an opening. Centre
    lines are clustered by distance, not by rounding, so a tiny shift in scale cannot split a wall in two."""
    merged: list[Wall] = []
    for orient in ("h", "v"):
        group = sorted((p for p in pieces if p.orient == orient), key=lambda w: w.centre_mm)
        clusters: list[list[Wall]] = []
        for p in group:
            if clusters and p.centre_mm - clusters[-1][-1].centre_mm <= tol_mm:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        for cl in clusters:
            last = None
            for p in sorted(cl, key=lambda w: w.start_mm):
                if last and p.start_mm - last.end_mm <= bridge_mm:
                    if p.start_mm > last.end_mm + 1:
                        last.gaps.append((last.end_mm, p.start_mm))
                    last.gaps.extend(p.gaps)
                    last.end_mm = max(last.end_mm, p.end_mm)
                    last.thickness_mm = max(last.thickness_mm, p.thickness_mm)  # nominal classes: keep the thickest piece's class
                else:
                    last = Wall(p.orient, p.centre_mm, p.start_mm, p.end_mm, p.thickness_mm, list(p.gaps))
                    merged.append(last)
    return merged


def girth_by_thickness(walls: list[Wall], classes_mm=(100, 150, 230)) -> dict[int, float]:
    """Total centre-line length per nominal thickness class (nearest class), in metres."""
    out: dict[int, float] = {}
    for w in walls:
        c = min(classes_mm, key=lambda c: abs(c - w.thickness_mm))
        out[c] = out.get(c, 0.0) + w.length_mm / 1000
    return {c: round(v, 2) for c, v in sorted(out.items())}


def _outdoors(walls: list[Wall], shape: tuple[int, int], mm_per_px: float, close_mm: float) -> np.ndarray:
    """Boolean mask of the outdoors: flood-filled from the sheet edge over the wall layout, with openings up to `close_mm` closed so it
    cannot leak into the rooms."""
    h, w = shape
    canvas = np.zeros((h, w), np.uint8)
    for wall in walls:
        t = wall.thickness_mm / mm_per_px / 2
        c, a, b = wall.centre_mm / mm_per_px, wall.start_mm / mm_per_px, wall.end_mm / mm_per_px
        p1, p2 = (((int(a), int(c - t)), (int(b), int(c + t))) if wall.orient == "h" else ((int(c - t), int(a)), (int(c + t), int(b))))
        cv2.rectangle(canvas, p1, p2, 1, -1)
    k = max(3, int(close_mm / mm_per_px))
    padded = cv2.copyMakeBorder(canvas, k, k, k, k, cv2.BORDER_CONSTANT, value=0)  # the sheet edge must not be closed over
    closed = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))[k:-k, k:-k]
    free = (closed == 0).astype(np.uint8)
    reach = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(free.copy(), reach, (0, 0), 2)
    return reach[1:-1, 1:-1] > 0


def outline_polygon_mm(walls: list[Wall], cell_mm: float = 100, close_mm: float = 2500, simplify_mm: float = 300, grow_mm: float = 150) -> list[tuple[float, float]] | None:
    """The outline of what the walls enclose (walls included), as a polygon in the walls' own millimetres, or None when the walls do not enclose a building (a wall missing leaks
    the outdoors in, and the enclosed part is then too small against the walls' bounding box to trust). Used for slabs in the 3D view; never for a quantity."""
    if not walls:
        return None
    xs = [w.start_mm for w in walls if w.orient == "h"] + [w.end_mm for w in walls if w.orient == "h"] + [w.centre_mm for w in walls if w.orient == "v"]
    ys = [w.start_mm for w in walls if w.orient == "v"] + [w.end_mm for w in walls if w.orient == "v"] + [w.centre_mm for w in walls if w.orient == "h"]
    pad = 3000
    x0, y0 = min(xs) - pad, min(ys) - pad
    shifted = [Wall(w.orient, w.centre_mm - (y0 if w.orient == "h" else x0), w.start_mm - (x0 if w.orient == "h" else y0), w.end_mm - (x0 if w.orient == "h" else y0), w.thickness_mm) for w in walls]
    shape = (int((max(ys) - min(ys) + 2 * pad) / cell_mm) + 2, int((max(xs) - min(xs) + 2 * pad) / cell_mm) + 2)
    inside = (~_outdoors(shifted, shape, cell_mm, close_mm)).astype(np.uint8)
    k = max(3, int(1200 / cell_mm))  # stubs and wall ends that stick out of the building are thinner than 1.2 m: an opening removes them
    inside = cv2.morphologyEx(inside, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    g = int(grow_mm / cell_mm)  # a slab edge shows a little outside the wall faces
    if g:
        inside = cv2.dilate(inside, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * g + 1, 2 * g + 1)))
    contours, _ = cv2.findContours(inside, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) * cell_mm ** 2 < 0.35 * (max(xs) - min(xs)) * (max(ys) - min(ys)):
        return None
    c = cv2.approxPolyDP(c, simplify_mm / cell_mm, True)
    return [(float(p[0][0]) * cell_mm + x0, float(p[0][1]) * cell_mm + y0) for p in c]


def footprint_area_m2(walls: list[Wall], shape: tuple[int, int], mm_per_px: float, close_mm: float = 2500) -> float:
    """The area enclosed by the outer walls (walls included), in m2: everything that is not outdoors."""
    outdoors = _outdoors(walls, shape, mm_per_px, close_mm)
    return float((~outdoors).sum()) * (mm_per_px / 1000) ** 2


def extents_m(walls: list[Wall]) -> tuple[float, float]:
    """Overall length (x) and width (y) of the wall layout, in metres: the bounding box of every run. Deliberately strict: a run that overshoots the
    building (a grid or extension line merged into a wall) makes it too big, and that is how a bad reading is caught against the printed overall
    dimensions. The building size to report is `building_size_m`."""
    xs = [w.start_mm for w in walls if w.orient == "h"] + [w.end_mm for w in walls if w.orient == "h"] + [w.centre_mm for w in walls if w.orient == "v"]
    ys = [w.start_mm for w in walls if w.orient == "v"] + [w.end_mm for w in walls if w.orient == "v"] + [w.centre_mm for w in walls if w.orient == "h"]
    return (max(xs) - min(xs)) / 1000, (max(ys) - min(ys)) / 1000


def building_size_m(walls: list[Wall]) -> tuple[float, float]:
    """The building's size between its outermost joints (centre lines), which a run overshooting the building cannot inflate. Falls back to the
    bounding box when there are too few joints."""
    j = joint_extents_mm(walls)
    return (j[0] / 1000, j[1] / 1000) if j else extents_m(walls)


def external_fractions(walls: list[Wall], shape: tuple[int, int], mm_per_px: float, close_mm: float = 2500, margin_px: int = 3,
                       step_mm: float = 500) -> list[float]:
    """For each wall, the share of its length that has the outdoors on one side (see _outdoors). Sampling along the wall, not at one
    point, lets a long run that is partly a party wall and partly an outer wall be split fairly."""
    h, w = shape
    outdoors = _outdoors(walls, shape, mm_per_px, close_mm)
    out = []
    for wall in walls:
        c = wall.centre_mm / mm_per_px
        off = wall.thickness_mm / mm_per_px / 2 + margin_px
        n = max(1, int(wall.length_mm / step_mm))
        hits = 0
        for i in range(n):
            m = (wall.start_mm + (i + 0.5) * wall.length_mm / n) / mm_per_px
            pts = [(int(m), int(c - off)), (int(m), int(c + off))] if wall.orient == "h" else [(int(c - off), int(m)), (int(c + off), int(m))]
            hits += any(bool(outdoors[min(max(y, 0), h - 1), min(max(x, 0), w - 1)]) for x, y in pts)
        out.append(hits / n)
    return out


def junctions(walls: list[Wall], tol_mm: float = 150) -> int:
    """Count the ends of walls that butt into another wall (T and L joints). A butting end double-counts the other wall's thickness, so
    each one takes a deduction when the trench or blockwork girth is built from full runs."""
    n = 0
    for w in walls:
        for end in (w.start_mm, w.end_mm):
            for v in walls:
                if v is w or v.orient == w.orient:
                    continue
                along_ok = abs(end - v.centre_mm) <= v.thickness_mm / 2 + tol_mm
                across_ok = v.start_mm - tol_mm <= w.centre_mm <= v.end_mm + tol_mm
                if along_ok and across_ok:
                    n += 1
                    break
    return n


def joint_extents_mm(walls: list[Wall], tol_mm: float = 150) -> tuple[float, float] | None:
    """Building size from where walls actually meet: the bounding box of the points where a horizontal and a vertical run cross or touch.
    A dangling line that runs past the building (an extension or grid line merged into a wall) makes no joint, so it cannot inflate this."""
    pts = []
    for h in (w for w in walls if w.orient == "h"):
        for v in (w for w in walls if w.orient == "v"):
            if h.start_mm - tol_mm <= v.centre_mm <= h.end_mm + tol_mm and v.start_mm - tol_mm <= h.centre_mm <= v.end_mm + tol_mm:
                pts.append((v.centre_mm, h.centre_mm))
    if len(pts) < 4:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)
