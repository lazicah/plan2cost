"""Read a whole drawing set: index every page, have the model say what each page is, then extract from the pages that matter.

The drawings are the guide; defaults are used only where the set is silent (see boq.py).
"""
import re

from plan2cost.client import get_client, image_part, model_name
from plan2cost.extract import parse_json
from plan2cost.pdf import page_count, page_text, render_pages, render_tiles, title_block_text
from plan2cost.tools.walls import Opening

ROLES = ["cover", "site", "floor_plan", "roof_plan", "section", "elevation", "ceiling_plan", "detail", "opening_schedule",
         "structural_foundation", "structural_other", "other"]

CLASSIFY_PROMPT = f"""You are indexing a set of construction drawings for a quantity surveyor. For every page below you get its number and
the text in its title block (drawing title and number) and the start of the text on the page. Trust the drawing title. Say what each page is. Roles: {', '.join(ROLES)}.
A page showing door or window types with dimensions, descriptions and quantities is "opening_schedule".
Reply with JSON only: {{"pages": [{{"page": int, "role": str, "title": str, "floor": str|null}}]}}
"""

OPENINGS_PROMPT = """You are reading door and window schedule pages from a drawing set, for a quantity surveyor.
Extract every opening TYPE shown, across all the pages given.

Rules:
- Use only what is printed. The width and height are the dimensions drawn on the type's elevation (millimetres).
  The quantity is the QUANTITY or "Grand total" printed for that type. Never invent or round a value.
- "kind" is "door" or "window". "material" is as described (timber, steel, glass, aluminium...).
- If a location table says which room or floor each one is in, put the floors in "floors"; otherwise leave it empty.
- Put anything missing, unreadable or inconsistent (e.g. a quantity that disagrees with the location table) in "questions".
- Reply with JSON only:

{"openings": [{"mark": str, "kind": "door"|"window", "material": str, "width_mm": number, "height_mm": number,
 "quantity": int, "floors": [str], "evidence": str}], "questions": [str]}
"""

LEVELS_PROMPT = """You are reading building sections and elevations for a quantity surveyor. Extract the printed level figures
(ground floor level, first floor level, roof base level, apex, natural ground level, and any floor-to-floor or clear heights).
Use only printed numbers, in millimetres. Do not infer. Reply with JSON only:

{"levels": [{"name": str, "value_mm": number, "page": int}], "storey_heights_mm": [{"from": str, "to": str, "value_mm": number}],
 "questions": [str]}
"""


PLAN_OPENINGS_PROMPT = """You are reading floor plans (and elevations, if given) for a quantity surveyor. There is NO door and window schedule,
so find the openings from the drawing symbols.

How to read them:
- Door: a gap in a wall with a swing arc, or a leaf line; sliding doors show offset parallel leaves. Window: a thin multi-line
  break in a wall (sill/glazing lines). Other openings: archways or wall gaps with no leaf.
- Width: the dimension printed beside or along the opening, or an opening width in a dimension chain. Use only printed numbers.
- Height: only from an elevation or section if the opening is dimensioned there or its sill and head levels are printed.
  If no height is printed, set height_mm to null. Never guess a height.
- "wall" is "external" if the opening is in an outside wall and "internal" if it is between rooms.
- Group identical openings (same kind, width, wall, floor) into one entry with a "count"; count each opening once.
- Put anything you cannot size or classify in "questions" instead of guessing.
- Reply with JSON only:

{"openings": [{"floor": str, "kind": "door"|"window"|"other", "width_mm": number|null, "height_mm": number|null, "wall": "external"|"internal",
 "count": int, "evidence": str}], "questions": [str]}
"""

DEFAULT_OPENING_HEIGHT_M = {"door": 2.1, "window": 1.2, "other": 2.1}  # used only when no schedule or elevation gives it


def index_pages(pdf: str, limit: int = 250) -> list[dict]:
    out = []
    for n in range(1, page_count(pdf) + 1):
        title = title_block_text(pdf, n)
        body = re.sub(r"\s+", " ", page_text(pdf, n)).strip()
        out.append({"page": n, "title_block": title, "text": body[:limit]})
    return out


def _chat(content: list) -> dict:
    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=[{"role": "user", "content": content}])
    return parse_json(resp.choices[0].message.content)


def classify_pages(pages: list[dict]) -> list[dict]:
    listing = "\n".join(f"Page {p['page']}: title block: {p['title_block'] or '(none)'} | page text: {p['text'] or '(none)'}" for p in pages)
    return _chat([{"type": "text", "text": f"{CLASSIFY_PROMPT}\n{listing}"}])["pages"]


def extract_openings(pdf: str, pages: list[int], scratch: str) -> dict:
    images = render_pages(pdf, pages, scratch, dpi=160)
    hints = "\n".join(f"--- text on page {n} ---\n{page_text(pdf, n)[:1500]}" for n in pages)
    return _chat([{"type": "text", "text": f"{OPENINGS_PROMPT}\n{hints}"}, *[image_part(p) for p in images]])


def extract_levels(pdf: str, pages: list[int], scratch: str) -> dict:
    images = render_pages(pdf, pages, scratch, dpi=110)
    return _chat([{"type": "text", "text": f"{LEVELS_PROMPT}\nPages given: {pages}"}, *[image_part(p) for p in images]])


EXTERNAL_MATERIALS = ("steel", "glass", "aluminium", "alum")


def to_openings(data: dict) -> tuple[list[Opening], list[str]]:
    """Schedule entries become Openings. Doors in timber are treated as internal and the rest as external: an assumption
    that the caller should flag, since the schedule does not say."""
    openings, questions = [], list(data.get("questions", []))
    for o in data.get("openings", []):
        if not (o.get("width_mm") and o.get("height_mm") and o.get("quantity")):
            questions.append(f"{o.get('mark')}: size or quantity is not readable on the schedule.")
            continue
        kind = o.get("kind", "window")
        external = kind == "window" or any(m in str(o.get("material", "")).lower() for m in EXTERNAL_MATERIALS)
        openings.append(Opening(o["mark"], o["width_mm"] / 1000, o["height_mm"] / 1000, int(o["quantity"]), kind, external))
    return openings, questions


def extract_plan_openings(pdf: str, pages: list[int], scratch: str) -> dict:
    images = render_pages(pdf, pages, scratch, dpi=170)
    return _chat([{"type": "text", "text": f"{PLAN_OPENINGS_PROMPT}\nPages given, in order: {pages}"}, *[image_part(p) for p in images]])


TILE_NOTE = """This image is one TILE (row {r}, column {c} of a {rows} x {cols} grid) of the {floor} floor plan. Report only the openings whose
centre lies inside this tile; ignore any that are cut by the tile edge and belong mostly to a neighbouring tile."""


def extract_plan_openings_tiled(pdf: str, page: int, floor: str, scratch: str, cols: int = 2, rows: int = 2) -> dict:
    """Read one floor plan tile by tile so door and window symbols are legible, then pool the results."""
    merged: dict = {"openings": [], "questions": []}
    for i, tile in enumerate(render_tiles(pdf, page, scratch, cols=cols, rows=rows)):
        note = TILE_NOTE.format(r=i // cols, c=i % cols, rows=rows, cols=cols, floor=floor)
        part = _chat([{"type": "text", "text": f"{PLAN_OPENINGS_PROMPT}\n{note}"}, image_part(tile)])
        for o in part.get("openings", []):
            o["floor"] = floor
            o["tile"] = f"r{i // cols}c{i % cols}"
            merged["openings"].append(o)
        merged["questions"] += part.get("questions", [])
    return merged


def plan_openings_to_openings(data: dict) -> tuple[list[Opening], list[str]]:
    """Openings found from plan symbols. A missing height falls back to the standard one and is asked about, never silent."""
    openings, questions = [], list(data.get("questions", []))
    for i, o in enumerate(data.get("openings", []), 1):
        kind = o.get("kind") if o.get("kind") in DEFAULT_OPENING_HEIGHT_M else "other"
        if not o.get("width_mm") or not o.get("count"):
            questions.append(f"{o.get('floor')} {kind} #{i}: width not printed on the plan.")
            continue
        h = o.get("height_mm")
        if not h:
            h = DEFAULT_OPENING_HEIGHT_M[kind] * 1000
            questions.append(f"{kind} {int(o['width_mm'])}mm ({o.get('floor')}): no height on an elevation; assumed {int(h)}mm. Confirm?")
        openings.append(Opening(f"{kind[0].upper()}{i}", o["width_mm"] / 1000, h / 1000, int(o["count"]), kind, o.get("wall") == "external"))
    return openings, questions


def storey_heights_m(levels: dict, floors: tuple[str, ...] = ("ground", "first", "second", "third")) -> dict[str, float]:
    """Floor-to-floor heights printed on the sections, mapped to floors in order from the ground floor level up.
    Floors the drawings do not give are left out, so the caller falls back to the default and flags it."""
    chain = [h for h in levels.get("storey_heights_mm", []) if "FLR" in h["from"].upper() or "FLOOR" in h["from"].upper()]
    return {f: h["value_mm"] / 1000 for f, h in zip(floors, chain)}


def read_document(pdf: str, scratch: str) -> dict:
    pages = classify_pages(index_pages(pdf))
    by_role: dict[str, list[int]] = {}
    for p in pages:
        by_role.setdefault(p["role"], []).append(p["page"])
    out = {"pages": pages, "openings": {"openings": [], "questions": []}, "levels": {"levels": [], "questions": []}}
    if by_role.get("opening_schedule"):
        out["openings"] = extract_openings(pdf, by_role["opening_schedule"], scratch)
    if not by_role.get("opening_schedule"):  # no schedule: fall back to symbols on the plans, heights from elevations
        plan_pages = by_role.get("floor_plan", []) + by_role.get("elevation", [])
        out["openings_from_plan"] = extract_plan_openings(pdf, plan_pages, scratch) if plan_pages else {"openings": [], "questions": []}
    if by_role.get("section"):
        out["levels"] = extract_levels(pdf, by_role["section"][:2], scratch)
    return out


def score_openings(data: dict, truth: dict) -> dict:
    got = {o["mark"]: o for o in data.get("openings", [])}
    rows = {}
    for mark, w in truth.items():
        if mark.startswith("_"):
            continue
        g = got.get(mark)
        rows[mark] = bool(g and (g["width_mm"], g["height_mm"], g["quantity"]) == (w["width_mm"], w["height_mm"], w["quantity"]))
    return rows


def save_document_run(*, case: str, result: dict, rows: dict, note: str = "") -> "Path":
    import json
    from datetime import datetime
    from pathlib import Path

    from plan2cost.extract import RUNS_DIR, update_index

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = len([d for d in RUNS_DIR.iterdir() if d.is_dir()]) + 1
    model = model_name()
    out = RUNS_DIR / f"{n:03d}-{case}-document-{model.lower().replace('/', '-')}"
    out.mkdir()
    questions = result["openings"].get("questions", []) + result["levels"].get("questions", [])
    wrong = 100 * list(rows.values()).count(False) / len(rows) if rows else 0
    when = datetime.now()
    (out / "result.json").write_text(json.dumps({"case": case, "floor": "document", "model": model, "time": when.isoformat(timespec="seconds"),
                                                 "extraction": result, "checks": rows, "pct_error": {"opening_types_wrong_pct": round(wrong, 1)},
                                                 "questions": questions}, indent=2))
    roles = "\n".join(f"| {p['page']} | {p['role']} | {p.get('title', '')} |" for p in result["pages"])
    checks = "\n".join(f"| {k} | {'ok' if v else 'WRONG'} |" for k, v in rows.items())
    (out / "report.md").write_text(
        f"# Run {n:03d}: {case} whole document, {model}\n\n{when:%Y-%m-%d %H:%M}\n\n"
        f"The model indexed every page of the set, classified each page, then read the opening schedules and section levels.\n\n"
        f"## Page roles\n\n| page | role | title |\n|---|---|---|\n{roles}\n\n"
        f"## Opening types vs the author's survey\n\n| mark | result |\n|---|---|\n{checks}\n\n"
        f"## Levels read from the sections\n\n```json\n{json.dumps(result['levels'], indent=2)}\n```\n\n"
        f"## Notes\n\n{note or '(none)'}\n\n## Questions the agent asked instead of guessing\n\n" + "\n".join(f"- {q}" for q in questions) + "\n")
    update_index()
    return out


def main() -> None:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--case", required=True)
    ap.add_argument("--truth", help="eval/cases/<id>/openings_truth.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--scratch", default="/tmp/p2c-doc")
    args = ap.parse_args()
    result = read_document(args.pdf, args.scratch)
    rows = score_openings(result["openings"], json.loads(Path(args.truth).read_text())) if args.truth else {}
    print({p["page"]: p["role"] for p in result["pages"]}, rows)
    print("saved", save_document_run(case=args.case, result=result, rows=rows, note=args.note))


if __name__ == "__main__":
    main()


def score_plan_openings(found: list[dict], schedule_truth: dict, tolerance_mm: int = 60) -> dict:
    """Recall and precision of symbol-detected openings against the schedule: an opening counts when kind matches and the
    width is within tolerance of a schedule width (plan widths can include the frame). Each schedule opening is matched once."""
    from collections import Counter

    truth = Counter()
    for mark, t in schedule_truth.items():
        if not mark.startswith("_"):
            truth[("window" if mark.startswith("AW") else "door", t["width_mm"])] += t["quantity"]
    left, hits, total_found = Counter(truth), 0, 0
    for o in found:
        n = int(o.get("count") or 0)
        total_found += n
        for _ in range(n):
            key = next((k for k in left if left[k] > 0 and k[0] == o.get("kind") and abs(k[1] - (o.get("width_mm") or -1e9)) <= tolerance_mm), None)
            if key:
                left[key] -= 1
                hits += 1
    total_truth = sum(truth.values())
    return {"schedule_openings": total_truth, "found": total_found, "matched": hits,
            "recall_pct": round(100 * hits / total_truth, 1), "precision_pct": round(100 * hits / total_found, 1) if total_found else 0.0}
