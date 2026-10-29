"""Openings located on a plan page against the author's counts. python -m eval.run_openings  (plan 6: windows per floor are known, doors only in total)."""
import collections
import json
import sys

from plan2cost.drawing.markup import model_for_page, plan_image, draw_markup
from plan2cost.drawing.openings import locate_openings

PDF = "reference/plan6/Detached and Semi Detached WD (1).pdf"

if __name__ == "__main__":
    floor, page = ("first", 7) if "first" in sys.argv else ("ground", 6)
    truth = json.load(open("eval/cases/plan6/windows_by_floor_truth.json"))[floor]
    sched = [{"label": k, "width_m": v["width_mm"] / 1000, "height_m": v["height_mm"] / 1000, "count": v["quantity"], "kind": "window" if k.startswith("AW") else "door"}
             for k, v in json.load(open("eval/cases/plan6/openings_truth.json")).items() if not k.startswith("_")]
    out = f"/tmp/open_{floor}"
    m = model_for_page(PDF, page, floor, out)
    img, scale = plan_image(m, PDF, page, None, 200)
    cands = len([1 for e in m.walls() for g in e.gaps_mm])
    issues = locate_openings(m, img, scale, PDF, page, sched)
    kinds = collections.Counter(o.category for o in m.openings())
    wins = collections.Counter(round(o.width_mm / 300) * 300 for o in m.openings() if o.category == "window")
    marks = collections.Counter((o.category, o.mark or "-") for o in m.openings())
    print(f"{floor}: gaps {cands}, kinds {dict(kinds)}; windows by width {dict(wins)}; truth windows {truth} (total {sum(truth.values())})")
    print("marks:", dict(marks))
    for i in issues:
        print("  ", i.severity, i.code, i.message[:120])
    draw_markup(m, f"{out}/markup_openings.jpg", pdf=PDF, page=page)
    m.save(f"{out}/model.json")
