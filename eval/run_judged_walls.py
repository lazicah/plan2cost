"""Vector candidates judged by the model, measured by code, against the author's totals. python eval/run_judged_walls.py [name ...]"""
import collections
import sys

from eval.run_vector_walls import CASES
import json

from plan2cost.measure import vector_scale
from plan2cost.vector import read_page
from plan2cost.vector_walls import axis_lines, extend_to_centrelines
from plan2cost.wall_judge import building_candidates, judge_page

if __name__ == "__main__":
    only = sys.argv[1:]
    for name, pdf, page, plan, floor in CASES:
        if only and not any(o in name for o in only):
            continue
        t = json.load(open(f"eval/cases/plan{plan}/girth_truth.json"))["floors"].get(floor, {})
        pg = read_page(pdf, page)
        lines = axis_lines(pg.segs)
        mm, basis = vector_scale(pdf, page, pg, lines)
        cands = building_candidates(lines, mm)
        r = judge_page(pdf, page, cands, mm, f"/tmp/judge_{plan}_{page}")
        walls = extend_to_centrelines([c.wall for c in cands if c.id in r["walls"]])
        tot = sum(w.length_mm for w in walls) / 1000
        by = collections.defaultdict(float)
        for w in walls:
            by[int(w.thickness_mm)] += w.length_mm / 1000
        truth = t.get("overall_m", 0)
        print(f"{name:14} candidates {len(cands):3} tiles {r['tiles']} kept {len(walls):3} total {tot:7.1f} vs {truth:7.1f} {(tot - truth) / truth * 100 if truth else 0:+.0f}% | {({k: round(v) for k, v in by.items()})}", flush=True)
