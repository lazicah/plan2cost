"""Does the element library improve the crop check? Same candidates on plan 6 ground, the current prompt against one built from reference/element_library.json."""
import collections
import json
import sys

import plan2cost.openings as op
from plan2cost.drawing_model import DrawingModel
from plan2cost.markup import plan_image

PDF = "reference/plan6/Detached and Semi Detached WD (1).pdf"
USE = ["ARCH-DOOR-HINGED", "ARCH-DOOR-DOUBLE", "ARCH-DOOR-SLIDING", "ARCH-OPENING", "ARCH-WINDOW-CASEMENT", "ARCH-WINDOW-SLIDING", "ARCH-STAIR", "ARCH-COLUMN",
       "ARCH-WARDROBE", "SAN-WC", "SAN-WHB", "SAN-SHOWER", "SAN-SINK", "ARCH-WALL-EXT", "ARCH-WALL-INT", "CONV-HATCH", "CONV-OPENING-TAG", "CONV-DIMENSION"]


def library_prompt() -> str:
    lib = {e["element_id"]: e for e in json.load(open("reference/element_library.json"))["elements"]}
    lines = []
    for i in USE:
        e = lib[i]
        vf = e["visual_features"]
        lines.append(f"- {i} ({e['canonical_name']}): {e['definition']} Drawn as: {'; '.join(vf['primitive_patterns'])}. "
                     + (f"Do not assume: {'; '.join(vf['must_not_assume'])}. " if vf["must_not_assume"] else "")
                     + (f"Easily confused with: {', '.join(e['common_confusions'])}." if e["common_confusions"] else ""))
    return ("This is a crop of a floor plan. A thick orange bar marks a gap that was found in a wall. Decide what is at the bar, using this reference of how elements look on plans:\n"
            + "\n".join(lines) + "\nJudge only from what you can see; a plan convention can differ, so project symbols win over this reference. Read the tag printed beside the bar if there is one, exactly as printed, else null.\n"
            'Return only JSON: {"element_id": one id from the reference, or "NONE" if the bar is not on a gap in a wall, "tag": "W3" or null, "confused_with": id or null}')


def mapped_verify(path: str) -> dict:
    from plan2cost.client import image_part
    from plan2cost.document import _chat

    if not path:
        return {"kind": "not_opening"}
    r = _chat([{"type": "text", "text": LIB_PROMPT}, image_part(path)])
    i = str(r.get("element_id", "NONE"))
    kind = "door" if i.startswith("ARCH-DOOR") else "window" if i.startswith("ARCH-WINDOW") else "opening" if i == "ARCH-OPENING" else "not_opening"
    return {"kind": kind, "tag": r.get("tag"), "element_id": i}


if __name__ == "__main__":
    LIB_PROMPT = library_prompt()
    truth = {"900": 4, "600": 16}
    sched = [{"label": k, "width_m": v["width_mm"] / 1000, "height_m": v["height_mm"] / 1000, "count": v["quantity"], "kind": "window" if k.startswith("AW") else "door"}
             for k, v in json.load(open("eval/cases/plan6/openings_truth.json")).items() if not k.startswith("_")]
    base_verify = op._verify
    for name, fn in (("current prompt", base_verify), ("library prompt", mapped_verify), ("current prompt", base_verify), ("library prompt", mapped_verify)):
        op._verify = fn
        m = DrawingModel.load("/tmp/open_ground/model.json")
        m.elements = [e for e in m.elements if e.category == "wall"]
        m.issues = []
        img, scale = plan_image(m, PDF, m.page, None, 200)
        op.locate_openings(m, img, scale, PDF, m.page, sched)
        kinds = collections.Counter(o.category for o in m.openings())
        w = collections.Counter(round(o.width_mm / 300) * 300 for o in m.openings() if o.category == "window")
        print(f"{name:15} kinds {dict(kinds)} windows 600: {w.get(600, 0)}/16, 900: {w.get(900, 0)}/4, all windows {sum(w.values())}", flush=True)
