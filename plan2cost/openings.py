"""Doors, windows and openings tied to the walls they are in. Code finds the candidates (the stretches of a wall where both faces are broken),
measures their width from the drawing, and reads tags from the text layer where there is one; the model looks at a crop of each candidate and says
what it is (door, window, a bare opening, or not an opening) and reads the tag printed beside it. Whether an opening is external or internal comes
from the wall it sits in, and its size from the schedule type it is matched to, never from the model."""
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

import cv2

from plan2cost.drawing_model import DrawingModel, Element, Issue

TAG = re.compile(r"^(?:[A-Z]{1,3}\d{1,2}[A-Za-z]?)$")
MIN_MM, MAX_MM = 450, 3700  # narrower is a jamb or a break in a face line, wider is a gap in the detection

PROMPT = """This is a crop of a floor plan. A thick orange bar marks a gap that was found in a wall. Say what the gap is:
- "door": a door leaf or a swing arc is drawn in or beside the gap;
- "window": frame or sill lines run across the gap, or it carries a window tag;
- "opening": an open gap in the wall with no door or window drawn (an arch, a pass-through, a doorway without a leaf);
- "not_opening": the bar is not on a gap in a wall (a stair, furniture, a wall end, a column, a text label, two walls meeting).
Also read the tag printed next to it if there is one (like W3, D2, SD1, AW1, TD2), exactly as printed, else null.
Judge only what you can see. Return only JSON: {"kind": "door|window|opening|not_opening", "tag": "W3" or null, "leaf": "single|double|sliding|none|unclear"}"""


def candidates(model: DrawingModel) -> list[dict]:
    """Every stretch of a wall where both faces are broken and that is a plausible opening width, with its place on the sheet."""
    out = []
    for e in model.walls():
        for a, b in e.gaps_mm:
            if not MIN_MM <= b - a <= MAX_MM:
                continue
            x0, y0, x1, y1 = (a, e.y0_mm, b, e.y0_mm) if e.orient == "h" else (e.x0_mm, a, e.x0_mm, b)
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(b - a), "external": e.external_share >= 0.5,
                        "thickness": e.thickness_mm})
    return out


def _mm_per_pt(model: DrawingModel) -> float | None:
    """Millimetres of building to a point of the PDF page, or None when the model came from an image (no text layer to place)."""
    cal = model.calibrations[0]
    if cal.unit == "pt":
        return cal.mm_per_unit
    return cal.mm_per_unit * cal.detail["dpi"] / 72 if cal.detail.get("dpi") else None


def dimension_candidates(model: DrawingModel, pdf: str, page: int, widths_mm: set, have: list, reach_mm: float = 4500) -> list[dict]:
    """A printed dimension equal to a schedule width marks a place where an opening may be: put a candidate on the nearest wall (running the
    same way as the dimension chain) at that position. Walls where a gap was already found at that place are not doubled up."""
    from plan2cost.dims import dimension_tokens

    k = _mm_per_pt(model)
    if not k or not widths_mm:
        return []
    out = []
    for t in dimension_tokens(pdf, page):
        if not any(abs(t.value - w) <= 5 for w in widths_mm):
            continue
        along, across = t.along * k, t.across * k
        orient = "v" if t.vertical else "h"  # a vertical chain dimensions openings in a vertical wall
        walls = [e for e in model.walls() if e.orient == orient]
        best = None
        for e in walls:
            lo, hi = (e.x0_mm, e.x1_mm) if orient == "h" else (e.y0_mm, e.y1_mm)
            pos = e.y0_mm if orient == "h" else e.x0_mm
            if lo - 100 <= along <= hi + 100 and abs(pos - across) <= reach_mm:
                d = abs(pos - across) - (400 if e.external_share >= 0.5 else 0)  # the chains outside the building dimension its outer walls
                if best is None or d < best[0]:
                    best = (d, e)
        if not best:
            continue
        e = best[1]
        a, b = along - t.value / 2, along + t.value / 2
        if any(h["wall"] == e.id and abs((h["x0"] + h["x1"] + h["y0"] + h["y1"]) / 2 - (a + b) / 2 - (e.y0_mm if orient == "h" else e.x0_mm)) < 450 for h in have):
            continue
        x0, y0, x1, y1 = (a, e.y0_mm, b, e.y0_mm) if orient == "h" else (e.x0_mm, a, e.x0_mm, b)
        out.append({"wall": e.id, "orient": orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": int(t.value), "external": e.external_share >= 0.5, "thickness": e.thickness_mm,
                    "source": "printed dimension"})
    uniq: list[dict] = []  # the same dimension is often printed on two chains
    for c in out:
        if not any(u["wall"] == c["wall"] and abs(u["x0"] - c["x0"]) + abs(u["y0"] - c["y0"]) < 300 for u in uniq):
            uniq.append(c)
    return uniq


def text_tags(pdf: str, page: int, model: DrawingModel) -> list[tuple[str, float, float]]:
    """Tags like W3 or D2 from the page's text layer with their position in the model's frame (mm). Empty for an image or a page with no text."""
    import subprocess

    from plan2cost.pdf import pdftoppm

    mm_per_pt = _mm_per_pt(model)
    if not mm_per_pt:
        return []
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    html = subprocess.run([exe, "-f", str(page), "-l", str(page), "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    out = []
    for x0, y0, x1, y1, w in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)</word>', html):
        if TAG.match(w):
            out.append((w, (float(x0) + float(x1)) / 2 * mm_per_pt, (float(y0) + float(y1)) / 2 * mm_per_pt))
    return out


def _crop(img, scale: float, c: dict, out_dir: str, i: int, side_mm: float = 3600) -> str:
    cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
    half = max(side_mm, c["width_mm"] + 2000) / 2
    x0, y0, x1, y1 = int((cx - half) * scale), int((cy - half) * scale), int((cx + half) * scale), int((cy + half) * scale)
    h, w = img.shape[:2]
    crop = img[max(y0, 0):min(y1, h), max(x0, 0):min(x1, w)].copy()
    ox, oy = max(x0, 0), max(y0, 0)
    if crop.size == 0:
        return ""
    cv2.line(crop, (int(c["x0"] * scale) - ox, int(c["y0"] * scale) - oy), (int(c["x1"] * scale) - ox, int(c["y1"] * scale) - oy), (0, 140, 255), max(5, crop.shape[0] // 90))
    k = 640 / max(crop.shape[:2])
    crop = cv2.resize(crop, (int(crop.shape[1] * k), int(crop.shape[0] * k)), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    path = f"{out_dir}/gap{i}.jpg"
    cv2.imwrite(path, crop)
    return path


def _verify(path: str) -> dict:
    from plan2cost.client import image_part
    from plan2cost.document import _chat

    if not path:
        return {"kind": "not_opening", "tag": None}
    try:
        return _chat([{"type": "text", "text": PROMPT}, image_part(path)])
    except Exception as e:
        return {"kind": "unverified", "tag": None, "error": type(e).__name__}


def locate_openings(model: DrawingModel, img, scale: float, pdf: str | None = None, page: int | None = None, schedule: list | None = None, workers: int = 6) -> list[Issue]:
    """Find the openings on the floor, add them to the model (door D-001, window WN-001, opening O-001), tie each to its wall and to a schedule
    type, and return the issues the reconciliation raises. `schedule` is the opening types read from the schedule pages (label, width_m, height_m,
    count, kind); the model's walls decide external or internal."""
    cands = candidates(model)
    for c in cands:
        c["source"] = "gap in the wall"
    if pdf and page and schedule:
        cands += dimension_candidates(model, pdf, page, {round(s["width_m"] * 1000) for s in schedule}, cands)
    tags = text_tags(pdf, page, model) if pdf and page else []
    out_dir = tempfile.mkdtemp()
    paths = [_crop(img, scale, c, out_dir, i) for i, c in enumerate(cands)]
    with ThreadPoolExecutor(workers) as ex:
        verdicts = list(ex.map(_verify, paths))
    labels = {s["label"].upper(): s for s in (schedule or [])}
    made, issues, dropped, unverified = [], [], 0, 0
    kept = []
    for c, v in zip(cands, verdicts):
        kind = v.get("kind")
        if kind == "unverified":
            unverified += 1
        elif kind not in ("door", "window", "opening"):
            dropped += 1
        else:
            kept.append((c, v))
    # each printed tag belongs to the one gap nearest to it (within 1.8 m); a tag is never shared between two openings
    pairs = sorted((((tx - (c["x0"] + c["x1"]) / 2) ** 2 + (ty - (c["y0"] + c["y1"]) / 2) ** 2) ** 0.5, gi, ti) for gi, (c, _) in enumerate(kept) for ti, (_, tx, ty) in enumerate(tags))
    gap_tag: dict = {}
    used_tags: set = set()
    for d, gi, ti in pairs:
        if d <= 1800 and gi not in gap_tag and ti not in used_tags:
            gap_tag[gi] = tags[ti][0]
            used_tags.add(ti)
    for gi, (c, v) in enumerate(kept):
        text_tag = gap_tag.get(gi)
        tag, how = (text_tag, "directly labelled (text layer)") if text_tag else ((v.get("tag") or "").strip().upper() or None, "directly labelled (read from the crop)")
        made.append({**c, "kind": v["kind"], "tag": tag, "how": how if tag else "inferred"})
    # a type the schedule knows, by tag; else by width when exactly one schedule type of that kind fits
    for m in made:
        if m["tag"] and m["tag"] in labels:
            m["mark"] = m["tag"]
            continue
        fit = [s for s in (schedule or []) if s["kind"] == m["kind"] and -0.30 * s["width_m"] * 1000 <= m["width_mm"] - s["width_m"] * 1000 <= 0.12 * s["width_m"] * 1000]  # a drawn gap is usually narrower than its type: the frame sits inside it if not m["tag"] else []
        if len({s["label"] for s in fit}) == 1:
            m["mark"], m["how"] = fit[0]["label"].upper(), "inferred (the only schedule type of that width)"
        else:
            m["mark"] = ""
            if m["tag"]:
                issues.append(Issue("tag_not_in_schedule", "warn", f"A {m['kind']} tagged {m['tag']} in {m['wall']} is not in the schedule.", [m["wall"]], "Check the tag against the schedule."))
    prefix = {"door": "D", "window": "WN", "opening": "O"}
    count = {k: 0 for k in prefix}
    for m in sorted(made, key=lambda m: (m["wall"], m["x0"] + m["y0"])):
        count[m["kind"]] += 1
        eid = f"{prefix[m['kind']]}-{count[m['kind']]:03d}"
        model.elements.append(Element(eid, m["kind"], "external" if m["external"] else "internal", model.page, model.floor, m["orient"], round(m["x0"], 1), round(m["y0"], 1),
                                      round(m["x1"], 1), round(m["y1"], 1), round(m["width_mm"] / 1000, 3), m["thickness"], evidence=m["how"] if m["mark"] else "inferred",
                                      confidence="medium" if m["mark"] else "low", parent=m["wall"], mark=m["mark"], width_mm=float(m["width_mm"]),
                                      notes=[] if m["tag"] else ["no tag could be read beside it"]))
    for o in model.openings():
        s = labels.get(o.mark)
        if s and abs(s["width_m"] * 1000 - o.width_mm) > 0.2 * s["width_m"] * 1000 and abs(s["width_m"] * 1000 - o.width_mm) > 150:
            issues.append(Issue("opening_width", "info", f"{o.id} ({o.mark}) measures {o.width_mm:.0f} mm on the drawing but the schedule says {s['width_m'] * 1000:.0f} mm.", [o.id],
                                "The drawn gap includes the frame; check only if the difference is large."))
    if unverified:
        issues.append(Issue("openings_unverified", "warn", f"{unverified} candidate openings could not be checked by the model and are left out.", [], "Run the check again."))
    found: dict = {}
    for o in model.openings():
        if o.mark:
            found[o.mark] = found.get(o.mark, 0) + 1
    for mark, n in found.items():
        if mark in labels and n > labels[mark]["count"]:
            issues.append(Issue("more_than_scheduled", "warn", f"{n} openings of type {mark} were found on this floor but the schedule has only {labels[mark]['count']} in the whole building.", [],
                                "Some are probably another type or a duplicate; the BoQ counts no more than the schedule."))
    untagged = [o for o in model.openings() if not o.mark]
    if untagged:
        issues.append(Issue("openings_unmatched", "warn", f"{len(untagged)} openings found on the plan could not be matched to a schedule type, so their size is unknown.", [o.id for o in untagged][:20],
                            "Give their sizes, or check the tags on the plan."))
    model.issues += issues
    return issues


def counts_by_mark(model: DrawingModel) -> dict:
    """{mark: {"external": n, "internal": n}} for the openings tied to a schedule type; what the BoQ deducts."""
    out: dict = {}
    for o in model.openings():
        if o.mark:
            out.setdefault(o.mark, {"external": 0, "internal": 0})[o.subtype] += 1
    return out
