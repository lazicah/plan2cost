"""Raster plan: geometry, then the model judges every wall found; compare both with the author's total. python -m eval.run_raster_judged 1 2 ..."""
import json
import os
import sys

import cv2

from plan2cost.interpret import interpret_image
from plan2cost.walls_cv import external_fractions
from plan2cost.wall_judge import judge_image_walls

if __name__ == "__main__":
    for n in [int(a) for a in sys.argv[1:]]:
        t = json.load(open(f"eval/cases/plan{n}/girth_truth.json"))["floors"].get("ground_floor", {})
        path = f"reference/plan{n}/ground-floor.jpg"
        facts = json.load(open(f"eval/cases/plan{n}/page_facts.json"))
        r = interpret_image(path, facts, keep_walls=True)
        if "error" in r:
            print(n, r["error"])
            continue
        img = cv2.imread(path)
        v = judge_image_walls(img, r["_walls"], r["mm_per_px"])
        kept = [w for i, w in enumerate(r["_walls"]) if i in v["keep"]]
        tot = sum(w.length_mm for w in kept) / 1000
        truth = t.get("overall_m", 0)
        print(f"plan{n} geometry {r['total_m']:.1f} judged {tot:.1f} (kept {len(kept)}/{len(r['_walls'])}, unsure {len(v['unsure'])}) truth {truth:.1f} -> geometry {(r['total_m'] - truth) / truth * 100:+.0f}% judged {(tot - truth) / truth * 100:+.0f}%", flush=True)
