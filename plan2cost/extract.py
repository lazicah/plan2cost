"""Model-side extraction: read wall dimensions from a plan image. Deterministic maths stays in tools/takeoff.py."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from plan2cost.client import get_client, image_part, model_name
from plan2cost.tools.takeoff import DimKind, WallRun, girth

PROMPT = """You are reading an architectural floor plan for a quantity surveyor. Extract the WALL RUNS needed for masonry girth.

Dimensioning patterns. Tag every length you take with how it was measured:
- "centre_line": wall centre to wall centre (grid-to-grid chains). Often the topmost dimension chain.
- "end_to_end": overall external face to external face. Often the chains below the centre-line chain.
- "in_to_in": clear distance between internal faces, usually written inside rooms.
The position hints above are only hints; decide from the numbers and the drawing. If you cannot tell the kind, use "unknown".

Wall thickness: read it from the drawing's own labels (e.g. 230, 150) and report it exactly as drawn. Do not convert to block sizes.

Rules:
- Use only dimensions printed on the drawing. Never scale from the image and never invent a value.
- Lengths in millimetres, exactly as printed.
- "count" is how many identical runs this entry stands for (e.g. mirrored units).
- "end_thickness_mm" is the thickness of the wall met at each end of the run, or null if the same as the run.
- Put anything missing or ambiguous in "questions" for the user instead of guessing.
- Reply with JSON only, matching:

{"floor": str, "wall_runs": [{"label": str, "length_mm": number, "kind": "centre_line"|"end_to_end"|"in_to_in"|"unknown",
 "thickness_mm": number|null, "end_thickness_mm": [number, number]|null, "count": int, "external": bool, "evidence": str}],
 "questions": [str]}
"""


def parse_json(text: str) -> dict:
    """Models often wrap JSON in prose or fences; take the outermost object."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model reply")
    return json.loads(m.group(0))


def to_runs(data: dict) -> tuple[list[WallRun], list[str]]:
    """Validate extraction into WallRuns; anything unusable becomes a question, not a guess."""
    runs, questions = [], list(data.get("questions", []))
    for r in data.get("wall_runs", []):
        label = r.get("label", "?")
        try:
            kind = DimKind(r.get("kind"))
        except ValueError:
            questions.append(f"{label}: which dimension kind is {r.get('length_mm')}mm (centre-line, end-to-end or in-to-in)?")
            continue
        if not r.get("thickness_mm") or not r.get("length_mm"):
            questions.append(f"{label}: wall thickness or length is not readable on the drawing.")
            continue
        end = tuple(r["end_thickness_mm"]) if r.get("end_thickness_mm") else None
        runs.append(WallRun(label, r["length_mm"] / 1000, kind, int(r["thickness_mm"]), end,
                            int(r.get("count") or 1), bool(r.get("external"))))
    return runs, questions


def extract_walls_image(image_path: str, floor: str) -> dict:
    return extract_walls(image_path, floor)


def extract_walls(image_path: str, floor: str) -> dict:
    resp = get_client().chat.completions.create(
        model=model_name(),
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"{PROMPT}\nFloor: {floor}"},
            image_part(image_path),
        ]}],
    )
    return parse_json(resp.choices[0].message.content)


RUNS_DIR = Path("eval/runs")


def save_run(*, case: str, floor: str, model: str, data: dict, pred: dict, errors: dict | None,
             questions: list[str], note: str = "", when: datetime | None = None) -> Path:
    """Write one run's raw output and a readable report under eval/runs/, then refresh the index."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = len([d for d in RUNS_DIR.iterdir() if d.is_dir()]) + 1
    slug = re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")
    out = RUNS_DIR / f"{n:03d}-{case}-{floor}-{slug}"
    out.mkdir()
    when = when or datetime.now()
    (out / "result.json").write_text(json.dumps(
        {"case": case, "floor": floor, "model": model, "time": when.isoformat(timespec="seconds"),
         "extraction": data, "girth": pred, "pct_error": errors, "questions": questions}, indent=2))
    rows = "\n".join(
        f"| {r.get('label')} | {r.get('length_mm')} | {r.get('kind')} | {r.get('thickness_mm')} | {r.get('count')} |"
        for r in data.get("wall_runs", []))
    err = "\n".join(f"| {k} | {pred.get(k)} | {v}% |" for k, v in (errors or {}).items())
    (out / "report.md").write_text(
        f"# Run {n:03d}: {case} {floor} floor, {model}\n\n{when:%Y-%m-%d %H:%M}\n\n"
        f"## Girth vs the author's surveyed truth\n\n| quantity | model (m) | error |\n|---|---|---|\n{err}\n\n"
        f"## Notes\n\n{note or '(none)'}\n\n"
        f"## Wall runs extracted\n\n| label | length mm | kind | thickness mm | count |\n|---|---|---|---|---|\n{rows}\n\n"
        "## Questions the agent asked instead of guessing\n\n" + "\n".join(f"- {q}" for q in questions) + "\n")
    update_index()
    return out


def update_index() -> None:
    lines = ["# Extraction runs\n", "Progress log, one row per run (newest last). Error is % off the author's surveyed girth.\n",
             "| run | model | floor | mean error | worst error | questions |", "|---|---|---|---|---|---|"]
    for d in sorted(p for p in RUNS_DIR.iterdir() if p.is_dir()):
        r = json.loads((d / "result.json").read_text())
        e = [v for v in (r.get("pct_error") or {}).values() if v != float("inf")]
        mean = f"{sum(e) / len(e):.1f}%" if e else "n/a"
        worst = f"{max(e):.1f}%" if e else "n/a"
        lines.append(f"| [{d.name}]({d.name}/report.md) | {r['model']} | {r['floor']} | {mean} | {worst} | {len(r['questions'])} |")
    (RUNS_DIR / "README.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--floor", required=True, help="e.g. ground or first (prefix used in truth.json)")
    ap.add_argument("--truth", help="truth.json to score against")
    ap.add_argument("--case", help="case id for the run log (default: the image's folder name)")
    ap.add_argument("--note", default="", help="commentary saved in the run report")
    args = ap.parse_args()
    data = extract_walls(args.image, args.floor)
    runs, questions = to_runs(data)
    pred = {f"{args.floor}_{k}": v for k, v in girth(runs).items()}
    print(json.dumps({"extraction": data, "girth": pred, "questions": questions}, indent=2))
    errors = None
    if args.truth:
        from eval.run import score_case

        truth = {k: v for k, v in json.loads(Path(args.truth).read_text()).items() if k.startswith(args.floor)}
        errors = score_case(pred, truth)
        print("pct error vs truth:", errors)
    out = save_run(case=args.case or Path(args.image).resolve().parent.name, floor=args.floor, model=model_name(),
                   data=data, pred=pred, errors=errors, questions=questions, note=args.note)
    print("saved", out)


if __name__ == "__main__":
    main()
