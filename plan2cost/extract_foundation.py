"""Model-side extraction of foundation data from structural drawing pages. Deterministic maths stays in tools/foundation.py."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from plan2cost.client import get_client, image_part, model_name
from plan2cost.extract import RUNS_DIR, parse_json, update_index
from plan2cost.pdf import render_pages
from plan2cost.tools.foundation import PadBase, pit_excavation_m3, whole_units

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


RUNS_PROMPT = """You are reading a structural foundation layout for a quantity surveyor. Extract the continuous STRIP foundation runs
(the dashed double lines joining the pad bases) so strip girth can be measured grid line by grid line.

Rules:
- Walk the grid lines one at a time: each lettered line (A, B, C...) and each numbered line (1, 3, 4...).
- For every grid line list each continuous strip run on it. A run's length is the sum of the printed dimensions it spans
  (e.g. 2325 + 1500 + 3225 = 7050). Show the sum in "evidence". Never scale from the image and never invent a value.
- Take a run through pad bases (the strip continues between and through them); pad widths are deducted later by the QS.
- Do not list pad bases themselves. Do not list a run you cannot place on a grid line; ask in "questions" instead.
- Lengths in millimetres. "count" is how many identical runs this entry stands for.
- Reply with JSON only, matching:

{"strip_runs": [{"grid_line": str, "from": str, "to": str, "length_mm": number, "count": int, "evidence": str}], "questions": [str]}
"""


def extract_strip_runs(image_path: str) -> dict:
    resp = get_client().chat.completions.create(
        model=model_name(), temperature=0,
        messages=[{"role": "user", "content": [{"type": "text", "text": RUNS_PROMPT}, image_part(image_path)]}])
    return parse_json(resp.choices[0].message.content)


def strip_girths(data: dict, pads: list[PadBase]) -> dict:
    """Blockwork girth is the full runs; trench girth takes the pad widths off (pits are dug separately).
    Junction overlap deductions where walls butt are not modelled yet."""
    full = sum(r["length_mm"] / 1000 * int(r.get("count") or 1) for r in data.get("strip_runs", []))
    pad_widths = sum(p.width_m * p.count for p in pads)
    return {"fdn_blockwork_girth_230_m": whole_units(full) if full else 0, "strip_trench_girth_230_m": whole_units(full - pad_widths) if full else 0}


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


def score(data: dict, pads: list[PadBase], truth: dict, depth_m: float) -> dict:
    """Compare against the types read off the drawing by the author's survey, then the derived pit volume."""
    want = {p["type"]: p for p in truth["pad_bases"]}
    got = {p.type: p for p in pads}
    rows = {}
    for t, w in want.items():
        g = got.get(t)
        rows[f"base_{t}"] = bool(g and (g.length_m, g.width_m, g.count) == (w["length_mm"] / 1000, w["width_mm"] / 1000, w["count"]))
    strip = data.get("strip") or {}
    rows["strip_width_mm"] = strip.get("width_mm") == truth["strip"]["width_mm"]
    rows["strip_thickness_mm"] = strip.get("thickness_mm") == truth["strip"]["thickness_mm"]
    rows["pit_excavation_m3"] = (pit_excavation_m3(pads, depth_m), truth["pit_excavation_column_bases_m3"])
    if "strip_runs" in data:
        g = strip_girths(data, pads)
        rows["blockwork_girth_m"] = (g["fdn_blockwork_girth_230_m"], truth["fdn_blockwork_girth_230_m"])
        rows["trench_girth_m"] = (g["strip_trench_girth_230_m"], truth["strip_trench_girth_230_m"])
    return rows


def save_foundation_run(*, case: str, data: dict, rows: dict, questions: list[str], note: str = "") -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = len([d for d in RUNS_DIR.iterdir() if d.is_dir()]) + 1
    model = model_name()
    out = RUNS_DIR / f"{n:03d}-{case}-foundation-{model.lower().replace('/', '-')}"
    out.mkdir()
    hits = [v for v in rows.values() if isinstance(v, bool)]
    pct = {k: round(abs(v[0] - v[1]) / v[1] * 100, 1) for k, v in rows.items() if isinstance(v, tuple)}
    pct["fields_wrong_pct"] = round(100 * hits.count(False) / len(hits), 1)
    when = datetime.now()
    (out / "result.json").write_text(json.dumps({"case": case, "floor": "foundation", "model": model, "time": when.isoformat(timespec="seconds"),
                                                 "extraction": data, "checks": rows, "pct_error": pct, "questions": questions}, indent=2))
    table = "\n".join(f"| {k} | {'ok' if v is True else 'WRONG' if v is False else f'model {v[0]}, survey {v[1]}'} |" for k, v in rows.items())
    (out / "report.md").write_text(
        f"# Run {n:03d}: {case} foundation, {model}\n\n{when:%Y-%m-%d %H:%M}\n\n## Checks against the drawing as read by the author's survey\n\n"
        f"| item | result |\n|---|---|\n{table}\n\n## Notes\n\n{note or '(none)'}\n\n## Extraction\n\n```json\n{json.dumps(data, indent=2)}\n```\n\n"
        "## Questions the agent asked instead of guessing\n\n" + "\n".join(f"- {q}" for q in questions) + "\n")
    update_index()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", required=True, help="comma-separated 1-based pages, e.g. 3,4,5")
    ap.add_argument("--truth", help="eval/cases/<id>/foundation_truth.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--girth", action="store_true", help="also walk the grid lines on the first page for strip girth")
    ap.add_argument("--scratch", default="/tmp/p2c-pages")
    args = ap.parse_args()
    images = render_pages(args.pdf, [int(p) for p in args.pages.split(",")], args.scratch)
    data = extract_foundation(images)
    pads, questions = to_pads(data)
    if args.girth:
        layout = render_pages(args.pdf, [int(args.pages.split(",")[0])], args.scratch, dpi=200)[0]
        runs = extract_strip_runs(layout)
        data["strip_runs"] = runs.get("strip_runs", [])
        questions += runs.get("questions", [])
    print(json.dumps(data, indent=2))
    if args.truth:
        truth = json.loads(Path(args.truth).read_text())
        rows = score(data, pads, truth, depth_m=1.2)
        print(rows)
        print("saved", save_foundation_run(case=args.case, data=data, rows=rows, questions=questions, note=args.note))


if __name__ == "__main__":
    main()
