"""Doors, windows and openings tied to the walls they are in. Code finds the candidates (the stretches of a wall where both faces are broken),
measures their width from the drawing, and reads tags from the text layer where there is one; the model looks at a crop of each candidate and says
what it is (door, window, a bare opening, or not an opening) and reads the tag printed beside it. Whether an opening is external or internal comes
from the wall it sits in, and its size from the schedule type it is matched to, never from the model."""
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from plan2cost.drawing.model import DrawingModel, Element, Issue

TAG = re.compile(r"^(?:[A-Z]{1,3}\d{1,2}[A-Za-z]?)$")
DOOR_WIDTHS_MM = (750, 900, 1050, 1200, 1800)  # the door and window sizes that recur in the author's own plans; a measured gap is snapped to the nearest
WINDOW_WIDTHS_MM = (600, 750, 900, 1200, 1500, 1800, 2400)
MIN_MM, MAX_MM = 450, 3700  # narrower is a jamb or a break in a face line, wider is a gap in the detection

PROMPT = """This is a crop of a floor plan. A thick orange bar marks a gap that was found in a wall. Say what the gap is:
- "door": a door leaf or a swing arc is drawn that belongs to THIS gap, its hinge at one end of the bar. A leaf or an arc that belongs to a different gap close by does not count;
- "window": frame or sill lines run across the gap, or it carries a window tag;
- "opening": an open gap in the wall with no door or window drawn (an arch, a pass-through, a doorway without a leaf);
- "not_opening": the bar is not on a gap in a wall: a short stretch of wall with thick wall faces on both sides (hatched or solid), a stair, furniture, a wall end, a column, a text label, two walls meeting.
Also read the tag printed next to it if there is one (like W3, D2, SD1, AW1, TD2), exactly as printed, else null.
Judge only what you can see. Return only JSON: {"kind": "door|window|opening|not_opening", "tag": "W3" or null, "leaf": "single|double|sliding|none|unclear"}"""


WALL_INK = 0.38  # share of a stretch's wall band drawn dark above which a door or opening candidate is a piece of wall (real door gaps measured 0.05 to 0.31, wall stubs 0.42 to 0.50)
TAGGED_MIN = 4  # fewer tags than this and the drawing is not taken to tag its openings
WEAK_SOURCES = ("between jamb lines", "between a wall end and the next wall", "where the wall faces are drawn lighter")  # detectors that need a tag to back them up on a tagged drawing


def near_void(c: dict, model: DrawingModel, reach_mm: float = 1500) -> bool:
    """Is the opening within reach of a space named Void? Windows on the walls of a void are often a glass facade from one floor to the next, and then have no tag of their own."""
    cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
    return any(s["kind"] == "void" and s["box_mm"][0] - reach_mm <= cx <= s["box_mm"][2] + reach_mm and s["box_mm"][1] - reach_mm <= cy <= s["box_mm"][3] + reach_mm for s in model.spaces)


def stretch_ink(img, scale: float, c: dict) -> float:
    """How much of the wall's thickness is drawn dark along a candidate's stretch (0 to 1). A door gap is nearly empty (a leaf and a threshold line at most); a stretch of wall
    drawn with thick faces and hatching is not."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    half = int(c["thickness"] / 2 * scale)
    if c["orient"] == "h":
        a, b = sorted((int(c["x0"] * scale), int(c["x1"] * scale)))
        y = int(c["y0"] * scale)
        band = gray[max(y - half, 0):y + half + 1, max(a, 0):b + 1]
    else:
        a, b = sorted((int(c["y0"] * scale), int(c["y1"] * scale)))
        x = int(c["x0"] * scale)
        band = gray[max(a, 0):b + 1, max(x - half, 0):x + half + 1]
    return float((band < 140).mean()) if band.size else 0.0


def tag_kind(tag: str) -> str | None:
    """door or window from the printed letters of a tag (D1, SD2, W3, AW1), else None."""
    return "door" if re.match(r"^[STP]?D\d", tag) else "window" if re.match(r"^[AST]?W\d", tag) else None


def snap(width_mm: float, sizes: tuple) -> int:
    return min(sizes, key=lambda s: abs(s - width_mm))


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


def end_gap_candidates(model: DrawingModel, have: list, reach_mm: float = 2400, tol_mm: float = 150) -> list[dict]:
    """A door is often a gap between the end of a wall and the wall it would meet (or the next wall on the same line), not a gap inside one run. For each wall end that
    meets nothing, the stretch from that end to the nearest wall ahead of it (450 to 2400 mm of clear space) is a candidate. Most will not be openings (a partition that
    simply stops), so the model decides from a crop; stretches that overlap a gap already found are left out."""
    from plan2cost.drawing.qc import _end_meets_wall, _wall

    els = model.walls()
    walls = [_wall(e) for e in els]
    out: list[dict] = []
    for e, w in zip(els, walls):
        for sign, end in ((1, w.end_mm), (-1, w.start_mm)):
            if _end_meets_wall(w, end, walls, tol_mm):
                continue
            best = None
            for o, v in zip(els, walls):
                if o is e:
                    continue
                if v.orient != w.orient:  # a wall across the line: its near face is the stop
                    face = v.centre_mm - sign * v.thickness_mm / 2
                    covers = v.start_mm - tol_mm <= w.centre_mm <= v.end_mm + tol_mm
                else:  # the next wall on the same line: where it starts
                    face = v.start_mm if sign == 1 else v.end_mm
                    covers = abs(v.centre_mm - w.centre_mm) <= max(v.thickness_mm, w.thickness_mm)
                clear = (face - end) * sign
                if covers and 450 <= clear <= reach_mm and (best is None or clear < best[0]):
                    best = (clear, face)
            if not best:
                continue
            a, b = sorted((end, best[1]))
            x0, y0, x1, y1 = (a, e.y0_mm, b, e.y0_mm) if e.orient == "h" else (e.x0_mm, a, e.x0_mm, b)
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            if any(abs((h["x0"] + h["x1"]) / 2 - mid[0]) < 450 and abs((h["y0"] + h["y1"]) / 2 - mid[1]) < 450 for h in have + out):
                continue
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(best[0]), "external": e.external_share >= 0.5,
                        "thickness": e.thickness_mm, "source": "between a wall end and the next wall"})
    return out


def _heavy_lines(band, c0: int, c1: int, margin: int = 6) -> int:
    """How many separate heavy lines run along the wall between two columns of its band (rows of the band mostly ink, groups of adjacent rows counted once)."""
    rows = band[:, c0 + margin:max(c1 - margin, c0 + margin + 1)].mean(axis=1) >= 0.7
    return int(np.count_nonzero(np.diff(np.concatenate([[0], rows.astype(np.int8)])) == 1))


def jamb_candidates(model: DrawingModel, img, scale: float, have: list, min_px: int = 3, require_sill: bool = True) -> list[dict]:
    """Openings drawn inside the wall with no break in its faces (a window shown as a sill and jamb lines across the wall): the stretches of a wall between two
    consecutive heavy lines that cross the whole thickness of the wall. Most of these stretches are plain wall, so they are only candidates; the model looks at each
    and says what it is. Stretches that overlap a gap already found are left out."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    dark = gray < 140
    out = []
    for e in model.walls():
        half = e.thickness_mm / 2 * scale + 1.5
        if e.orient == "h":
            a, b = sorted((int(e.x0_mm * scale), int(e.x1_mm * scale)))
            r0, r1 = int(e.y0_mm * scale - half), int(e.y0_mm * scale + half)
            band = dark[max(r0, 0):r1 + 1, max(a, 0):b + 1]
        else:
            a, b = sorted((int(e.y0_mm * scale), int(e.y1_mm * scale)))
            c0, c1 = int(e.x0_mm * scale - half), int(e.x0_mm * scale + half)
            band = dark[max(a, 0):b + 1, max(c0, 0):c1 + 1].T
        if band.size == 0 or band.shape[1] < 10:
            continue
        full = band.mean(axis=0) >= 0.85  # a column that is ink across the whole wall thickness
        runs, n = [], band.shape[1]
        i = 0
        while i < n:
            if full[i]:
                j = i
                while j + 1 < n and full[j + 1]:
                    j += 1
                if j - i + 1 >= min_px:
                    runs.append((i, j))
                i = j + 1
            else:
                i += 1
        if len(runs) > 12:
            continue  # a wall drawn solid, or hatched so densely that every column is full: no jamb lines to read
        for (s1, e1), (s2, e2) in zip(runs, runs[1:]):
            lo, hi = (e1 + 1) / scale, s2 / scale  # the stretch between the two lines, in mm along the wall
            width = hi - lo
            if not MIN_MM <= width <= MAX_MM:
                continue
            if require_sill and _heavy_lines(band, int(lo * scale), int(hi * scale)) < 3:
                continue  # two heavy face lines and nothing between them is plain wall; a window symbol has a third line (the sill) between its faces
            lo, hi = lo + max(a, 0) / scale, hi + max(a, 0) / scale  # the band starts at pixel max(a, 0) of the sheet
            x0, y0, x1, y1 = (lo, e.y0_mm, hi, e.y0_mm) if e.orient == "h" else (e.x0_mm, lo, e.x0_mm, hi)
            if any(h["wall"] == e.id and min(hi, h["x1"] if e.orient == "h" else h["y1"]) - max(lo, h["x0"] if e.orient == "h" else h["y0"]) > 0.5 * width for h in have):
                continue
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(width), "external": e.external_share >= 0.5,
                        "thickness": e.thickness_mm, "source": "between jamb lines"})
    return out


def thin_face_candidates(model: DrawingModel, img, scale: float, have: list, min_run_mm: float = 300, jamb_mm: float = 60) -> list[dict]:
    """Windows drawn as lighter lines inside the wall, with a dot or a short line at each end: along a wall the ink across its thickness drops from the heavy face lines to the
    thin lines of the symbol. A stretch of 300 to 2400 mm where the wall is drawn at under 60% of its usual weight, but still drawn, is a candidate (widened by the jamb at each end).
    Most such stretches are not openings (hatching, a notch), so the model looks at each; stretches that overlap an opening already found are left out."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    dark = gray < 140
    out = []
    for e in model.walls():
        half = int(e.thickness_mm / 2 * scale + 2)
        if e.orient == "h":
            a, b = sorted((int(e.x0_mm * scale), int(e.x1_mm * scale)))
            c = int(e.y0_mm * scale)
            band = dark[max(c - half, 0):c + half + 1, max(a, 0):b + 1]
        else:
            a, b = sorted((int(e.y0_mm * scale), int(e.y1_mm * scale)))
            c = int(e.x0_mm * scale)
            band = dark[max(a, 0):b + 1, max(c - half, 0):c + half + 1].T
        if band.size == 0 or band.shape[1] < 20 or band.shape[0] < 4:
            continue
        frac = band.mean(axis=0)
        solid = frac[frac >= 0.3]
        if len(solid) < 0.3 * len(frac):
            continue  # a wall that is not drawn heavily for most of its length has no weight to drop from
        heavy = float(np.median(solid))
        thin = (frac > 0.06) & (frac < 0.6 * heavy)
        edges = np.diff(np.concatenate([[0], thin.astype(np.int8), [0]]))
        for s, f in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            run = (f - s) / scale
            if run < min_run_mm or run + 2 * jamb_mm > MAX_MM - 1000:
                continue
            lo, hi = max(a, 0) / scale + s / scale - jamb_mm, max(a, 0) / scale + f / scale + jamb_mm
            x0, y0, x1, y1 = (lo, e.y0_mm, hi, e.y0_mm) if e.orient == "h" else (e.x0_mm, lo, e.x0_mm, hi)
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            if any(h["wall"] == e.id and abs((h["x0"] + h["x1"]) / 2 - mid[0]) < 450 and abs((h["y0"] + h["y1"]) / 2 - mid[1]) < 450 for h in have + out):
                continue
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(hi - lo), "external": e.external_share >= 0.5, "thickness": e.thickness_mm,
                        "source": "where the wall faces are drawn lighter"})
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
    from plan2cost.drawing.dims import dimension_tokens

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

    from plan2cost.kit.pdf import pdftoppm

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
    from plan2cost.kit.client import image_part
    from plan2cost.kit.client import chat_json

    if not path:
        return {"kind": "not_opening", "tag": None}
    try:
        return chat_json([{"type": "text", "text": PROMPT}, image_part(path)])
    except Exception as e:
        return {"kind": "unverified", "tag": None, "error": type(e).__name__}


def locate_openings(model: DrawingModel, img, scale: float, pdf: str | None = None, page: int | None = None, schedule: list | None = None, workers: int = 6,
                    tags: list | None = None) -> list[Issue]:
    """Find the openings on the floor, add them to the model (door D-001, window WN-001, opening O-001), tie each to its wall and to a schedule
    type, and return the issues the reconciliation raises. `schedule` is the opening types read from the schedule pages (label, width_m, height_m,
    count, kind); the model's walls decide external or internal. `tags` are the opening tags read from the plan by the model ((tag, x_mm, y_mm)); when None, the tags come from the
    PDF's text layer. On a drawing that tags its openings the tags are evidence: a candidate with no tag near it, from the weaker detectors, is left out, and a tag with no opening near it
    is searched for at its place."""
    cands = candidates(model)
    for c in cands:
        c["source"] = "gap in the wall"
    if pdf and page and schedule:
        cands += dimension_candidates(model, pdf, page, {round(s["width_m"] * 1000) for s in schedule}, cands)
    cands += jamb_candidates(model, img, scale, cands)
    cands += thin_face_candidates(model, img, scale, cands)
    cands += end_gap_candidates(model, cands)
    tag_source = "read by the model" if tags is not None else "text layer"
    if tags is None:
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
        elif kind not in ("door", "window", "opening") or (c.get("source") == "where the wall faces are drawn lighter" and kind != "window"):  # a lighter-drawn stretch is a window symbol or nothing
            dropped += 1
        elif kind in ("door", "opening") and c.get("source") != "gap in the wall" and stretch_ink(img, scale, c) > WALL_INK:  # a stretch drawn with heavy faces and hatching is wall, whatever the arc beside it
            dropped += 1
        else:
            kept.append((c, v))

    def pair(kept):
        """Each printed tag belongs to the one gap nearest to it (within 1.8 m); a tag is never shared between two openings."""
        pairs = sorted((((tx - (c["x0"] + c["x1"]) / 2) ** 2 + (ty - (c["y0"] + c["y1"]) / 2) ** 2) ** 0.5, gi, ti) for gi, (c, _) in enumerate(kept) for ti, (_, tx, ty) in enumerate(tags))
        gap_tag, used, gap_dist = {}, set(), {}
        for d, gi, ti in pairs:
            if d <= 1800 and gi not in gap_tag and ti not in used:
                gap_tag[gi] = tags[ti][0]
                gap_dist[gi] = d
                used.add(ti)
        return gap_tag, used, gap_dist

    gap_tag, used_tags, gap_dist = pair(kept)
    if len(tags) >= TAGGED_MIN:  # a drawing that tags its openings: the tags are evidence
        model.tagged = True
        # a window's own tag stands within about a metre of its centre; a stretch of wall between two windows has only its neighbours' tags, further off
        crop_tag = lambda v: bool(re.match(TAG, (v.get("tag") or "").strip().upper()))  # a tag the model read beside the opening in its crop is evidence too: the tag positions are coarse
        kept2 = [(c, v) for gi, (c, v) in enumerate(kept)
                 if not (c.get("source") in WEAK_SOURCES or (v["kind"] == "window" and c["width_mm"] > 1900))
                 or crop_tag(v)
                 or (v["kind"] == "window" and c["width_mm"] <= 2400 and near_void(c, model))  # glazing to a void runs from one floor to the next and carries no tag
                 or (gi in gap_tag and not (v["kind"] == "window" and c["width_mm"] > 1900 and gap_dist[gi] > 1000))]
        untagged = len(kept) - len(kept2)
        kept = kept2
        gap_tag, used_tags, gap_dist = pair(kept)
        lost = [ti for ti in range(len(tags)) if ti not in used_tags]
        near = [c for c in jamb_candidates(model, img, scale, [c for c, _ in kept], require_sill=False)
                if any(((tags[ti][1] - (c["x0"] + c["x1"]) / 2) ** 2 + (tags[ti][2] - (c["y0"] + c["y1"]) / 2) ** 2) ** 0.5 <= 1800 for ti in lost) and c["width_mm"] <= 2400]
        for c in near:
            c["source"] = "at a printed tag"
        with ThreadPoolExecutor(workers) as ex:
            found = list(ex.map(_verify, [_crop(img, scale, c, out_dir, 1000 + i) for i, c in enumerate(near)]))
        added = [(c, v) for c, v in zip(near, found) if v.get("kind") in ("door", "window", "opening")]
        kept += added
        gap_tag, used_tags, gap_dist = pair(kept)
        lost = [tags[ti][0] for ti in range(len(tags)) if ti not in used_tags]
        matched = [tags[ti] for ti in used_tags]
        unplaced = []  # a printed tag is an opening even where its wall was not measured. Counted from the tag, at a standard size, only where no opening of its kind was located near it
        # (so a tag read twice, or beside an opening that was found, adds nothing), and not when the same tag was read beside a located opening in its crop
        located = [(tag_kind((v.get("tag") or "").strip().upper()) or v["kind"], (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2) for c, v in kept]
        for ti, (tg, tx, ty) in enumerate(tags):
            kind = tag_kind(tg)
            if ti in used_tags or not kind or any(m[0] == tg and ((m[1] - tx) ** 2 + (m[2] - ty) ** 2) ** 0.5 <= 3000 for m in matched):
                continue
            if any(k == kind and ((x - tx) ** 2 + (y - ty) ** 2) ** 0.5 <= 2500 for k, x, y in located):
                continue
            unplaced.append({"tag": tg, "kind": kind, "x_mm": round(tx), "y_mm": round(ty)})
        model.unplaced_tags = unplaced
        model.tag_totals = {k: sum(1 for ti, (tg, _, _) in enumerate(tags) if tag_kind(tg) == k and (ti in used_tags or any(u['tag'] == tg and u['kind'] == k for u in unplaced))) for k in ('window', 'door')}  # distinct tags of each kind on the plan
        issues.append(Issue("tags_matched", "info", f"{len(tags)} opening tags were read from the plan ({tag_source}); {len(used_tags)} are matched to an opening, {len(added)} openings were found by searching at a tag, "
                                                    f"{untagged} candidates with no tag near them were left out.", [], ""))
        if lost:
            n_w, n_d = sum(u["kind"] == "window" for u in unplaced), sum(u["kind"] == "door" for u in unplaced)
            issues.append(Issue("tags_unmatched", "warn", f"{len(lost)} printed opening tags have no opening near them ({', '.join(sorted(lost)[:12])}{'...' if len(lost) > 12 else ''}), probably in walls that were not measured; "
                                                          f"{n_w} windows and {n_d} doors are counted from the tags (the same tag read twice is counted once), at a standard size.", [],
                                "Check those places on the plan; their sizes are standard, not measured."))
    for gi, (c, v) in enumerate(kept):
        text_tag = gap_tag.get(gi)
        tag, how = (text_tag, f"directly labelled ({tag_source})") if text_tag else ((v.get("tag") or "").strip().upper() or None, "directly labelled (read from the crop)")
        by_tag = tag_kind(text_tag) if text_tag else None  # the printed letter is stronger evidence than a look at a crop
        kind = by_tag or v["kind"]
        if kind == "door" and not by_tag and c["width_mm"] < 700:  # no door is narrower than 700 mm clear (the author's smallest is 750): a small window symbol with a neighbour's arc beside it
            kind = "window"
        made.append({**c, "kind": kind, "tag": tag, "how": how if tag else "inferred"})
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
            if m["tag"] and schedule:
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
    wide = [o for o in model.openings() if o.category == "window" and o.width_mm > 1900]
    if wide:
        issues.append(Issue("wide_windows", "warn", f"{len(wide)} windows are wider than 1.9 m ({', '.join(o.id for o in wide[:6])}); a stretch of plain wall between two window frames can look like a window.", [o.id for o in wide][:20],
                            "Check these on the markup; a wall taken for a window leaves its wall area out of the bill."))
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
    if untagged and schedule:
        issues.append(Issue("openings_unmatched", "warn", f"{len(untagged)} openings found on the plan could not be matched to a schedule type, so their size is unknown.", [o.id for o in untagged][:20],
                            "Give their sizes, or check the tags on the plan."))
    model.issues += issues
    return issues


