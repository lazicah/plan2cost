"""Wall girth for one floor plan page, measured: the scale and grid come from the PDF, the walls from the page image, and the lengths
from the two together. No model is involved in the measuring; the agent uses the result and judges it."""
import tempfile

import cv2

from plan2cost.drawing.dims import dimension_tokens
from plan2cost.drawing.grid import calibrate, find_grid
from plan2cost.kit.pdf import render_pages
from plan2cost.drawing.walls_cv import extents_m, external_fractions, find_walls, footprint_area_m2, junctions


# Walls are drawn at a fixed width on paper whatever the sheet's scale (plan2's 230mm wall is 5.27 pt on both its sheets), so the accepted face
# spacing is set in points and converted with the sheet's own scale. Class names are the nominal block thicknesses.
THICKNESS_WINDOWS_PT = {100: (1.9, 2.9), 150: (2.9, 4.5), 230: (4.6, 6.0)}


def measure_walls(pdf: str, page: int, dpi: int = 150, margin_mm: float = 2500) -> dict:
    """The older measurement tuned to one drawing style (a vector PDF page with a grid and a text layer: the scale from the grid and the printed dimensions, the walls from the rendered page). It is the last fallback, used only when neither the vector nor the raster route can read a page, and its result is flagged low confidence."""
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


def vector_scale(pdf: str, page: int, pg, lines, stated_denominator: float | None = None) -> tuple[float | None, str]:
    """Scale in mm per point, best source first. Each source says how it was found so the caller can state its confidence."""
    d = vector_scale_detail(pdf, page, pg, lines, stated_denominator)
    return d["mm_per_pt"], d["basis"]


def vector_scale_detail(pdf: str, page: int, pg, lines, stated_denominator: float | None = None) -> dict:
    """The same, with the evidence kept: which method, how many printed dimensions voted and how strongly they agreed."""
    from plan2cost.drawing.scale import fit_scale

    from plan2cost.kit.pdf import page_text
    from plan2cost.drawing.scale import stated_scale

    toks = dimension_tokens(pdf, page)
    stated_denominator = stated_denominator or stated_scale(page_text(pdf, page))
    t = fit_scale(toks, pg.segs, lines, stated_denominator)
    if t["mm_per_pt"] and t["votes"] >= 8 and t["agree"] >= 0.25 and t["dominance"] >= 2:
        return {"mm_per_pt": t["mm_per_pt"], "method": "printed dimensions against the lines they measure", "votes": t["votes"], "agree": t["agree"],
                "dominance": t["dominance"], "stated_denominator": stated_denominator,
                "basis": f"printed dimensions against the lines they measure ({t['votes']} dimensions, {int(t['agree'] * 100)}% agree)"}
    grid = calibrate(find_grid(pdf, page), [x.value for x in toks])
    if grid.mm_per_pt and len(grid.verticals) >= 2 and len(grid.horizontals) >= 2:
        return {"mm_per_pt": grid.mm_per_pt, "method": "grid bubbles against printed chains", "stated_denominator": stated_denominator,
                "basis": grid.scale_basis + " (grid bubbles; about 2% accuracy)"}
    from plan2cost.drawing.scale import scale_from_wall_thickness

    w = scale_from_wall_thickness(lines, stated_denominator)
    if w.get("mm_per_pt"):
        return {"mm_per_pt": w["mm_per_pt"], "method": "wall thickness with the stated scale", "stated_denominator": stated_denominator, "basis": w["basis"]}
    return {"mm_per_pt": None, "method": "none", "basis": ""}


def measure_walls_vector(pdf: str, page: int, mm_per_pt: float | None = None, stated_denominator: float | None = None, mask_mm_per_px: float = 50.0, keep: bool = False) -> dict:
    """The exact route for a plan drawn as vectors: same result shape as measure_walls, from face lines instead of pixels. The scale is
    read from the drawing (or given, e.g. from dimensions the model read); the wall weight and the building cluster are found, not set."""
    from plan2cost.drawing.vector import read_page
    from plan2cost.drawing.vector_walls import axis_lines, find_walls_vector
    from plan2cost.drawing.walls_cv import girth_by_thickness

    pg = read_page(pdf, page)
    lines = axis_lines(pg.segs)
    if len(lines) < 50:
        return {"error": "This page has too little vector line work (a raster plan?).", "confidence": "none"}
    basis, detail = "given", {"method": "given", "basis": "given"}
    if not mm_per_pt:
        detail = vector_scale_detail(pdf, page, pg, lines, stated_denominator)
        mm_per_pt, basis = detail["mm_per_pt"], detail["basis"]
    if not mm_per_pt:
        return {"error": "No scale could be read from this page; give one from printed dimensions.", "confidence": "none"}
    walls, info = find_walls_vector(lines, mm_per_pt)
    if not walls:
        return {"error": "No walls were found on this page.", "confidence": "none"}
    shape = (int(pg.height * mm_per_pt / mask_mm_per_px) + 2, int(pg.width * mm_per_pt / mask_mm_per_px) + 2)
    fr = external_fractions(walls, shape, mask_mm_per_px)
    total = sum(w.length_mm for w in walls) / 1000
    ext = sum(w.length_mm * f for w, f in zip(walls, fr)) / 1000
    length, width = extents_m(walls)
    return {"source": "vector", "scale": basis, "mm_per_pt": mm_per_pt, "wall_weight_pt": info["wall_weight"], "length_m": round(length, 2), "width_m": round(width, 2),
            "walls": len(walls), "total_m": round(total, 2), "external_m": round(ext, 2), "internal_m": round(total - ext, 2),
            "junction_ends": junctions(walls), "by_thickness_m": girth_by_thickness(walls),
            **({"_walls": walls, "_fractions": fr, "_unit": "pt", "_mm_per_unit": mm_per_pt, "_calibration": detail} if keep else {})}
