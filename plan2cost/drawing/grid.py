"""Structural grid from a drawing's text layer: the numbered and lettered bubbles give each grid line's position on the sheet, and the
printed dimension chains calibrate sheet points to millimetres. The wall walk then measures bay by bay, so lengths come from the drawing
and never from the model. Vector PDFs only; a raster drawing has no text layer and falls back to the model reading the chains."""
import re
import subprocess
from dataclasses import dataclass

from plan2cost.kit.pdf import pdftoppm

PT_MM = 25.4 / 72  # one PDF point on paper, in mm


@dataclass
class GridLine:
    label: str
    pos_pts: float  # x for numbered (vertical) lines, y for lettered (horizontal) lines
    axis: str  # "x" or "y"


@dataclass
class Grid:
    verticals: list[GridLine]  # numbered, ordered left to right
    horizontals: list[GridLine]  # lettered, ordered top to bottom
    mm_per_pt: float | None = None
    scale_basis: str = ""

    def bays(self, axis: str) -> list[tuple[str, str, float]]:
        """(from, to, length_mm) between neighbouring grid lines along an axis."""
        lines = self.verticals if axis == "x" else self.horizontals
        if self.mm_per_pt is None:
            return []
        return [(a.label, b.label, round((b.pos_pts - a.pos_pts) * self.mm_per_pt)) for a, b in zip(lines, lines[1:])]


def _words(pdf: str, page: int) -> list[tuple[float, float, float, float, str]]:
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    html = subprocess.run([exe, "-f", str(page), "-l", str(page), "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    return [(float(a), float(b), float(c), float(d), w) for a, b, c, d, w in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', html)]


def _aligned(tokens: list[tuple[float, float, str]], axis_key: int, tol: float = 4.0, min_n: int = 3) -> list[tuple[float, float, str]]:
    """The largest set of single-character tokens sharing one coordinate (a row or a column of bubbles)."""
    best: list = []
    for t in tokens:
        group = [u for u in tokens if abs(u[axis_key] - t[axis_key]) <= tol]
        labels = {u[2] for u in group}
        if len(labels) == len(group) and len(group) > len(best):  # every label once: a real row, not scattered repeats
            best = group
    return best if len(best) >= min_n else []


def find_grid(pdf: str, page: int, scale: float | None = None) -> Grid:
    """Locate the bubbles. `scale` is the drawing scale denominator (100 for 1:100); with it, points convert to mm directly."""
    singles = [((x0 + x1) / 2, (y0 + y1) / 2, w) for x0, y0, x1, y1, w in _words(pdf, page) if re.fullmatch(r"[A-Z0-9]", w)]
    nums = [t for t in singles if t[2].isdigit()]
    letters = [t for t in singles if t[2].isalpha()]
    row = sorted(_aligned(nums, axis_key=1), key=lambda t: t[0])  # same y, different x
    col = sorted(_aligned(letters, axis_key=0), key=lambda t: t[1])  # same x, different y
    grid = Grid([GridLine(t[2], t[0], "x") for t in row], [GridLine(t[2], t[1], "y") for t in col])
    if scale:
        grid.mm_per_pt, grid.scale_basis = PT_MM * scale, f"stated scale 1:{int(scale)}"
    return grid


def calibrate(grid: Grid, chain_values_mm: list[int], tolerance: float = 0.02) -> Grid:
    """Without a stated scale, take the scale from the printed chain dimensions: the one that makes the most grid bays match a
    printed value to within the tolerance. A scale that matches fewer than three bays is not trusted."""
    pts = [b.pos_pts - a.pos_pts for lines in (grid.verticals, grid.horizontals) for a, b in zip(lines, lines[1:])]
    best, best_hits = None, 0
    for d in pts:
        for v in set(chain_values_mm):
            s = v / d if d else 0
            hits = sum(1 for p in pts if any(abs(p * s - c) <= tolerance * c for c in chain_values_mm))
            if hits > best_hits:
                best, best_hits = s, hits
    if best and best_hits >= 3:
        grid.mm_per_pt, grid.scale_basis = best, f"fitted to printed chain dimensions ({best_hits} bays match)"
    return grid
