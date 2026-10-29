"""Model-checked walls: the model judges what a picture shows, code does the measuring and the editing. Three checks, each with a closed question about a crop of
the plan, and an edit only when the model's answer and the geometry agree:
- a run that overshoots the last joint of the building: the model says whether the stretch is on a wall; if not, code trims the run back to the joint;
- two runs on one line that overlap: the model says whether it is one wall; if so, code drops the one that lies inside the other;
- a place where the model sees a wall with no line on it: code searches the plan there for a wall-like bar whose both ends meet existing walls, and adds it only if found.
Every edit is logged as an issue marked "model check", so a person can see what changed; a model answer on its own never sets a length."""
import tempfile
from pathlib import Path

import cv2
import numpy as np

from plan2cost.drawing.model import DrawingModel, Element, Issue, refresh
from plan2cost.drawing.qc import _joints, _wall

MAGENTA, CYAN = (255, 0, 255), (255, 200, 0)  # BGR

ON_WALL = """This is a crop of a building floor plan. A program drew a thick {colour} line over a stretch of line work and treated it as a wall. Is there a real wall under the {colour} line:
two thick parallel faces (solid, hatched or poche-filled) forming a bar of wall? Or is it only a thin line, such as a grid line, dimension line, extension line, leader or a line running off past the building?
Judge only what you can see. Return only JSON: {{"on_wall": true or false or null (null if you cannot tell), "why": "one short sentence"}}"""
SAME_WALL = """This is a crop of a floor plan. A program drew two lines over it, {a} and {b}, both along the same wall line and overlapping. Are they one wall found twice, or two different walls
(for example two leaves of a cavity, or a wall and a separate thin line next to it)? Return only JSON: {{"same_wall": true or false or null, "why": "one short sentence"}}"""
MISSED = """This is a floor plan with the walls a program measured drawn on it: red are external walls, blue internal walls, numbers are ids. List walls of the building that are drawn on the plan
as a wall but have no coloured line on them. For each give its place as a box on THIS picture, as fractions of the picture's width and height (x0, y0, x1, y1, from the top left), tight around the
missing wall, and whether the wall is horizontal ("h") or vertical ("v") on the picture. Judge only what you can see; do not list door or window gaps, grid lines or dimension lines.
Return only JSON: {"missed": [{"box": [0.0, 0.0, 0.0, 0.0], "orient": "h", "what": "short plain description"}]}"""


def _ask(prompt: str, crop) -> dict:
    from plan2cost.kit.client import chat_json, image_part

    path = str(Path(tempfile.mkdtemp()) / "crop.jpg")
    cv2.imwrite(path, crop)
    return chat_json([{"type": "text", "text": prompt}, image_part(path)])


def _crop(img, scale: float, box_mm: tuple, draw: list, min_side: int = 700, max_side: int = 1400):
    """The plan inside a box (x0, y0, x1, y1 in mm) with lines drawn on it: draw = [((x0, y0), (x1, y1), colour)] in mm."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (int(max(v * scale, 0)) for v in box_mm)
    x1, y1 = min(x1, w), min(y1, h)
    out = img[y0:y1, x0:x1].copy()
    if out.size == 0:
        return None
    for (a, b, colour) in draw:
        cv2.line(out, (int(a[0] * scale) - x0, int(a[1] * scale) - y0), (int(b[0] * scale) - x0, int(b[1] * scale) - y0), colour, max(4, int(max(out.shape[:2]) / 160)))
    k = min_side / max(out.shape[:2]) if max(out.shape[:2]) < min_side else min(1.0, max_side / max(out.shape[:2]))
    return cv2.resize(out, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)


def _log(model: DrawingModel, code: str, message: str, ids: list) -> None:
    model.issues.append(Issue(code, "info", message, ids, "", "model check"))


def trim_overshoots(model: DrawingModel, img, scale: float, ask=_ask) -> list[Issue]:
    """Runs that go more than 0.6 m past the last joint of the building: ask whether the stretch is on a wall, trim it back if not."""
    els = model.walls()
    walls = [_wall(e) for e in els]
    pts = _joints(walls)
    if len(pts) < 4:
        return []
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    log: list[Issue] = []
    for e, w in zip(els, walls):
        lo, hi = (x0, x1) if w.orient == "h" else (y0, y1)
        for side, beyond in (("start", lo - w.start_mm), ("end", w.end_mm - hi)):
            if beyond <= 600:
                continue
            a, b = (w.start_mm, lo) if side == "start" else (hi, w.end_mm)
            pa, pb = ((a, w.centre_mm), (b, w.centre_mm)) if w.orient == "h" else ((w.centre_mm, a), (w.centre_mm, b))
            pad = 1500
            box = (min(pa[0], pb[0]) - pad, min(pa[1], pb[1]) - pad, max(pa[0], pb[0]) + pad, max(pa[1], pb[1]) + pad)
            crop = _crop(img, scale, box, [(pa, pb, MAGENTA)])
            if crop is None:
                continue
            r = ask(ON_WALL.format(colour="magenta"), crop)
            if r.get("on_wall") is False:
                if side == "start":
                    w.start_mm = lo
                    e.x0_mm, e.y0_mm = (lo, e.y0_mm) if e.orient == "h" else (e.x0_mm, lo)
                else:
                    w.end_mm = hi
                    e.x1_mm, e.y1_mm = (hi, e.y1_mm) if e.orient == "h" else (e.x1_mm, hi)
                e.notes.append(f"trimmed by {beyond / 1000:.1f} m after the model saw no wall past the last joint")
                log.append(Issue("trimmed", "info", f"{e.id} trimmed back by {beyond / 1000:.1f} m to the last joint: the model saw no wall there ({r.get('why', '')}).", [e.id], "", "model check"))
    return log


def merge_duplicates(model: DrawingModel, img, scale: float, ask=_ask) -> list[Issue]:
    """Pairs flagged as overlapping on one line: if the model says it is one wall and the shorter lies inside the longer, drop the shorter."""
    log: list[Issue] = []
    byid = {e.id: e for e in model.walls()}
    for issue in [i for i in model.issues if i.code == "overlap"]:
        a, b = (byid.get(i) for i in issue.elements[:2])
        if not a or not b or a.id not in byid or b.id not in byid:
            continue
        wa, wb = _wall(a), _wall(b)
        short, long_ = (a, b) if wa.length_mm <= wb.length_mm else (b, a)
        ws, wl = _wall(short), _wall(long_)
        inside = min(ws.end_mm, wl.end_mm) - max(ws.start_mm, wl.start_mm)
        if inside < 0.9 * ws.length_mm:
            continue  # only part overlaps: leave the question for a person
        cx, cy = (short.x0_mm + short.x1_mm) / 2, (short.y0_mm + short.y1_mm) / 2
        box = (cx - 1800, cy - 1800, cx + 1800, cy + 1800)
        crop = _crop(img, scale, box, [((short.x0_mm, short.y0_mm), (short.x1_mm, short.y1_mm), MAGENTA), ((long_.x0_mm, long_.y0_mm), (long_.x1_mm, long_.y1_mm), CYAN)])
        if crop is None:
            continue
        r = ask(SAME_WALL.format(a="the magenta line", b="the cyan line"), crop)
        if r.get("same_wall") is True:
            byid.pop(short.id)
            model.elements = [e for e in model.elements if e.id != short.id]
            log.append(Issue("merged", "info", f"{short.id} dropped as the same wall as {long_.id}: the model saw one wall ({r.get('why', '')}).", [long_.id], "", "model check"))
    return log


def _bar(img, scale: float, box_mm: tuple, orient: str):
    """The longest wall-like bar of the given orientation inside a box: (start, end, centre, thickness) in mm along and across, or None."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (int(max(v * scale, 0)) for v in box_mm)
    x1, y1 = min(x1, w), min(y1, h)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    dark = (cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY) < 140).astype(np.uint8)
    along = (x1 - x0) if orient == "h" else (y1 - y0)
    close_px, open_px = max(3, int(1300 * scale)), max(3, min(int(600 * scale), int(along * 0.6)))
    shape = (lambda n: (n, 1)) if orient == "h" else (lambda n: (1, n))
    pad = close_px  # blank padding, or closing would stretch a bar that stops short of the edge of the box out to the edge
    dark = cv2.copyMakeBorder(dark, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    bar = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, shape(close_px)))
    bar = cv2.morphologyEx(bar, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, shape(open_px)))[pad:-pad, pad:-pad]
    n, _, stats, _ = cv2.connectedComponentsWithStats(bar)
    best = None
    for i in range(1, n):
        bx, by, bw, bh, _ = stats[i]
        length, thick = (bw, bh) if orient == "h" else (bh, bw)
        t_mm = thick / scale
        if length / scale >= 600 and 80 <= t_mm <= 350 and (best is None or length > best[0]):
            best = (length, bx, by, bw, bh)
    if best is None:
        return None
    _, bx, by, bw, bh = best
    if orient == "h":
        return ((x0 + bx) / scale, (x0 + bx + bw) / scale, (y0 + by + bh / 2) / scale, bh / scale)
    return ((y0 + by) / scale, (y0 + by + bh) / scale, (x0 + bx + bw / 2) / scale, bw / scale)


def _meets(model: DrawingModel, orient: str, centre: float, end: float, tol: float = 250) -> bool:
    """Does a perpendicular wall cross the line `centre` at position `end` along it?"""
    for e in model.walls():
        if e.orient == orient:
            continue
        v = _wall(e)
        if abs(v.centre_mm - end) <= v.thickness_mm / 2 + tol and v.start_mm - tol <= centre <= v.end_mm + tol:
            return True
    return False


def add_missed(model: DrawingModel, img, scale: float, markup_path: str, ask=_ask) -> list[Issue]:
    """Ask the model where a drawn wall has no line, then look for a bar of wall in that place; add it only when both its ends meet existing walls."""
    if len(model.markup_frame) != 4:
        return []
    fx, fy, shrink, mscale = model.markup_frame
    mimg = cv2.imread(markup_path)
    mh, mw = mimg.shape[:2]
    r = ask(MISSED, mimg)
    log: list[Issue] = []
    walls = [_wall(e) for e in model.walls()]
    for m in (r.get("missed") or [])[:6]:
        try:
            bx0, by0, bx1, by1 = (float(v) for v in m["box"])
            orient = m["orient"] if m.get("orient") in ("h", "v") else None
        except (KeyError, TypeError, ValueError):
            continue
        if not orient or not (0 <= bx0 < bx1 <= 1.0 and 0 <= by0 < by1 <= 1.0):
            continue
        to_mm = lambda px, py: ((px * mw / shrink + fx) / mscale, (py * mh / shrink + fy) / mscale)
        (ax, ay), (bx, by) = to_mm(bx0, by0), to_mm(bx1, by1)
        pad = 300
        found = _bar(img, scale, (ax - pad, ay - pad, bx + pad, by + pad), orient)
        what = m.get("what", "")
        if not found:
            log.append(Issue("missed_not_found", "info", f"The model saw a wall with no line ({what}) but no wall-like bar could be found there.", [], "Look at that place on the plan.", "model check"))
            continue
        start, end, centre, thick = found
        if not (_meets(model, orient, centre, start) and _meets(model, orient, centre, end)):
            log.append(Issue("missed_not_added", "warn", f"The model saw a wall with no line ({what}) and a bar of {(end - start) / 1000:.1f} m was found, but its ends do not both meet walls, so it was not added.", [], "Check this place on the plan; add the wall if it is there.", "model check"))
            continue
        if any(w.orient == orient and abs(w.centre_mm - centre) <= max(w.thickness_mm, thick) and min(w.end_mm, end) - max(w.start_mm, start) > 0.5 * (end - start) for w in walls):
            continue  # already measured
        t = float(np.median([e.thickness_mm for e in model.walls()])) if model.walls() else thick
        thickness = t if abs(thick - t) <= 0.3 * t else round(thick / 10) * 10
        n = 1 + max((int(e.id.split("-")[1]) for e in model.walls()), default=0)
        x0, y0, x1, y1 = (start, centre, end, centre) if orient == "h" else (centre, start, centre, end)
        new = Element(f"W-{n:03d}", "wall", "internal", model.page, model.floor, orient, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1), round((end - start) / 1000, 3), float(thickness),
                      evidence="geometrically measured", confidence="low", notes=["added after the model saw a wall with no line here; found by code and joined to walls at both ends"])
        model.elements.append(new)
        walls.append(_wall(new))
        log.append(Issue("added", "info", f"{new.id} added ({(end - start) / 1000:.1f} m internal): the model saw a wall here ({what}) and code found it joining walls at both ends.", [new.id], "", "model check"))
    return log


def verify_walls(model: DrawingModel, img, scale: float, markup_path: str) -> bool:
    """Run the three checks, apply the edits, recompute totals and code checks. Returns True when the walls changed. A failed model call skips that check, never the run."""
    log: list[Issue] = []
    for step in (lambda: trim_overshoots(model, img, scale), lambda: merge_duplicates(model, img, scale), lambda: add_missed(model, img, scale, markup_path)):
        try:
            log += step()
        except Exception as ex:
            log.append(Issue("verify_skipped", "info", f"A model check of the walls was skipped ({type(ex).__name__}).", [], "", "model check"))
    changed = any(i.code in ("trimmed", "merged", "added") for i in log)
    if changed:
        refresh(model)
    model.issues += log
    return changed
