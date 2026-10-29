"""Ratios from the author's own BOQs sheets (reference/plan1..9/General works.xlsx), written into data/coefficients.json. Only numbers leave the workbooks.

The workbooks are templates reused from job to job, so a value can be stale. Each ratio therefore uses only plans that pass a screen, and the entry keeps the per-plan
values so the spread is visible: a ground area shared by several plans is a template default and is dropped; a trim ratio that is 20 times the others is dropped.
Run:  python -m eval.derive_coefficients
"""
import json
import re
import statistics as st
import warnings
from collections import Counter
from pathlib import Path

import openpyxl

warnings.filterwarnings("ignore")
UNITS = {"m2", "m3", "m", "nr", "kg", "t", "sum", "item", "ps"}
FLOORS = {1: 4, 2: 2, 3: 2, 4: 3, 5: 2, 6: 2, 7: 1, 8: 1, 9: 1}  # ground, first, ... drawings in each plan folder
SOURCE = "authorboq"
PLAN_FILE = "reference/plan{}/General works.xlsx"


def parse(path: str) -> list[dict]:
    """Item rows of the BOQs sheet: description, unit, quantity, amount, and the section heading they sit under."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[next(n for n in wb.sheetnames if n.strip() == "BOQs")]
    section, items = "", []
    for r in ws.iter_rows(values_only=True):
        cells = [c for c in r if c not in (None, "")]
        strs = [c for c in cells if isinstance(c, str)]
        nums = [c for c in cells if isinstance(c, (int, float)) and not isinstance(c, bool)]
        unit = next((s.strip().lower().replace("²", "2").replace("³", "3") for s in strs if s.strip().lower().replace("²", "2").replace("³", "3") in UNITS), None)
        desc = next((s for s in strs if len(s.strip()) > 6 and s.strip().lower() not in UNITS), None)
        if unit and desc and len(nums) >= 2:
            items.append({"section": section, "desc": re.sub(r"\s+", " ", desc.strip()), "unit": unit, "qty": nums[0]})
        elif len(strs) == 1 and not nums and strs[0].strip() == strs[0].strip().upper() and 6 < len(strs[0].strip()) < 80:
            section = strs[0].strip()
    return items


def total(items: list[dict], unit: str, pattern: str, exclude: str = "") -> float:
    return round(sum(x["qty"] for x in items if x["unit"] == unit and x["qty"] and re.search(pattern, x["desc"], re.I) and not (exclude and re.search(exclude, x["desc"], re.I))), 2)


def plan_metrics(i: int) -> dict:
    it = parse(PLAN_FILE.format(i))
    t = lambda unit, pat, ex="": total(it, unit, pat, ex)  # noqa: E731
    cols, beams, slab, stairs, fascia = t("m3", r"^Isolated columns|^Columns", "base"), t("m3", "Beam"), t("m3", r"Suspended (Floor )?Slab"), t("m3", "Staircase"), t("m3", "fascia")
    return {"floors": FLOORS[i], "cols": cols, "beams": beams, "slab": slab, "stairs": stairs, "struct": round(cols + beams + slab + stairs + fascia, 2),
            "steel_kg": t("kg", "nominal size"), "roof_m2": t("m2", "Roof covering"), "ridge": t("m", "^Ridge"), "hip": t("m", "^Hipped"), "valley": t("m", "^Valley"),
            "eaves": t("m", "Eaves"), "rafter": t("m", "rafter"), "purlin": t("m", "purlin", r"50 x 50"),
            "timber": t("m", r"wall plate") + t("m", "tie beam") + t("m", "rafter") + t("m", "kingpost") + t("m", "purlin", r"50 x 50"),
            "A_ground": max(t("m2", "Fabric reference|BRC"), t("m2", "polythene")), "excavation": t("m3", "maximum depth not exceeding 2.00m", "Earthwork"),
            "blinding": t("m3", "Blinding"), "footing": t("m3", "^Foundation") + t("m3", "Column Base"),
            "blocks": round(sum(x["qty"] for x in it if x["unit"] == "m2" and x["qty"] and re.search("hollow blocks", x["desc"], re.I)), 2)}


def entry(id: str, what: str, unit: str, per: str, vals: dict[int, float], note: str, group: str = "from plans") -> dict:
    v = [x for x in vals.values()]
    return {"id": id, "group": group, "what": what, "unit": unit, "per": per, "low": round(min(v), 3), "typical": round(st.median(v), 3), "high": round(max(v), 3), "sources": [SOURCE],
            "confidence": "medium" if len(v) >= 6 else "low", "n_plans": len(v), "per_plan": {f"plan{k}": round(x, 3) for k, x in vals.items()},
            "note": f"{note} From {len(v)} plan(s) of the author's own BOQs sheets; the per-plan values are kept in per_plan."}


def derive() -> list[dict]:
    m = {i: plan_metrics(i) for i in range(1, 10)}
    shared = {a for a, c in Counter(x["A_ground"] for x in m.values()).items() if c > 1}
    area_ok = [i for i, x in m.items() if x["A_ground"] and x["A_ground"] not in shared]  # a ground area several plans share is a template default
    roofed = [i for i, x in m.items() if x["roof_m2"] > 50]
    pick = lambda ids, f: {i: f(m[i]) for i in ids}  # noqa: E731
    out = [
        entry("plans_roof_timber_m_per_m2_roof", "All roof timber (wall plates, tie beams, rafters, king posts and struts, purlins) per m2 of roof covering", "m", "m2 of roof",
              pick([i for i in roofed if m[i]["timber"] > 50], lambda x: x["timber"] / x["roof_m2"]), "The author's roofs are trussed, so this is well above a calculator's 2.8 to 3.5."),
        entry("plans_roof_purlins_m_per_m2_roof", "Purlins per m2 of roof covering", "m", "m2 of roof", pick([i for i in roofed if m[i]["purlin"]], lambda x: x["purlin"] / x["roof_m2"]), "Very steady across plans."),
        entry("plans_roof_rafters_m_per_m2_roof", "Rafters per m2 of roof covering", "m", "m2 of roof", pick([i for i in roofed if m[i]["rafter"]], lambda x: x["rafter"] / x["roof_m2"]), ""),
        entry("plans_roof_ridge_m_per_m2_roof", "Ridge per m2 of roof covering", "m", "m2 of roof", pick(roofed, lambda x: x["ridge"] / x["roof_m2"]), ""),
        entry("plans_roof_valley_m_per_m2_roof", "Valleys per m2 of roof covering", "m", "m2 of roof", pick(roofed, lambda x: x["valley"] / x["roof_m2"]), ""),
        entry("plans_roof_hip_m_per_m2_roof", "Hips per m2 of roof covering", "m", "m2 of roof", pick(roofed, lambda x: x["hip"] / x["roof_m2"]), "Zero for a gable roof, so the range is wide: use the roof type."),
        entry("plans_roof_eaves_m_per_m2_roof", "Eaves per m2 of roof covering", "m", "m2 of roof", pick([i for i in roofed if m[i]["eaves"] / m[i]["roof_m2"] > 0.05], lambda x: x["eaves"] / x["roof_m2"]),
              "One plan with 1 m of eaves for 281 m2 of roof was dropped as a missing entry."),
        entry("plans_roof_area_over_footprint", "Roof covering over the ground floor area", "factor", "m2 of ground floor area", pick([i for i in roofed if i in area_ok and m[i]["floors"] > 1], lambda x: x["roof_m2"] / x["A_ground"]),
              "Two-floor plans only; includes overhang and pitch."),
        entry("plans_structural_concrete_m3_per_m2_floor", "Columns, beams, suspended slab, stairs and fascia per m2 of floor (ground area x floors)", "m3", "m2 of floor",
              pick([i for i in area_ok if m[i]["floors"] > 1], lambda x: x["struct"] / (x["A_ground"] * x["floors"])), "Floor is the ground area times the number of floors, which overstates upper floors that are smaller."),
        entry("plans_steel_kg_per_m2_floor", "Reinforcement in the frame, per m2 of floor (ground area x floors)", "kg", "m2 of floor", pick([i for i in area_ok if m[i]["floors"] > 1 and m[i]["steel_kg"] > 1000], lambda x: x["steel_kg"] / (x["A_ground"] * x["floors"])), ""),
        entry("plans_steel_kg_per_m3_structural_concrete", "Reinforcement per m3 of frame concrete", "kg", "m3 of concrete", pick([i for i in range(1, 10) if m[i]["struct"] > 50 and m[i]["steel_kg"] > 1000], lambda x: x["steel_kg"] / x["struct"]), "Wide spread: the sheets are not consistent about which bars they count."),
        entry("plans_suspended_slab_m3_per_m2_upper_floor", "Suspended slab concrete per m2 of ground area, per upper floor", "m3", "m2 of floor", pick([i for i in area_ok if m[i]["floors"] > 1], lambda x: x["slab"] / (x["A_ground"] * (x["floors"] - 1))), "About a 120 to 150mm slab on the ground area."),
        entry("plans_beams_m3_per_slab_m3", "Beam concrete per m3 of suspended slab", "m3", "m3 of slab", pick([i for i in range(1, 10) if m[i]["slab"] > 5], lambda x: x["beams"] / x["slab"]), ""),
        entry("plans_columns_m3_per_slab_m3", "Column concrete per m3 of suspended slab", "m3", "m3 of slab", pick([i for i in range(1, 10) if m[i]["slab"] > 5], lambda x: x["cols"] / x["slab"]), ""),
        entry("plans_staircase_concrete_m3_per_flight", "Concrete in a staircase (per floor above the ground)", "m3", "storey", pick([i for i in (2, 3, 4) if m[i]["stairs"]], lambda x: x["stairs"] / (x["floors"] - 1)), "Plans 1, 5 and 6 give 7 to 12 and are likely not for this plan."),
        entry("plans_excavation_m3_per_m2_ground", "Excavation (trenches, pits, bed) per m2 of ground floor area", "m3", "m2 of ground floor", pick(area_ok, lambda x: x["excavation"] / x["A_ground"]), ""),
        entry("plans_blinding_m3_per_m2_ground", "Blinding concrete per m2 of ground floor area", "m3", "m2 of ground floor", pick(area_ok, lambda x: x["blinding"] / x["A_ground"]), ""),
        entry("plans_footing_concrete_m3_per_m2_ground", "Foundation and column base concrete per m2 of ground floor area", "m3", "m2 of ground floor", pick(area_ok, lambda x: x["footing"] / x["A_ground"]), "Depends on the soil and the foundation type."),
        entry("plans_hollow_block_wall_m2_per_m2_floor", "Hollow block wall area (all walls) per m2 of floor (ground area x floors)", "m2", "m2 of floor", pick(area_ok, lambda x: x["blocks"] / (x["A_ground"] * x["floors"])), "Block area as the sheets count it, with openings taken off."),
    ]
    return [e for e in out if e["per_plan"]]


def main() -> None:
    p = Path("data/coefficients.json")
    d = json.loads(p.read_text())
    d["sources"][SOURCE] = {"name": "The author's own BOQs sheets for plans 1 to 9 (kept local; ratios only, screened for stale template values)", "url": "", "checked": "parsed; each ratio keeps its per-plan values"}
    d["entries"] = [e for e in d["entries"] if SOURCE not in e["sources"]] + derive()
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print(len(d["entries"]), "entries,", len([e for e in d["entries"] if SOURCE in e["sources"]]), "from the plans")


if __name__ == "__main__":
    main()
