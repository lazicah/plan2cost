"""Wall girth from the raster ground-floor exports (reference/planN/ground-floor.jpg) against the author's totals.
Model-read page facts are cached in eval/cases/planN/page_facts.json so the geometry can be iterated without model calls."""
import json
import os
import sys

from plan2cost.interpret import interpret_image
from plan2cost.page_facts import read_page_facts

if __name__ == "__main__":
    plans = [int(a) for a in sys.argv[1:] if a.isdigit()] or [1, 2, 3, 4, 5, 6]
    floor = "first" if "first" in sys.argv else "ground"
    for n in plans:
        key = "first_floor" if floor == "first" else "ground_floor"
        t = json.load(open(f"eval/cases/plan{n}/girth_truth.json"))["floors"].get(key, {})
        path = f"reference/plan{n}/{'first' if floor == 'first' else 'ground'}-floor.jpg"
        if not os.path.exists(path):
            continue
        fp = f"eval/cases/plan{n}/page_facts{'_first' if floor == 'first' else ''}.json"
        if not os.path.exists(fp):
            json.dump(read_page_facts(path), open(fp, "w"))
        facts = json.load(open(fp)) if os.path.exists(fp) else read_page_facts(path)
        r = interpret_image(path, facts)
        if "error" in r:
            print(f"plan{n} ERROR {r['error']}", r.get("tried"))
            continue
        pct = lambda a, b: f"{(a - b) / b * 100:+.0f}%" if b else "n/a"
        print(f"plan{n} {floor:6} total {r['total_m']:7.1f} vs {t.get('overall_m', 0):7.1f} {pct(r['total_m'], t.get('overall_m', 0)):>5} | external {r['external_m']:6.1f} vs {t.get('external_m', 0):6.1f} {pct(r['external_m'], t.get('external_m', 0)):>5} | {r['length_m']}x{r['width_m']} | {r['scale'][:58]}", flush=True)
        for line in r["tried"]:
            print("      ", line)
