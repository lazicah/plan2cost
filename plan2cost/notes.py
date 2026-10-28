"""Specification notes printed on drawings (roof sheet, ceiling, floor finish, slab thickness...). The model reads the page text and
returns each note with the exact quote; code keeps only notes whose quote is really on the page."""
import re

from plan2cost.client import get_client, model_name
from plan2cost.extract import parse_json
from plan2cost.pdf import page_text

TOPICS = ["roof_covering", "roof_structure", "ceiling", "floor_finish", "slab", "blinding_hardcore", "foundation", "wall_material",
          "wall_finish", "paint", "balustrade", "staircase", "door_window", "waterproofing", "other"]

PROMPT = f"""You are reading the text printed on drawing pages, for a quantity surveyor. Extract the SPECIFICATION NOTES: statements that say
what a building element is made of, how thick it is, its size, spacing or finish (for example a roofing sheet gauge, timber sizes and
spacing, a ceiling type, a floor finish and its bed, a slab thickness).

Rules:
- Use only text that is on the pages. "quote" must be copied exactly from the page text, as one continuous piece (at least a few words).
- "topic" is one of: {', '.join(TOPICS)}.
- Do not extract room names, dimensions or labels. Do not merge notes from different places.
- Reply with JSON only: {{"notes": [{{"page": int, "topic": str, "summary": str, "quote": str}}]}}
"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def extract_notes(pdf: str, pages: list[int], chat=None) -> dict:
    chat = chat or _chat
    texts = {p: page_text(pdf, p) for p in pages}
    body = "\n\n".join(f"=== Page {p} ===\n{t}" for p, t in texts.items() if t.strip())
    if not body:
        return {"notes": [], "dropped": 0, "pages_without_text": pages}
    raw = chat(f"{PROMPT}\n{body}").get("notes", [])
    kept, dropped = [], 0
    for n in raw:
        text = texts.get(n.get("page"), "")
        if n.get("quote") and _norm(n["quote"]) in _norm(text) and len(_norm(n["quote"])) >= 12:
            kept.append({k: n.get(k) for k in ("page", "topic", "summary", "quote")})
        else:
            dropped += 1  # a quote that is not on the page is never kept
    return {"notes": kept, "dropped": dropped, "pages_without_text": [p for p, t in texts.items() if not t.strip()]}


def _chat(prompt: str) -> dict:
    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=[{"role": "user", "content": prompt}])
    return parse_json(resp.choices[0].message.content)
