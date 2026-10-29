"""External girth against the author's totals for several closing radii (how large an opening still counts as part of the building)."""
import json
import os
import pickle

import cv2

from eval.run_vector_walls import CASES
from plan2cost.drawing.interpret import interpret_image
from plan2cost.drawing.measure import vector_scale
from plan2cost.drawing.vector import read_page
from plan2cost.drawing.vector_walls import axis_lines, find_walls_vector
from plan2cost.drawing.walls_cv import external_fractions

CACHE = "/tmp/ext_cases.pkl"


def cases():
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, "rb"))
    out = []
    for name, pdf, page, plan, floor in CASES:
        if plan == 5:
            continue
        t = json.load(open(f"eval/cases/plan{plan}/girth_truth.json"))["floors"].get(floor, {})
        pg = read_page(pdf, page)
        lines = axis_lines(pg.segs)
        mm, _ = vector_scale(pdf, page, pg, lines)
        walls, _ = find_walls_vector(lines, mm)
        out.append((f"vec {name}", walls, (int(pg.height * mm / 50) + 2, int(pg.width * mm / 50) + 2), t.get("external_m", 0), t.get("overall_m", 0)))
    for n in (1, 2, 3, 4, 6):
        t = json.load(open(f"eval/cases/plan{n}/girth_truth.json"))["floors"]["ground_floor"]
        facts = json.load(open(f"eval/cases/plan{n}/page_facts.json"))
        r = interpret_image(f"reference/plan{n}/ground-floor.jpg", facts, keep_walls=True)
        h, w = cv2.imread(f"reference/plan{n}/ground-floor.jpg", 0).shape
        s = r["mm_per_px"]
        out.append((f"img plan{n}", r["_walls"], (int(h * s / 50) + 2, int(w * s / 50) + 2), t["external_m"], t["overall_m"]))
    pickle.dump(out, open(CACHE, "wb"))
    return out


if __name__ == "__main__":
    data = cases()
    for close in (2500, 4000, 6000, 8000, 12000):
        errs = []
        row = []
        for name, walls, shape, ext_truth, _ in data:
            fr = external_fractions(walls, shape, 50.0, close_mm=close)
            ext = sum(w.length_mm * f for w, f in zip(walls, fr)) / 1000
            e = (ext - ext_truth) / ext_truth * 100
            errs.append(abs(e))
            row.append(f"{e:+.0f}")
        print(f"close {close:6}: mean abs err {sum(errs) / len(errs):5.1f}%  | {' '.join(row)}", flush=True)
    print([d[0] for d in data])
