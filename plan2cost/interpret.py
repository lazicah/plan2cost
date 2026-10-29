"""Drawing interpretation: one entry point for any plan, whatever the source. The source (vector PDF page or raster image) only changes how
line work is read; the scale, the wall bands, the external/internal split and the checks are the same. Code measures; the model reads
the few printed facts code cannot (stated scale, overall dimensions) and judges candidates; the result says how much to trust it."""
import collections
import math
from collections import Counter

import cv2
import numpy as np

from plan2cost.raster_lines import vectorise
from plan2cost.vector_walls import Line, find_walls_vector
from plan2cost.walls_cv import external_fractions, extents_m, girth_by_thickness, junctions

STANDARD_MM = 225  # the unit the ruler is first read in; the printed overall dimensions then decide the true scale
BLOCK_SIZES_MM = (100, 150, 200, 225, 230, 300)  # standard wall thicknesses; the dimension fit only chooses among them


def bin_width(w: float) -> float:
    """Raster stroke widths wobble by a pixel or two; group them in half-octaves so a weight is a stable key."""
    return round(2 ** (round(math.log2(max(w, 1.0)) * 2) / 2), 1)


def ruler_candidates(lines: list[Line], min_len_px: float = 80, max_gap_px: float = 150, min_w_px: float = 3.0, top: int = 3) -> list[tuple[float, float, str]]:
    """Readings of the dominant wall thickness in pixels, strongest first, as (pixels, evidence, kind). Evidence is the length of line work
    that supports it. 'pair': the spacing of long parallel heavy lines of similar weight (walls drawn as two faces). 'bar': the width of long
    solid bands (walls drawn as one band). The caller tests each against independent facts; none is trusted on its own."""
    heavy = sorted((l for l in lines if l.length >= min_len_px and l.w >= min_w_px), key=lambda l: (l.orient, l.pos))
    gaps: collections.Counter = collections.Counter()
    for i, a in enumerate(heavy):
        for b in heavy[i + 1:]:
            if b.orient != a.orient or b.pos - a.pos > max_gap_px:
                break
            ov = min(a.b, b.b) - max(a.a, b.a)
            if b.pos - a.pos > min_w_px and ov > min_len_px * 0.7 and max(a.w, b.w) <= 1.8 * min(a.w, b.w):
                gaps[round((b.pos - a.pos) / 2) * 2] += ov
    bars: collections.Counter = collections.Counter()
    for l in lines:
        if l.length >= 4 * min_len_px and l.w >= 3 * min_w_px:
            bars[round(l.w / 4) * 4] += l.length
    out = [(float(g), float(e), "pair") for g, e in gaps.most_common(top) if e >= 600] + [(float(w), float(e), "bar") for w, e in bars.most_common(top) if e >= 600]
    return sorted(out, key=lambda c: -c[1])


def scale_from_overall(extent_a_mm: float, extent_b_mm: float, printed_mm: list[float], tol: float = 0.045) -> tuple[float, float] | None:
    """Find the factor that makes the measured extents (at the first-pass scale) equal two printed overall values, one per axis. Returns the
    factor to apply to the first-pass scale and how closely the two axes agree; None if no pair of printed values fits both axes."""
    best = None
    for va in printed_mm:
        for vb in printed_mm:
            fa, fb = va / extent_a_mm, vb / extent_b_mm
            if abs(fa - fb) <= tol * max(fa, fb):
                err = abs(fa - fb) / max(fa, fb)
                if best is None or err < best[1]:
                    best = ((fa + fb) / 2, err)
    return best


def _run(lines: list[Line], px: float, facts: dict | None, primitive: str = "pair"):
    """One reading of the wall thickness, taken all the way through: walls at the first-pass scale, their extents against the printed overall
    dimensions (which pick the block size), then the walls again at the scale that block size fixes. Returns None when the reading breaks down.
    A reading is only believable if the walls at its final scale still form a building."""
    s0 = STANDARD_MM / px
    walls, info = find_walls_vector(lines, s0, primitive=primitive)
    hs, vs = [w for w in walls if w.orient == "h"], [w for w in walls if w.orient == "v"]
    block, err = STANDARD_MM, None
    if hs and vs:
        ext_x = max(w.end_mm for w in hs) - min(w.start_mm for w in hs)
        ext_y = max(w.end_mm for w in vs) - min(w.start_mm for w in vs)
        vals = [float(v) for v in (facts or {}).get("horizontal_mm", []) + (facts or {}).get("vertical_mm", []) if v]
        fit = scale_from_overall(ext_x, ext_y, vals) if vals else None
        if fit:
            t = _block_for(fit[0])
            if t:
                block, err = t, fit[1]
    s = block / px
    if block != STANDARD_MM or not walls:
        walls, info = find_walls_vector(lines, s, primitive=primitive)
    total = sum(w.length_mm for w in walls) / 1000
    joints = junctions(walls) if walls else 0
    return {"walls": walls, "info": info, "block": block, "err": err, "s": s, "total": total, "joints": joints, "building": total >= 30 and joints >= 8}


def _block_for(factor: float, tol: float = 0.07) -> int | None:
    """The standard block thickness the dimension fit points to (the ruler read as 225mm times the fitted factor), or None when the fit
    implies a wall thickness that is not a block size, which means this reading of the ruler is not the wall."""
    implied = STANDARD_MM * factor
    t = min(BLOCK_SIZES_MM, key=lambda b: abs(b - implied))
    return t if abs(t - implied) / t <= tol else None


def interpret_image(path: str, facts: dict | None = None, dark: int = 150) -> dict:
    gray = cv2.imread(path, 0)
    lines = vectorise(gray, dark=dark, min_len_px=30)
    for l in lines:
        l.w = bin_width(l.w)
    cands = ruler_candidates(lines)
    if not cands:
        return {"error": "No regular wall bands could be found in this image.", "confidence": "none"}
    tried, results = [], []
    for px, evidence, kind in cands:
        r = _run(lines, px, facts, kind)
        r.update(px=px, kind=kind, evidence=evidence)
        results.append(r)
        tried.append(f"{kind} {px:.0f}px: {len(r['walls'])} walls, {r['total']:.0f} m, {r['joints']} joints, " + (f"fit error {r['err'] * 100:.1f}% block {r['block']}" if r["err"] is not None else "no dimension fit"))
    # believable readings first (a building at the final scale); among them the best dimension fit, else the best-supported reading
    pool = [r for r in results if r["building"]] or results
    fitted = [r for r in pool if r["err"] is not None]
    best = min(fitted, key=lambda r: r["err"]) if fitted else pool[0]
    notes = []
    if best["err"] is not None:
        scale_basis = f"printed overall dimensions fit a {best['block']}mm wall of {best['px']:.0f}px (axes agree to {best['err'] * 100:.1f}%)"
    else:
        scale_basis = f"assumed the dominant wall {best['kind']} ({best['px']:.0f}px) is {STANDARD_MM}mm"
        notes.append("no printed overall dimension fits the measured building on both axes; scale is a guess" if facts else "no printed dimensions were read; scale is a guess")
    walls, info, s = best["walls"], best["info"], best["s"]
    if not walls:
        return {"error": "No walls were found in this image.", "confidence": "none", "tried": tried}
    h, w_ = gray.shape
    px_mask = 50.0
    shape = (int(h * s / px_mask) + 2, int(w_ * s / px_mask) + 2)
    fr = external_fractions(walls, shape, px_mask)
    total = sum(x.length_mm for x in walls) / 1000
    ext = sum(x.length_mm * f for x, f in zip(walls, fr)) / 1000
    length, width = extents_m(walls)
    return {"source": "raster", "scale": scale_basis, "mm_per_px": round(s, 3), "ruler": [best["px"], best["kind"], best["block"]], "wall_weight_px": info["wall_weight"],
            "length_m": round(length, 2), "width_m": round(width, 2), "walls": len(walls), "total_m": round(total, 2), "external_m": round(ext, 2),
            "internal_m": round(total - ext, 2), "junction_ends": junctions(walls), "by_thickness_m": girth_by_thickness(walls), "building": best["building"],
            "notes": notes, "tried": tried}
