"""Drawing interpretation: one entry point for any plan, whatever the source. The source (vector PDF page or raster image) only changes how
line work is read; the scale, the wall bands, the external/internal split and the checks are the same. Code measures; the model reads
the few printed facts code cannot (stated scale, overall dimensions) and judges candidates; the result says how much to trust it."""
import collections
import math

import cv2

from plan2cost.drawing.raster_lines import bar_lines, bar_widths, vectorise_multi
from plan2cost.drawing.vector_walls import Line, find_walls_vector
from plan2cost.drawing.walls_cv import external_fractions, extents_m, girth_by_thickness, joint_extents_mm, junctions

STANDARD_MM = 225  # the unit the ruler is first read in; the printed overall dimensions then decide the true scale
BLOCK_SIZES_MM = (100, 150, 200, 225, 230, 300)  # standard wall thicknesses; the dimension fit only chooses among them


def bin_width(w: float) -> float:
    """Raster stroke widths wobble by a pixel or two; group them in half-octaves so a weight is a stable key."""
    return round(2 ** (round(math.log2(max(w, 1.0)) * 2) / 2), 1)


def _clusters(counter: collections.Counter, tol: float = 0.12, top: int = 6) -> list[tuple[float, float]]:
    """Group neighbouring values (within `tol` of each other) into one reading each: (weighted centre, total evidence), strongest first."""
    items = dict(counter)
    out = []
    while items and len(out) < top:
        key = max(items, key=items.get)
        near = [k for k in items if abs(k - key) <= tol * key]
        evidence = sum(items[k] for k in near)
        centre = sum(k * items[k] for k in near) / evidence
        out.append((centre, float(evidence)))
        for k in near:
            del items[k]
    return out


def ruler_candidates(lines: list[Line], min_len_px: float = 80, min_gap_px: float = 8, max_gap_px: float = 100, min_w_px: float = 3.0, top: int = 6) -> list[tuple[float, float, str]]:
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
            if b.pos - a.pos >= min_gap_px and ov > min_len_px * 0.7 and max(a.w, b.w) <= 1.8 * min(a.w, b.w):
                gaps[round(b.pos - a.pos)] += ov
    out = [(g, e, "pair") for g, e in _clusters(gaps, top=top) if e >= 600]
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
    walls, info = find_walls_vector(lines, s0, primitive=primitive, min_length_m=25, min_joints=4, dominant_bar=px if primitive == "bar" else None)
    hs, vs = [w for w in walls if w.orient == "h"], [w for w in walls if w.orient == "v"]
    block, err, fitted_s = STANDARD_MM, None, None
    options = []  # building size by three definitions; a dangling line inflates the raw ends, a split corner shrinks the joints
    if hs and vs:
        options.append((max(w.end_mm for w in hs) - min(w.start_mm for w in hs), max(w.end_mm for w in vs) - min(w.start_mm for w in vs)))
        je = joint_extents_mm(walls)
        if je:
            options += [(je[0] + STANDARD_MM, je[1] + STANDARD_MM), je]
    vals = [float(v) for v in (facts or {}).get("horizontal_mm", []) + (facts or {}).get("vertical_mm", []) if v]
    fits = [f for f in (scale_from_overall(ex, ey, vals) for ex, ey in options) if f] if vals else []
    if fits:
        fit = min(fits, key=lambda f: f[1])
        t = _block_for(fit[0], 0.14 if primitive == "bar" else 0.07)
        if t and t >= 150:  # the dominant wall of a building is not a 100mm partition
            block, err = t, fit[1]
            if primitive == "bar":  # a bar is drawn with its outline, so its width overstates the wall; the dimension fit is the better scale
                fitted_s = s0 * fit[0]
    s = fitted_s or block / px
    if block != STANDARD_MM or fitted_s or not walls:
        walls, info = find_walls_vector(lines, s, primitive=primitive, min_length_m=25, min_joints=4, dominant_bar=px if primitive == "bar" else None)
    total = sum(w.length_mm for w in walls) / 1000
    joints = junctions(walls) if walls else 0
    return {"walls": walls, "info": info, "block": block, "err": err, "s": s, "total": total, "joints": joints, "building": total >= 30 and joints >= 6}


def _block_for(factor: float, tol: float = 0.07) -> int | None:  # a solid bar is drawn with its outline, so callers allow more for bars
    """The standard block thickness the dimension fit points to (the ruler read as 225mm times the fitted factor), or None when the fit
    implies a wall thickness that is not a block size, which means this reading of the ruler is not the wall."""
    implied = STANDARD_MM * factor
    t = min(BLOCK_SIZES_MM, key=lambda b: abs(b - implied))
    return t if abs(t - implied) / t <= tol else None


def interpret_image(path: str, facts: dict | None = None, dark: int = 150, keep_walls: bool = False) -> dict:
    """Read a raster plan (a photo or a scan): find the wall thickness from the line work, try each candidate scale against the model-read page facts (stated scale, overall dimensions) and keep the best believable reading. Returns the totals, the scale basis and the confidence; with `keep_walls` the walls and their outdoors share are kept for the drawing model."""
    gray = cv2.imread(path, 0)
    lines = vectorise_multi(gray, dark=dark)
    for l in lines:
        l.raw, l.w = l.w, bin_width(l.w)  # keep the measured thickness; the binned width is only the weight class
    cands = ruler_candidates(lines) + [(w, e, "bar") for w, e in _clusters(bar_widths(gray, dark=dark), tol=0.15, top=4) if e >= 600]
    cands.sort(key=lambda c: -c[1])
    if not cands:
        return {"error": "No regular wall bands could be found in this image.", "confidence": "none"}
    tried, results = [], []
    for px, evidence, kind in cands:
        r = _run(bar_lines(gray, px, dark) if kind == "bar" else lines, px, facts, kind)
        r.update(px=px, kind=kind, evidence=evidence)
        results.append(r)
        tried.append(f"{kind} {px:.0f}px: {len(r['walls'])} walls, {r['total']:.0f} m, {r['joints']} joints, " + (f"fit error {r['err'] * 100:.1f}% block {r['block']}" if r["err"] is not None else "no dimension fit"))
    # believable readings first (a building at the final scale); among them the best dimension fit, else the best-supported reading
    pool = [r for r in results if r["building"]] or results
    fitted = [r for r in pool if r["err"] is not None]
    good = [r for r in fitted if r["err"] <= 0.02]  # several readings can fit the dimensions by chance: of the good fits, the best-supported one
    pairs_ok = [r for r in good if r["kind"] == "pair"]  # a "bar" reading of double-line walls is just their thick faces seen one by one
    best = max(pairs_ok or good, key=lambda r: r["evidence"]) if good else min(fitted, key=lambda r: r["err"]) if fitted else pool[0]
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
            "notes": notes, "tried": tried,
            **({"_walls": walls, "_fractions": fr, "_unit": "px", "_mm_per_unit": s, "_image": path, "_calibration": {
                "method": "wall thickness as a ruler, block size chosen by the printed overall dimensions" if best["err"] is not None else "wall thickness assumed to be 225mm",
                "kind": best["kind"], "ruler_px": best["px"], "block_mm": best["block"], "fit_error": best["err"], "basis": scale_basis, "readings": tried,
                "printed_overall_mm": (facts or {}).get("horizontal_mm", []) + (facts or {}).get("vertical_mm", []), "stated_denominator": (facts or {}).get("scale")}}
               if keep_walls else {})}


def extents_match_printed(length_m: float, width_m: float, printed_mm: list[int], tol: float = 0.07) -> bool:
    """Do the measured building extents equal two printed dimensions (one per axis, either order)? Outer-to-outer and grid-to-grid strings
    differ by a wall thickness at most, so a few percent is allowed. A network of grid or extension lines does not match."""
    vals = [v / 1000 for v in printed_mm if v >= 3000]
    return any(abs(a - length_m) <= tol * length_m and abs(b - width_m) <= tol * width_m for a in vals for b in vals) or \
        any(abs(a - width_m) <= tol * width_m and abs(b - length_m) <= tol * length_m for a in vals for b in vals)


def interpret_page(pdf: str, page: int, scratch: str | None = None, keep: bool = False) -> dict:
    """Wall measurement for one plan page of a PDF, by the best route the page allows. Vector line work is read exactly; a raster page is
    rendered and read through the image route (the model reads the printed overall dimensions to fix the scale); a page neither route can
    read falls back to the older measurement tuned to one drawing style, flagged as low confidence. `confidence` says how far to trust it."""
    import tempfile

    from plan2cost.drawing.measure import measure_walls, measure_walls_vector
    from plan2cost.facts.page_facts import read_page_facts
    from plan2cost.kit.pdf import render_pages

    from plan2cost.drawing.dims import dimension_tokens

    v = measure_walls_vector(pdf, page, keep=keep)
    if "error" not in v and v["total_m"] >= 25 and not extents_match_printed(v["length_m"], v["width_m"], [t.value for t in dimension_tokens(pdf, page)]):
        v = {"error": "the measured building does not match the printed overall dimensions (probably not the walls)", "was": v["total_m"]}
    if "error" not in v and v["total_m"] >= 25:
        from_dims = v["scale"].startswith("printed dimensions")
        v["route"] = "vector"
        v["confidence"] = "high" if from_dims else "medium"
        v["notes"] = [] if from_dims else ["the scale was inferred from the wall thickness and the stated scale, not from printed dimensions"]
        return v
    scratch = scratch or tempfile.mkdtemp()
    img = render_pages(pdf, [page], scratch, dpi=250)[0]
    try:
        facts = read_page_facts(img)
    except Exception as e:  # no model available: the image route can still run, with a guessed scale
        facts = None
        facts_note = f"the model could not read the printed dimensions ({type(e).__name__})"
    else:
        facts_note = None
    r = interpret_image(img, facts, keep_walls=keep)
    if "error" not in r and r["total_m"] >= 25:
        r["route"] = "raster"
        r["_image"] = img
        if "_calibration" in r:
            r["_calibration"]["dpi"] = 250
        fitted = "printed overall dimensions fit" in r["scale"]
        r["confidence"] = "medium" if fitted and r.get("building") else "low"
        if facts_note:
            r["notes"].append(facts_note)
        return r
    old = measure_walls(pdf, page)
    if "error" not in old:
        old.update(route="raster-legacy", confidence="low", notes=["measured by the older detector tuned to one drawing style"])
        return old
    return {"error": "No route could read the walls on this page.", "confidence": "none", "vector": v.get("error"), "raster": r.get("error")}
