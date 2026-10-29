"""The model reads pad bases and their schedule from structural drawing pages. Deterministic maths stays in takeoff/foundation.py."""
import re

from plan2cost.kit.client import get_client, image_part, model_name, parse_json
from plan2cost.takeoff.foundation import PadBase

PROMPT = """You are reading structural foundation drawings for a quantity surveyor. Extract only what is printed.

Rules:
- Use only dimensions and notes printed on the drawings. Never scale from the image and never invent a value.
- Lengths in millimetres, exactly as printed.
- Pad bases (isolated column bases): one entry per base TYPE with its plan size, the number of bases ("4no Thus" means 4),
  the thickness if shown, and the reinforcement note exactly as printed (e.g. "06-Y1202@200c/c B").
- Strip foundation: width and thickness from the section note (e.g. "675mm x 225mm mass concrete strip foundation"),
  blinding thickness and material, ground slab thickness, mesh reference, and any hardcore or backfill note.
- Section levels: overall depth figures printed beside the section, each with what you think it measures.
- Put anything missing or ambiguous in "questions" instead of guessing.
- Reply with JSON only, matching:

{"strip": {"width_mm": number|null, "thickness_mm": number|null, "blinding_mm": number|null, "blinding_material": str|null,
  "slab_mm": number|null, "mesh": str|null, "notes": [str]},
 "pad_bases": [{"type": str, "length_mm": number, "width_mm": number, "thickness_mm": number|null, "count": int, "rebar": [str]}],
 "section_depths_mm": [{"value": number, "meaning": str}],
 "questions": [str]}
"""


def extract_foundation(image_paths: list[str]) -> dict:
    resp = get_client().chat.completions.create(
        model=model_name(), temperature=0,
        messages=[{"role": "user", "content": [{"type": "text", "text": PROMPT}, *[image_part(p) for p in image_paths]]}])
    return parse_json(resp.choices[0].message.content)


def to_pads(data: dict) -> tuple[list[PadBase], list[str]]:
    pads, questions = [], list(data.get("questions", []))
    for p in data.get("pad_bases", []):
        if not (p.get("length_mm") and p.get("width_mm") and p.get("count")):
            questions.append(f"Base type {p.get('type')}: size or number is not readable on the drawing.")
            continue
        pads.append(PadBase(re.sub(r"\D", "", str(p["type"])) or str(p["type"]), p["length_mm"] / 1000, p["width_mm"] / 1000, int(p["count"]),
                        (p["thickness_mm"] / 1000) if p.get("thickness_mm") else 0.25, tuple(p.get("rebar") or ())))
    return pads, questions


