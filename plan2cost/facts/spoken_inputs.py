"""The estimate's inputs from what the user said: the model reads the transcript, code keeps only values that make sense. Anything not said stays empty, so the form is
never filled with a guess."""
from plan2cost.kit.progress import FINISH_LEVELS, ROOF_TYPES

PROMPT = """A person described a building they want costed. Read their words and return only JSON with the details they actually stated, null for anything not said:
{"storey_height_m": number or null (floor to floor, in metres; convert feet to metres), "roof_type": "gable" or "hip" or "flat" or null, "pitch_deg": number or null (roof pitch in degrees),
"overhang_m": number or null (roof overhang in metres), "finish_level": "standard" or "premium" or null}
Do not guess. 'Hipped' means hip; 'pitched' alone is not a roof type.

What they said: """


def clean(raw: dict) -> dict:
    """Keep a value only if it is in the range the form accepts."""
    out: dict = {}

    def num(key, lo, hi):
        try:
            v = float(raw.get(key))
        except (TypeError, ValueError):
            return
        if lo <= v <= hi:
            out[key] = round(v, 2)
    num("storey_height_m", 2.0, 6.0)
    num("pitch_deg", 5, 60)
    num("overhang_m", 0, 2.0)
    if raw.get("roof_type") in ROOF_TYPES:
        out["roof_type"] = raw["roof_type"]
    if raw.get("finish_level") in FINISH_LEVELS:
        out["finish_level"] = raw["finish_level"]
    return out


def read_spoken_inputs(transcript: str) -> dict:
    from plan2cost.kit.client import chat_json

    if not transcript.strip():
        return {}
    return clean(chat_json([{"type": "text", "text": PROMPT + transcript}]))
