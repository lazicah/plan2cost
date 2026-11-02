"""Doors, windows and openings tied to the walls they are in. The candidate finders (`opening_candidates`) propose stretches of wall where an opening may be; the model looks at a
crop of each and says what it is (door, window, a bare opening, or not an opening) and reads the tag printed beside it; the printed tags are evidence for or against each candidate.
Code decides what is kept and measures the width from the drawing. Whether an opening is external or internal comes from the wall it sits in, and its size from the schedule type it
is matched to (or the nearest standard size), never from the model. The entry point is `locate_openings`."""
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

import cv2

from plan2cost.drawing.model import DrawingModel, Element, Issue
from plan2cost.drawing.opening_candidates import (TAG, candidates, dimension_candidates, end_gap_candidates, jamb_candidates, stretch_ink,  # noqa: F401  (re-exported)
                                                  text_tags, thin_face_candidates)

DOOR_WIDTHS_MM = (750, 900, 1050, 1200, 1800)  # the door and window sizes that recur in the author's own plans; a measured gap is snapped to the nearest
WINDOW_WIDTHS_MM = (600, 750, 900, 1200, 1500, 1800, 2400)

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


def tag_kind(tag: str) -> str | None:
    """door or window from the printed letters of a tag (D1, SD2, W3, AW1), else None."""
    return "door" if re.match(r"^[STP]?D\d", tag) else "window" if re.match(r"^[AST]?W\d", tag) else None


def snap(width_mm: float, sizes: tuple) -> int:
    """The nearest of the standard sizes to a measured width (a drawn gap is rarely exactly 900 or 1200)."""
    return min(sizes, key=lambda s: abs(s - width_mm))


def _crop(img, scale: float, c: dict, out_dir: str, i: int, side_mm: float = 3600) -> str:
    """A 640 px crop of the plan around a candidate with an orange bar drawn on it, written to `out_dir`; the picture the model judges. Returns its path (empty when the candidate is off the page)."""
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
    """Ask the model what a candidate is: door, window, opening or not an opening, with the tag beside it and the door leaf. A failed call is reported as 'unverified', never guessed."""
    from plan2cost.kit.client import image_part
    from plan2cost.kit.client import chat_json

    if not path:
        return {"kind": "not_opening", "tag": None}
    try:
        return chat_json([{"type": "text", "text": PROMPT}, image_part(path)])
    except Exception as e:
        return {"kind": "unverified", "tag": None, "error": type(e).__name__}


def _find_candidates(model: DrawingModel, img, scale: float, pdf: str | None, page: int | None, schedule: list | None) -> list[dict]:
    """Every candidate from every finder, strongest evidence first; a finder leaves out what an earlier one already found."""
    cands = candidates(model)
    for c in cands:
        c["source"] = "gap in the wall"
    if pdf and page and schedule:
        cands += dimension_candidates(model, pdf, page, {round(s["width_m"] * 1000) for s in schedule}, cands)
    cands += jamb_candidates(model, img, scale, cands)
    cands += thin_face_candidates(model, img, scale, cands)
    cands += end_gap_candidates(model, cands)
    return cands


def _judge(cands: list[dict], img, scale: float, out_dir: str, workers: int) -> tuple[list, int, int]:
    """The model looks at a crop of each candidate; code then drops what it can show is not an opening. Returns the kept (candidate, verdict) pairs, how many were
    dropped and how many could not be checked."""
    paths = [_crop(img, scale, c, out_dir, i) for i, c in enumerate(cands)]
    with ThreadPoolExecutor(workers) as ex:
        verdicts = list(ex.map(_verify, paths))
    kept, dropped, unverified = [], 0, 0
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
    return kept, dropped, unverified


def _centre(c: dict) -> tuple[float, float]:
    return (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _pair_tags(kept: list, tags: list) -> tuple[dict, set, dict]:
    """Each printed tag belongs to the one candidate nearest to it (within 1.8 m); a tag is never shared between two openings. Returns {candidate index: tag}, the set of tag indexes
    used, and {candidate index: distance to its tag}."""
    pairs = sorted((_dist(_centre(c), (tx, ty)), gi, ti) for gi, (c, _) in enumerate(kept) for ti, (_, tx, ty) in enumerate(tags))
    gap_tag, used, gap_dist = {}, set(), {}
    for d, gi, ti in pairs:
        if d <= 1800 and gi not in gap_tag and ti not in used:
            gap_tag[gi] = tags[ti][0]
            gap_dist[gi] = d
            used.add(ti)
    return gap_tag, used, gap_dist


def _crop_tag(v: dict) -> str:
    """The tag the model read beside an opening in its crop (upper case), or ''."""
    return (v.get("tag") or "").strip().upper()


def _unplaced_tags(tags: list, used: set, kept: list) -> list[dict]:
    """Tags that stand where no opening was located. A printed tag is an opening even where its wall was not measured, so it is counted from the tag, at a standard size, but only
    where no opening of its kind was located within 2.5 m (a tag read twice, or beside an opening that was found, adds nothing) and not when the same tag was read beside a located
    opening in its crop."""
    matched = [tags[ti] for ti in used]
    located = [(tag_kind(_crop_tag(v)) or v["kind"], *_centre(c)) for c, v in kept]
    out = []
    for ti, (tg, tx, ty) in enumerate(tags):
        kind = tag_kind(tg)
        if ti in used or not kind or any(m[0] == tg and _dist((m[1], m[2]), (tx, ty)) <= 3000 for m in matched):
            continue
        if any(k == kind and _dist((x, y), (tx, ty)) <= 2500 for k, x, y in located):
            continue
        out.append({"tag": tg, "kind": kind, "x_mm": round(tx), "y_mm": round(ty)})
    return out


def _use_tags_as_evidence(model: DrawingModel, img, scale: float, kept: list, tags: list, tag_source: str, out_dir: str, workers: int) -> tuple[list, dict, list[Issue]]:
    """On a drawing that tags its openings the tags are evidence. A candidate from the weaker finders, and a window wider than 1.9 m, is kept only if a tag stands beside it (by
    position or read in its crop) or it is glazing to a void; a tag with no opening near it is searched for at its place; the tags left over are recorded on the model.
    Returns the kept pairs, {candidate index: tag}, and the issues to report."""
    model.tagged = True
    gap_tag, used, gap_dist = _pair_tags(kept, tags)
    # a window's own tag stands within about a metre of its centre; a stretch of wall between two windows has only its neighbours' tags, further off
    kept2 = [(c, v) for gi, (c, v) in enumerate(kept)
             if not (c.get("source") in WEAK_SOURCES or (v["kind"] == "window" and c["width_mm"] > 1900))
             or re.match(TAG, _crop_tag(v))  # a tag the model read beside the opening in its crop is evidence too: the tag positions are coarse
             or (v["kind"] == "window" and c["width_mm"] <= 2400 and near_void(c, model))  # glazing to a void runs from one floor to the next and carries no tag
             or (gi in gap_tag and not (v["kind"] == "window" and c["width_mm"] > 1900 and gap_dist[gi] > 1000))]
    untagged = len(kept) - len(kept2)
    kept = kept2
    gap_tag, used, gap_dist = _pair_tags(kept, tags)
    lost = [ti for ti in range(len(tags)) if ti not in used]
    near = [c for c in jamb_candidates(model, img, scale, [c for c, _ in kept], require_sill=False)
            if any(_dist((tags[ti][1], tags[ti][2]), _centre(c)) <= 1800 for ti in lost) and c["width_mm"] <= 2400]
    for c in near:
        c["source"] = "at a printed tag"
    with ThreadPoolExecutor(workers) as ex:
        found = list(ex.map(_verify, [_crop(img, scale, c, out_dir, 1000 + i) for i, c in enumerate(near)]))
    added = [(c, v) for c, v in zip(near, found) if v.get("kind") in ("door", "window", "opening")]
    kept += added
    gap_tag, used, gap_dist = _pair_tags(kept, tags)
    unplaced = _unplaced_tags(tags, used, kept)
    model.unplaced_tags = unplaced
    model.tag_totals = {k: sum(1 for ti, (tg, _, _) in enumerate(tags) if tag_kind(tg) == k and (ti in used or any(u["tag"] == tg and u["kind"] == k for u in unplaced))) for k in ("window", "door")}  # distinct tags of each kind on the plan
    issues = [Issue("tags_matched", "info", f"{len(tags)} opening tags were read from the plan ({tag_source}); {len(used)} are matched to an opening, {len(added)} openings were found by searching at a tag, "
                                            f"{untagged} candidates with no tag near them were left out.", [], "")]
    lost_names = [tags[ti][0] for ti in range(len(tags)) if ti not in used]
    if lost_names:
        n_w, n_d = sum(u["kind"] == "window" for u in unplaced), sum(u["kind"] == "door" for u in unplaced)
        issues.append(Issue("tags_unmatched", "warn", f"{len(lost_names)} printed opening tags have no opening near them ({', '.join(sorted(lost_names)[:12])}{'...' if len(lost_names) > 12 else ''}), probably in walls that were not measured; "
                                                      f"{n_w} windows and {n_d} doors are counted from the tags (the same tag read twice is counted once), at a standard size.", [],
                            "Check those places on the plan; their sizes are standard, not measured."))
    return kept, gap_tag, issues


def _describe(kept: list, gap_tag: dict, tag_source: str) -> list[dict]:
    """Each kept candidate as an opening with its kind and tag. The printed letter of a tag (D or W) is stronger evidence than a look at a crop, and no door is narrower than
    650 mm clear (the author's smallest is 750): a narrower one is a small window symbol with a neighbour's arc or tag beside it, whatever tag position was matched."""
    made = []
    for gi, (c, v) in enumerate(kept):
        text_tag = gap_tag.get(gi)
        tag, how = (text_tag, f"directly labelled ({tag_source})") if text_tag else (_crop_tag(v) or None, "directly labelled (read from the crop)")
        kind = (tag_kind(text_tag) if text_tag else None) or v["kind"]
        if kind == "door" and c["width_mm"] < 650 and tag_kind(_crop_tag(v)) != "door":
            kind = "window"
        made.append({**c, "kind": kind, "tag": tag, "how": how if tag else "inferred"})
    return made


def _match_schedule(made: list[dict], labels: dict, schedule: list | None) -> list[Issue]:
    """Give each opening the schedule type it is: by its tag, else by width when exactly one type of its kind fits. Returns the issues for tags the schedule does not have."""
    issues = []
    for m in made:
        if m["tag"] and m["tag"] in labels:
            m["mark"] = m["tag"]
            continue
        fit = [s for s in (schedule or []) if s["kind"] == m["kind"] and -0.30 * s["width_m"] * 1000 <= m["width_mm"] - s["width_m"] * 1000 <= 0.12 * s["width_m"] * 1000]  # a drawn gap is usually narrower than its type: the frame sits inside it
        if len({s["label"] for s in fit}) == 1:
            m["mark"], m["how"] = fit[0]["label"].upper(), "inferred (the only schedule type of that width)"
        else:
            m["mark"] = ""
            if m["tag"] and schedule:
                issues.append(Issue("tag_not_in_schedule", "warn", f"A {m['kind']} tagged {m['tag']} in {m['wall']} is not in the schedule.", [m["wall"]], "Check the tag against the schedule."))
    return issues


def _add_elements(model: DrawingModel, made: list[dict]) -> None:
    """Add the openings to the model with ids D-001 (doors), WN-001 (windows) and O-001 (bare openings), in order along each wall."""
    prefix = {"door": "D", "window": "WN", "opening": "O"}
    count = {k: 0 for k in prefix}
    for m in sorted(made, key=lambda m: (m["wall"], m["x0"] + m["y0"])):
        count[m["kind"]] += 1
        eid = f"{prefix[m['kind']]}-{count[m['kind']]:03d}"
        model.elements.append(Element(eid, m["kind"], "external" if m["external"] else "internal", model.page, model.floor, m["orient"], round(m["x0"], 1), round(m["y0"], 1),
                                      round(m["x1"], 1), round(m["y1"], 1), round(m["width_mm"] / 1000, 3), m["thickness"], evidence=m["how"] if m["mark"] else "inferred",
                                      confidence="medium" if m["mark"] else "low", parent=m["wall"], mark=m["mark"], width_mm=float(m["width_mm"]),
                                      notes=[] if m["tag"] else ["no tag could be read beside it"]))


def _opening_issues(model: DrawingModel, labels: dict, schedule: list | None, unverified: int) -> list[Issue]:
    """What a person should look at about the openings: widths against the schedule, wide windows, candidates the model could not check, types found more often than scheduled, and
    openings with no schedule type."""
    issues = []
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
    untyped = [o for o in model.openings() if not o.mark]
    if untyped and schedule:
        issues.append(Issue("openings_unmatched", "warn", f"{len(untyped)} openings found on the plan could not be matched to a schedule type, so their size is unknown.", [o.id for o in untyped][:20],
                            "Give their sizes, or check the tags on the plan."))
    return issues


def locate_openings(model: DrawingModel, img, scale: float, pdf: str | None = None, page: int | None = None, schedule: list | None = None, workers: int = 10,
                    tags: list | None = None) -> list[Issue]:
    """Find the openings on the floor, add them to the model (door D-001, window WN-001, opening O-001), tie each to its wall and to a schedule type, and return the issues raised.
    `schedule` is the opening types read from the schedule pages (label, width_m, height_m, count, kind); the model's walls decide external or internal. `tags` are the opening tags
    read from the plan by the model ((tag, x_mm, y_mm)); when None they come from the PDF's text layer. The steps: find candidates, have the model judge each crop, use the tags as
    evidence on a drawing that has them, describe and add the survivors, and report what needs a look."""
    cands = _find_candidates(model, img, scale, pdf, page, schedule)
    tag_source = "read by the model" if tags is not None else "text layer"
    if tags is None:
        tags = text_tags(pdf, page, model) if pdf and page else []
    out_dir = tempfile.mkdtemp()
    kept, _, unverified = _judge(cands, img, scale, out_dir, workers)
    gap_tag, _, _ = _pair_tags(kept, tags)
    issues: list[Issue] = []
    if len(tags) >= TAGGED_MIN:  # a drawing that tags its openings
        kept, gap_tag, issues = _use_tags_as_evidence(model, img, scale, kept, tags, tag_source, out_dir, workers)
    labels = {s["label"].upper(): s for s in (schedule or [])}
    made = _describe(kept, gap_tag, tag_source)
    issues += _match_schedule(made, labels, schedule)
    _add_elements(model, made)
    issues += _opening_issues(model, labels, schedule, unverified)
    model.issues += issues
    return issues
