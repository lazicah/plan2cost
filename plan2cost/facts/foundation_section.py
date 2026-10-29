"""The foundation cross-section on a structural drawing: the layers and the dimensions printed beside it. The model reads the section
image; code checks every number is really printed on the page and that the layers add up to the overall depth."""
import re

from plan2cost.kit.client import get_client, image_part, model_name
from plan2cost.kit.client import parse_json
from plan2cost.kit.pdf import page_text, render_pages

PROMPT = """You are reading a structural foundation drawing for a quantity surveyor. Find the cross-section of the strip foundation
(usually titled SECTION A-A) with its notes and the vertical dimension chain printed beside it.

Rules:
- Use only numbers printed on the drawing. Never scale. Millimetres.
- Read the layers from the section: the floor slab, the filling under it (hardcore and laterite, often given as one total),
  the strip footing, the blinding under the footing. Read the footing width and thickness from its note (e.g. 675mm x 225mm).
- The vertical chain gives each layer's thickness and an overall figure. Say which printed number belongs to which layer.
- If a layer's thickness is not printed, use null. Do not split a total into parts.
- Put anything missing or inconsistent in "questions".
- Reply with JSON only:

{"footing_width_mm": number|null, "footing_thickness_mm": number|null, "blinding_mm": number|null, "blinding_material": str|null,
 "slab_mm": number|null, "mesh": str|null, "fill_depth_mm": number|null, "hardcore_mm": number|null, "laterite_mm": number|null,
 "overall_depth_mm": number|null, "dimensions": [{"value_mm": number, "meaning": str}], "questions": [str]}
"""

FIELDS = ("footing_width_mm", "footing_thickness_mm", "blinding_mm", "slab_mm", "fill_depth_mm", "hardcore_mm", "laterite_mm", "overall_depth_mm")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def check_section(data: dict, text: str, tol_mm: float = 5.0) -> dict:
    """Keep only numbers that are printed on the page, and test that the layers add up to the overall depth."""
    printed = _tokens(text)
    kept, unprinted = {}, []
    for f in FIELDS:
        v = data.get(f)
        if v is None:
            continue
        if float(v).is_integer() and str(int(v)) in printed:
            kept[f] = v
        else:
            unprinted.append(f)
    questions = list(data.get("questions", []))
    if "fill_depth_mm" in kept:  # the filling is printed as one total: a hardcore/laterite split is the model's, not the drawing's
        for f in ("hardcore_mm", "laterite_mm"):
            if kept.pop(f, None) is not None:
                questions.append(f"{f} was not used: the drawing prints the filling as one depth ({kept['fill_depth_mm']:g}mm), not split.")
    layers = [kept.get(k) for k in ("slab_mm", "fill_depth_mm", "footing_thickness_mm", "blinding_mm")]
    overall = kept.get("overall_depth_mm")
    closes = None
    if overall and all(v is not None for v in layers):
        closes = abs(sum(layers) - overall) <= tol_mm
        if not closes:
            questions.append(f"The layers add up to {sum(layers):g}mm but the overall depth printed is {overall:g}mm; which is right?")
    for f in unprinted:
        questions.append(f"{f} = {data[f]} is not printed on the page, so it was not used.")
    return {"values": kept, "unprinted": unprinted, "layers_close": closes, "questions": questions,
            "materials": {k: data.get(k) for k in ("blinding_material", "mesh")}, "dimensions": data.get("dimensions", [])}


def read_foundation_section(pdf: str, page: int, scratch: str, chat=None) -> dict:
    text = page_text(pdf, page)
    if chat is None:
        img = render_pages(pdf, [page], scratch, dpi=200)[0]
        resp = get_client().chat.completions.create(model=model_name(), temperature=0,
                                                    messages=[{"role": "user", "content": [{"type": "text", "text": PROMPT}, image_part(img)]}])
        data = parse_json(resp.choices[0].message.content)
    else:
        data = chat(PROMPT)
    out = check_section(data, text)
    out["page"] = page
    return out
