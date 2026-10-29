"""Wall girth truth from the author's workbooks (private, in reference/): the 'Block work Girth' summary blocks, per floor and block size.
Writes eval/cases/planN/girth_truth.json (numbers only). External = EXTERNAL GIRTH summary; overall = OVERALL summary; internal = overall - external."""
import json
import sys
from pathlib import Path

import openpyxl

FLOORS = ["FOUNDATION", "GROUND FLOOR", "FIRST FLOOR", "SECOND FLOOR", "THIRD FLOOR"]


def read(plan: int) -> dict:
    wb = openpyxl.load_workbook(f"reference/plan{plan}/General works.xlsx", data_only=True, read_only=True)
    rows = list(wb["Block work Girth"].iter_rows(values_only=True))
    blocks, current = {}, None
    for r in rows:
        label = str(r[10]).strip().upper() if len(r) > 10 and r[10] else ""
        if label.startswith("EXTERNAL GIRTH") and r[13] == 225 or label == "EXTERNAL GIRTH" and isinstance(r[13], (int, float)) and r[13] == 225:
            current = "external"
        elif label == "OVERALL":
            current = "overall"
        elif current and any(label.startswith(f) for f in FLOORS):
            floor = next(f for f in FLOORS if label.startswith(f)).lower().replace(" ", "_")
            blocks.setdefault(current, {})[floor] = {"225": r[13] or 0, "150": r[14] or 0, "100": r[15] or 0}
    out = {}
    for floor, ov in blocks.get("overall", {}).items():
        ext = blocks.get("external", {}).get(floor, {})
        total = round(sum(float(v) for v in ov.values()), 3)
        e = round(sum(float(v) for v in ext.values()), 3)
        if total or e:
            out[floor] = {"overall_m": total, "external_m": e, "internal_m": round(total - e, 3), "by_block_mm": {k: float(v) for k, v in ov.items() if float(v)}}
    return out


if __name__ == "__main__":
    for plan in map(int, sys.argv[1:] or range(1, 10)):
        try:
            data = read(plan)
        except Exception as e:  # a plan folder without the workbook
            print(plan, "skipped:", e)
            continue
        d = Path(f"eval/cases/plan{plan}")
        d.mkdir(parents=True, exist_ok=True)
        (d / "girth_truth.json").write_text(json.dumps({"_note": "from the author's workbook, Block work Girth summary (numbers only)", "floors": data}, indent=1))
        print(plan, {f: (v["overall_m"], v["external_m"]) for f, v in data.items()})
