"""Wall girth by the vector route on every plan page with a truth in eval/cases/planN/girth_truth.json. Prints measured against surveyed."""
import json
import sys

from plan2cost.measure import measure_walls_vector

CASES = [("plan4 ground", "reference/plan4/4 BED DUPLEX WITH CIN.pdf", 4, 4, "ground_floor"), ("plan4 first", "reference/plan4/4 BED DUPLEX WITH CIN.pdf", 5, 4, "first_floor"),
         ("plan4 pent", "reference/plan4/4 BED DUPLEX WITH CIN.pdf", 6, 4, "second_floor"),
         ("plan6 ground", "reference/plan6/Detached and Semi Detached WD (1).pdf", 6, 6, "ground_floor"), ("plan6 first", "reference/plan6/Detached and Semi Detached WD (1).pdf", 7, 6, "first_floor"),
         ("plan7 ground", "reference/plan7/3 plus 1 bedroom WD (1).pdf", 2, 7, "ground_floor"),
         ("plan5 ground", "reference/plan5/ARCHITECTURAL DRAWINGS FOR MR FREDRICK NWANSO.pdf", 3, 5, "ground_floor")]

if __name__ == "__main__":
    only = sys.argv[1:]
    for name, pdf, page, plan, floor in CASES:
        if only and not any(o in name for o in only):
            continue
        t = json.load(open(f"eval/cases/plan{plan}/girth_truth.json"))["floors"].get(floor, {})
        r = measure_walls_vector(pdf, page)
        if "error" in r:
            print(f"{name:14} ERROR {r['error']}")
            continue
        pct = lambda a, b: f"{(a - b) / b * 100:+.0f}%" if b else "n/a"
        print(f"{name:14} total {r['total_m']:7.1f} vs {t.get('overall_m', 0):7.1f} {pct(r['total_m'], t.get('overall_m', 0)):>5} | external {r['external_m']:6.1f} vs {t.get('external_m', 0):6.1f} {pct(r['external_m'], t.get('external_m', 0)):>5} | weight {r['wall_weight_pt']} | {r['scale'][:44]}", flush=True)
