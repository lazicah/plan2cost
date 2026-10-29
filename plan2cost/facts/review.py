"""Model review of an annotated plan: a second pair of eyes that can only raise questions. The review looks at the plan with the measured walls
drawn and numbered and says what looks wrong against a checklist of the usual ways a wall measurement fails. Whatever it says is recorded as an
issue marked "model review" with the evidence "inferred"; it never changes a wall or a quantity, because a model's reading of an image is the
weakest evidence in the system."""
from plan2cost.drawing.model import DrawingModel, Issue

PROMPT = """This is a floor plan with the walls a program measured drawn on it: red lines are external walls, blue internal walls, orange rings mark walls
with an open doubt, and the numbers are wall ids. Review the measurement against the drawing. Look for:
- walls of the building that are drawn on the plan but have no coloured line on them (missed walls), including whole outer walls and short partitions;
- coloured lines that are not on a wall: grid lines, dimension or extension lines, window frames, stairs, furniture, or a line running past the building;
- two ids on the same wall (counted twice);
- a wall that is external on the plan but shown as internal, or the reverse.
Judge only what you can see. Do not guess hidden walls. If you are unsure, say so; do not invent problems.
Return only JSON: {"missed": [{"where": "short plain description of the place", "what": "what looks missing"}],
"not_walls": [{"id": "007", "why": "..."}], "duplicates": [{"ids": ["002","003"]}], "wrong_side": [{"id": "012", "why": "..."}], "overall": "one sentence"}"""


def review_model(model: DrawingModel, markup_path: str) -> list[Issue]:
    """Ask the model to review the annotated plan. Returns issues to add; the model itself is left unchanged until the caller appends them."""
    from plan2cost.kit.client import chat_json, image_part

    r = chat_json([{"type": "text", "text": PROMPT}, image_part(markup_path)])
    known = {e.id for e in model.walls()}
    wid = lambda n: f"W-{int(str(n).replace('W-', '')):03d}" if str(n).replace("W-", "").isdigit() else None
    out = []
    for m in r.get("missed", []):
        out.append(Issue("review_missed", "warn", f"The model reviewing the plan thinks a wall may be missing: {m.get('what', '')} ({m.get('where', '')}).", [],
                         "Look at that part of the plan; if there is a wall, add it.", "model review"))
    for n in r.get("not_walls", []):
        i = wid(n.get("id"))
        if i in known:
            out.append(Issue("review_not_wall", "warn", f"The model reviewing the plan thinks {i} is not a wall: {n.get('why', '')}.", [i], "Check this run on the plan.", "model review"))
    for d in r.get("duplicates", []):
        ids = [i for i in (wid(x) for x in d.get("ids", [])) if i in known]
        if len(ids) >= 2:
            out.append(Issue("review_duplicate", "warn", f"The model reviewing the plan thinks {' and '.join(ids)} are the same wall.", ids, "Check for a double count.", "model review"))
    for n in r.get("wrong_side", []):
        i = wid(n.get("id"))
        if i in known:
            out.append(Issue("review_side", "info", f"The model reviewing the plan thinks {i} is classed on the wrong side (external or internal): {n.get('why', '')}.", [i], "", "model review"))
    return out
