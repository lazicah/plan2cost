"""Tools that turn recorded facts into quantities and a priced BoQ. Every number comes from deterministic code in takeoff/."""
import json
from pathlib import Path

from plan2cost.kit.progress import Run
from plan2cost.takeoff.boq import BoqItem, foundation_boq, foundation_extras, price_boq, strip_inputs, substructure_extras, superstructure_boq
from plan2cost.drawing.roof import Roof
from plan2cost.facts.roof_spec import RoofSpec
from plan2cost.facts.rooms import Room
from plan2cost.takeoff.roof import roof_boq
from plan2cost.takeoff.checklist import coverage, statement
from plan2cost.takeoff.finishes import finishes_boq, floor_finishes, lintel_items
from plan2cost.takeoff.foundation import GridLine, PadBase, foundation_takeoff
from plan2cost.takeoff.walls import Opening


def compute_foundation(run: Run, block_mm: int = 230) -> dict:
    """Strip foundation from the ground floor walls when no foundation layout is given: trench girth is the ground floor wall girth less
    the overlaps at joints, trench width is three times the block thickness, depths are flagged defaults. Needs the facts
    ext_girth_ground_m and int_girth_ground_m (and, if known, junction_ends_ground, building_length_m, building_width_m; with the lengths it also
    computes the ground bed, topsoil, blinding, formwork, disposal and backfill). Items are added to the BoQ by compute_boq."""

    facts = {f["name"]: f["value"] for f in run.facts}
    layout = run.data.get("strip_layout")
    if layout:  # the drawn strip layout beats the ground floor stand-in: blockwork runs the full length, the trench is net of the bases
        total, overlaps = float(layout["gross_m"]), float(layout["gross_m"]) - float(layout["net_m"])
    elif "ext_girth_ground_m" not in facts or "int_girth_ground_m" not in facts:
        return {"error": "Record ext_girth_ground_m and int_girth_ground_m first (read_wall_girth on the ground floor plan), or read the strip layout (read_strip_layout)."}
    else:
        total = float(facts["ext_girth_ground_m"]) + float(facts["int_girth_ground_m"])
        overlaps = float(facts.get("junction_ends_ground", 0)) * block_mm / 1000
    drawn = {"block_mm": block_mm}
    if "fdn_footing_width_mm" in facts:
        drawn["width_mm"] = float(facts["fdn_footing_width_mm"])
    if "fdn_footing_thickness_mm" in facts:
        drawn["footing_thickness_m"] = float(facts["fdn_footing_thickness_mm"]) / 1000
    if "fdn_overall_depth_mm" in facts:  # the printed overall depth is measured from the stripped level; topsoil is added back for the dig from ground level
        drawn["trench_depth_m"] = float(facts["fdn_overall_depth_mm"]) / 1000 + 0.15
    section, log, grade = strip_inputs(drawn=drawn)
    for a in log:
        if a.source == "assumed":
            run.assumptions.append({"name": f"foundation_{a.name}", "value": a.value, "basis": a.basis})
    pads = [PadBase(**d) for d in run.data.get("pads", [])]
    t = foundation_takeoff([GridLine("ground floor walls", runs=[(total, 1)], deductions=[(overlaps, 1)] if overlaps else [])], pads, section)
    items = foundation_boq(t, section, grade)
    length, width = facts.get("building_length_m"), facts.get("building_width_m")
    if length and width:  # the author's slab area is the overall length x width; fills are that less the wall footprint
        slab = float(length) * float(width)
        items += foundation_extras(pads, grade, slab_area_m2=slab, fill_area_m2=slab - total * block_mm / 1000)
        extras = {i.key: i.qty for i in items}
        items += substructure_extras(t, section, pads, total - overlaps, float(length), float(width), extras)
    run.data["foundation_items"] = [i.__dict__ for i in items]
    return {"trench_girth_m": round(total - overlaps, 2), "trench_width_mm": section.width_mm, "lines": [f"{i.key} {i.qty} {i.unit}" for i in items],
            "assumed": [f"{a.name}={a.value}" for a in log if a.source == "assumed"]}


def merge_located_openings(schedule: list[dict], located: dict) -> list:
    """The openings the BoQ deducts. For each schedule type, the ones found on the plans count on the side of the wall they sit in; whatever the
    schedule has beyond that stays as scheduled, on the old rule (windows external, doors by material), so nothing is counted twice or dropped."""
    found: dict = {}
    for floor_counts in located.values():
        for mark, c in floor_counts.items():
            f = found.setdefault(mark, {"external": 0, "internal": 0})
            f["external"] += c["external"]
            f["internal"] += c["internal"]
    out = []
    for o in schedule:
        o = dict(o)
        f = found.get(o["label"].upper(), {"external": 0, "internal": 0})
        ext_n, int_n = min(f["external"], o["count"]), min(f["internal"], max(o["count"] - f["external"], 0))
        rest = o["count"] - ext_n - int_n
        for n, external in ((ext_n, True), (int_n, False)):
            if n:
                out.append(Opening(o["label"], o["width_m"], o["height_m"], n, o["kind"], external))
        if rest:
            out.append(Opening(o["label"], o["width_m"], o["height_m"], rest, o["kind"], o["external"]))
    return out


def floor_openings(run: Run, floor: str) -> list[Opening]:
    """The doors and windows located on one floor's plan, sized from the schedule, each on the side of the wall it is in."""
    located = (run.data.get("located_openings") or {}).get(floor, {})
    out = []
    for o in run.data.get("openings", []):
        c = located.get(o["label"].upper(), {"external": 0, "internal": 0})
        for n, external in ((c["external"], True), (c["internal"], False)):
            if n:
                out.append(Opening(o["label"], o["width_m"], o["height_m"], n, o["kind"], external))
    return out


def compute_boq(run: Run) -> dict:
    """Wall blockwork and priced BoQ lines from recorded facts: girth per floor (facts named ext_girth_<floor>_m and
    int_girth_<floor>_m), storey heights and the openings read from the drawings."""

    ext = {f["name"][len("ext_girth_"):-2]: float(f["value"]) for f in run.facts if f["name"].startswith("ext_girth_") and f["name"].endswith("_m")}
    internal = {f["name"][len("int_girth_"):-2]: float(f["value"]) for f in run.facts if f["name"].startswith("int_girth_") and f["name"].endswith("_m")}
    if not ext or not internal:
        return {"error": "Record the external and internal girth per floor first, as facts named ext_girth_<floor>_m and int_girth_<floor>_m."}
    problems = [f"{f}: internal girth is {g} m, which is not plausible for a floor with rooms" for f, g in internal.items() if g <= 0]
    problems += [f"{f}: external girth is {g} m, which is not plausible" for f, g in ext.items() if g <= 0]
    if len(ext) > 1:
        top, low = max(ext.values()), min(ext.values())
        if low < 0.6 * top:
            problems.append(f"External girth differs too much between floors ({ext}); upper floors are normally close to the ground floor.")
    if problems:
        return {"error": "Implausible girth. Re-read the plan, or use assume_floor_like_ground for an upper floor. Do not ask the user about girth.", "problems": problems}
    heights = dict(run.data.get("heights") or {})
    for f in run.facts:
        if f["name"].startswith("storey_height_") and f["name"].endswith("_m"):
            heights.setdefault(f["name"][len("storey_height_"):-2], float(f["value"]))
    missing = [f for f in ext if f not in heights]
    if missing:
        return {"error": f"No storey height for {missing}. Read the levels, record an assumed height, or ask the user."}
    openings = merge_located_openings(run.data.get("openings", []), run.data.get("located_openings", {}))
    items = superstructure_boq(ext, internal, heights, openings)
    facts = {f["name"]: f["value"] for f in run.facts}
    questions: list[str] = []
    rooms_by_floor = run.data.get("rooms", {})
    if rooms_by_floor:
        include_open = str(facts.get("include_open_spaces", "")).lower() in ("yes", "true", "1")
        floors = {f: floor_finishes(f, [Room(**{k: v for k, v in r.items() if k not in ("area_m2", "perimeter_m")}) for r in rs], heights.get(f, 3.0),
                                    floor_openings(run, f), include_open) for f, rs in rooms_by_floor.items()}
        for f in floors:
            if f not in run.data.get("located_openings", {}):
                run.assumptions.append({"name": f"finishes_{f}_openings", "value": "not deducted", "basis": f"the openings of the {f} floor are not located, so none were taken off its wall finishes"})
        fin, ask = finishes_boq(floors, facts)
        items += fin
        questions += ask
        if floors and any(fl.open_spaces for fl in floors.values()) and "include_open_spaces" not in facts:
            questions.append(f"Do the {', '.join(sorted({n for fl in floors.values() for n in fl.open_spaces}))} count for floor finishes, and what is their finish?")
    if run.data.get("roof"):
        r = run.data["roof"]
        top = next((f for f in ("fourth", "third", "second", "first", "ground") if f in ext), None)
        spec = RoofSpec(**r["spec"]) if r.get("spec") else None
        rf = Roof(**{**r["roof"], "lines": [tuple(x) for x in r["roof"]["lines"]]})
        roof_items, ask, working = roof_boq(rf, spec, facts, ext.get(top))
        items += roof_items
        questions += ask
        run.data["roof"]["working"] = working
    lint, ask = lintel_items(openings, float(facts["lintel_bearing_mm"]) if facts.get("lintel_bearing_mm") else None)
    items += lint
    questions += ask
    items += [BoqItem(**d) for d in run.data.get("foundation_items", [])]
    rates = json.loads(Path("data/rates.json").read_text())
    priced = price_boq(items, rates)
    run.data["boq"] = {"items": [i.__dict__ for i in items], **priced}
    cov = coverage([i.key for i in items], floors=len(ext))
    out = {"lines": len(items), "total": priced["total"], "currency": priced["currency"], "unpriced": priced["unpriced"]}
    if questions:  # one plain question each; the answers are recorded as facts (names in the prompt) and compute_boq is run again
        out["to_confirm_with_user"] = questions
    if cov:
        run.data["boq"]["coverage"] = {k: v for k, v in cov.items() if k != "items"} | {"statement": statement(cov), "items": cov["items"]}
        out["coverage"] = statement(cov)
    return out


TOOLS = {
    "compute_foundation": (compute_foundation, "block_mm: int (default 230): strip foundation from the ground floor walls; run after the ground girth is recorded, before compute_boq"),
    "compute_boq": (compute_boq, "no args: wall areas and priced lines from the recorded facts"),
}
