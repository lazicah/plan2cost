"""Read a whole drawing set: index every page, have the model say what each page is, then extract from the pages that matter.

The drawings are the guide; defaults are used only where the set is silent (see boq.py).
"""
import re

from plan2cost.kit.client import chat_json, image_part
from plan2cost.kit.pdf import page_count, page_text, render_pages, title_block_text
from plan2cost.takeoff.walls import Opening

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


def index_pages(pdf: str, limit: int = 250) -> list[dict]:
    out = []
    for n in range(1, page_count(pdf) + 1):
        title = title_block_text(pdf, n)
        body = re.sub(r"\s+", " ", page_text(pdf, n)).strip()
        out.append({"page": n, "title_block": title, "text": body[:limit]})
    return out


def classify_pages(pages: list[dict]) -> list[dict]:
    listing = "\n".join(f"Page {p['page']}: title block: {p['title_block'] or '(none)'} | page text: {p['text'] or '(none)'}" for p in pages)
    return chat_json([{"type": "text", "text": f"{CLASSIFY_PROMPT}\n{listing}"}])["pages"]


def extract_openings(pdf: str, pages: list[int], scratch: str) -> dict:
    images = render_pages(pdf, pages, scratch, dpi=160)
    hints = "\n".join(f"--- text on page {n} ---\n{page_text(pdf, n)[:1500]}" for n in pages)
    return chat_json([{"type": "text", "text": f"{OPENINGS_PROMPT}\n{hints}"}, *[image_part(p) for p in images]])


def extract_levels(pdf: str, pages: list[int], scratch: str) -> dict:
    images = render_pages(pdf, pages, scratch, dpi=110)
    return chat_json([{"type": "text", "text": f"{LEVELS_PROMPT}\nPages given: {pages}"}, *[image_part(p) for p in images]])


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


def storey_heights_m(levels: dict, floors: tuple[str, ...] = ("ground", "first", "second", "third")) -> dict[str, float]:
    """Floor-to-floor heights printed on the sections, mapped to floors in order from the ground floor level up.
    Floors the drawings do not give are left out, so the caller falls back to the default and flags it."""
    chain = [h for h in levels.get("storey_heights_mm", []) if "FLR" in h["from"].upper() or "FLOOR" in h["from"].upper()]
    return {f: h["value_mm"] / 1000 for f, h in zip(floors, chain)}


