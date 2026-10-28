"""Wall girth for one floor plan page, measured: the scale and grid come from the PDF, the walls from the page image, and the lengths
from the two together. No model is involved in the measuring; the agent uses the result and judges it."""
import tempfile

import cv2

from plan2cost.dims import dimension_tokens
from plan2cost.grid import calibrate, find_grid
from plan2cost.pdf import render_pages
from plan2cost.walls_cv import extents_m, external_fractions, find_walls, footprint_area_m2, junctions


# Walls are drawn at a fixed width on paper whatever the sheet's scale (plan2's 230mm wall is 5.27 pt on both its sheets), so the accepted face
# spacing is set in points and converted with the sheet's own scale. Class names are the nominal block thicknesses.
THICKNESS_WINDOWS_PT = {100: (1.9, 2.9), 150: (2.9, 4.5), 230: (4.6, 6.0)}


def measure_walls(pdf: str, page: int, dpi: int = 150, margin_mm: float = 2500) -> dict:
    grid = calibrate(find_grid(pdf, page), [t.value for t in dimension_tokens(pdf, page)])
    if grid.mm_per_pt is None or len(grid.verticals) < 2 or len(grid.horizontals) < 2:
        return {"error": "No grid and scale could be read from this page's text layer (a scanned plan?).", "confidence": "none"}
    img = render_pages(pdf, [page], tempfile.mkdtemp(), dpi=dpi)[0]
    gray = cv2.imread(img, 0)
    k = dpi / 72
    mm_px = grid.mm_per_pt / k
    m = margin_mm / grid.mm_per_pt
    xs = [g.pos_pts for g in grid.verticals]
    ys = [g.pos_pts for g in grid.horizontals]
    region = tuple(int(v * k) for v in (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m))
    windows = {n: (lo * grid.mm_per_pt, hi * grid.mm_per_pt) for n, (lo, hi) in THICKNESS_WINDOWS_PT.items()}
    walls = find_walls(gray, mm_px, (max(region[0], 0), max(region[1], 0), region[2], region[3]), windows=windows)
    if not walls:
        return {"error": "No walls were found on this page.", "confidence": "none"}
    fr = external_fractions(walls, gray.shape, mm_px)
    total = sum(w.length_mm for w in walls) / 1000
    ext = sum(w.length_mm * f for w, f in zip(walls, fr)) / 1000
    length, width = extents_m(walls)
    return {"scale": grid.scale_basis, "length_m": round(length, 2), "width_m": round(width, 2),
            "footprint_m2": round(footprint_area_m2(walls, gray.shape, mm_px), 1), "walls": len(walls), "total_m": round(total, 2), "external_m": round(ext, 2),
            "internal_m": round(total - ext, 2), "junction_ends": junctions(walls),
            "by_thickness_m": {int(t): round(sum(w.length_mm for w in walls if abs(w.thickness_mm - t) < 1) / 1000, 2) for t in {w.thickness_mm for w in walls}},
            "confidence": "medium"}
