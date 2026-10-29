"""The bill of materials and labour: each BoQ line turned into the materials (cement, sand, granite, bars, planks, blocks, tiles...) and the labour that make it, in the way of the
author's SIMPLIFIED BOQ. The recipes are data/materials_labour.json: material per unit of measured work, derived from two bills of one duplex (eval/derive_materials.py), with
unit rates for materials and labour. A line with no recipe (windows, doors, fittings, excavation) is carried at its BoQ rate. Quantities of estimated lines keep their low to high range."""
import json
import math
from functools import lru_cache
from pathlib import Path

from plan2cost.takeoff.sections import bill_name, bill_of, group_of

# BoQ line key -> (recipe family in the ratios, name of the element it makes). Families: concrete (per m3), blinding (per m3), steel_per_t, formwork_per_m2, block_per_m2 (1:4 mortar), block_int_per_m2 (1:6),
# plaster_per_m2, paint_per_m2, floor_tiling_per_m2, skirting_per_m, ceiling_per_m2, roof_cover_per_m2, roof_timber_per_m, earthwork_support_per_m2.
RECIPES = {
    "strip_footing_concrete_m3": ("concrete", "Foundation footing concrete (1:2:4)"), "column_base_concrete_m3": ("concrete", "Column bases concrete"),
    "ground_slab_m3": ("concrete", "Ground floor slab concrete"), "concrete_filling_blockwork_voids_m3": ("concrete", "Concrete filling the voids of foundation blocks"),
    "frame_columns_concrete_m3": ("concrete", "Columns concrete"), "frame_beams_concrete_m3": ("concrete", "Beams concrete"), "suspended_slab_concrete_m3": ("concrete", "Suspended slab concrete"),
    "staircase_concrete_m3": ("concrete", "Staircase concrete"), "roof_slab_concrete_m3": ("concrete", "Roof slab concrete"),
    "blinding_foundations_m3": ("blinding_per_m3", "Blinding"), "blinding_on_hardcore_m3": ("blinding_per_m3", "Blinding under the ground floor slab"),
    "frame_steel_t": ("steel_per_t", "Reinforcement (columns, beams, slabs and stairs)"), "rebar_y12_foundations_t": ("steel_per_t", "Reinforcement (foundation)"),
    "rebar_y8_foundations_t": ("steel_per_t", "Reinforcement (foundation links)"),
    "frame_formwork_soffit_m2": ("formwork_per_m2", "Formwork to soffits of slabs"), "frame_formwork_beams_columns_m2": ("formwork_per_m2", "Formwork to beams and columns"),
    "fdn_blockwork_230_m2": ("block_per_m2", "Blockwork in foundation"), "ext_blockwork_230_m2": ("block_per_m2", "Blockwork in external walls"), "int_blockwork_230_m2": ("block_int_per_m2", "Blockwork in internal walls"),
    "external_wall_render_m2": ("plaster_per_m2", "Rendering to external walls"), "fdn_wall_render_m2": ("plaster_per_m2", "Rendering to foundation walls"), "internal_wall_finish_m2": ("plaster_per_m2", "Plastering to internal walls"),
    "external_wall_paint_m2": ("paint_per_m2", "Painting to external walls"), "internal_wall_paint_m2": ("paint_per_m2", "Painting to internal walls"),
    "floor_finish_m2": ("floor_tiling_per_m2", "Floor tiling and screed"), "skirting_m": ("skirting_per_m", "Skirting tiles"), "ceiling_finish_m2": ("ceiling_per_m2", "Ceiling work"),
    "roof_covering_m2": ("roof_cover_per_m2", "Roof covering"), "roof_timbers_m": ("roof_timber_per_m", "Roof carcassing (hardwood)"), "earthwork_support_m2": ("earthwork_support_per_m2", "Earthwork support"),
}
# what the labour of each family is paid by, and how it scales: (labour rate key, quantity it is paid on per unit of the BoQ line)
LABOUR = {"concrete": [("casting_per_bag", "cement_bag")], "blinding_per_m3": [("casting_per_bag", "cement_bag")], "steel_per_t": [("iron_bending_per_kg", 1000.0)], "formwork_per_m2": [("carpenter_per_m2", 1.0)],
          "block_per_m2": [("block_laying_per_block", "block_225")], "block_int_per_m2": [("block_laying_per_block", "block_225")], "plaster_per_m2": [("plaster_per_m2", 1.0)], "paint_per_m2": [("painting_per_m2", 1.0), ("screeding_for_paint_per_m2", 1.0)],
          "floor_tiling_per_m2": [("floor_tiling_per_m2", 1.0)], "ceiling_per_m2": [("ceiling_per_m2", 1.0)], "roof_cover_per_m2": [("roof_covering_per_m2", 1.0)],
          "roof_timber_per_m": [("carcassing_per_m", 1.0)], "earthwork_support_per_m2": [("earthwork_support_per_m2", 1.0)]}


@lru_cache(maxsize=1)
def table() -> dict:
    return json.loads(Path("data/materials_labour.json").read_text())


def _ceil(x: float) -> int:
    return max(1, math.ceil(round(x, 6))) if x > 0 else 0


def _line(no: str, name: str, unit: str, q: tuple[float, float, float], rate: float, basis: str) -> dict:
    qty = tuple(_ceil(x) for x in q)
    return {"no": no, "description": name, "unit": unit, "qty": qty[1], "qty_low": qty[0], "qty_high": qty[2], "rate": rate, "amount": round(qty[1] * rate, 2),
            "amount_low": round(qty[0] * rate, 2), "amount_high": round(qty[2] * rate, 2), "basis": basis}


def recipe_lines(item: dict, element: str, family: str, key: str = "") -> list[dict]:
    """The material and labour lines of one BoQ line, at its typical quantity and at the low and high ends."""
    t = table()
    ratios, mats, labs = t["ratios"][family], t["materials"], t["labour"]
    q = (item.get("qty_low") if item.get("qty_low") is not None else item["qty"], item["qty"], item.get("qty_high") if item.get("qty_high") is not None else item["qty"])
    short = element.split(" (")[0]
    out = []
    for m, per in ratios.items():
        out.append(_line("", f"{mats[m]['name']} – {short}", mats[m]["unit"], tuple(x * per for x in q), mats[m]["rate"], item.get("basis", "measured")))
    for lab, on in LABOUR.get(family, []):
        per_unit = ratios[on] if isinstance(on, str) else on
        out.append(_line("", f"Labour – {labs[lab]['name'].lower()} – {short}", labs[lab]["unit"], tuple(x * per_unit for x in q), labs[lab]["rate"], item.get("basis", "measured")))
    return out


def bill_of_materials(items: list[dict]) -> dict:
    """Sections (the bills of the BoQ, in order), each with element sub-sections of material and labour lines, and the lines carried at their BoQ rate. Totals have a low to high range."""
    by_bill: dict[int, dict] = {}
    for it in items:
        b = it.get("bill") or bill_of(it["key"])
        sec = by_bill.setdefault(b, {"bill": b, "name": bill_name(b), "group": group_of(b), "subs": [], "carried": []})
        if it["key"] in RECIPES and it["qty"]:
            family, element = RECIPES[it["key"]]
            sec["subs"].append({"name": element, "lines": recipe_lines(it, element, family, it["key"]), "key": it["key"]})
        elif it.get("rate") and it["qty"]:
            lo = it.get("qty_low") if it.get("qty_low") is not None else it["qty"]
            hi = it.get("qty_high") if it.get("qty_high") is not None else it["qty"]
            sec["carried"].append({"no": "", "description": it["description"], "unit": it["unit"], "qty": it["qty"], "qty_low": lo, "qty_high": hi, "rate": it["rate"], "amount": round(it["qty"] * it["rate"], 2),
                                   "amount_low": round(lo * it["rate"], 2), "amount_high": round(hi * it["rate"], 2), "basis": it.get("basis", "measured")})
    sections = [by_bill[b] for b in sorted(by_bill)]
    total = lambda k: round(sum(sum(ln[k] for ln in s["lines"]) for sec in sections for s in sec["subs"]) + sum(c[k] for sec in sections for c in sec["carried"]), 2)  # noqa: E731
    for n, sec in enumerate(sections, 1):
        for i, s in enumerate(sec["subs"], 1):
            for j, ln in enumerate(s["lines"], 1):
                ln["no"] = f"{n}.{i}.{j}"
        for j, c in enumerate(sec["carried"], 1):
            c["no"] = f"{n}.C{j}"
        for s in sec["subs"]:
            s.update({k: round(sum(ln[k] for ln in s["lines"]), 2) for k in ("amount", "amount_low", "amount_high")})
        sec.update({k: round(sum(s[k] for s in sec["subs"]) + sum(c[k] for c in sec["carried"]), 2) for k in ("amount", "amount_low", "amount_high")})
    return {"sections": sections, "total": total("amount"), "total_low": total("amount_low"), "total_high": total("amount_high"), "source": table()["sources"]["simplified"]}
