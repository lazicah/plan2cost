"""The estimate: what the floors measured, plus the quantities the plans cannot give, from coefficients as low, typical and high. Every number comes from code."""
from plan2cost.kit.progress import ROOF_TYPES, Run
from plan2cost.takeoff.boq import load_rates, price_boq
from plan2cost.takeoff.checklist import coverage, statement
from plan2cost.takeoff.materials import bill_of_materials
from plan2cost.takeoff.rough import FloorData, estimate
from plan2cost.takeoff.sections import structure
from plan2cost.takeoff.walls import Opening
from plan2cost.tools.records import add_fact, settle


def _floor(d: dict) -> FloorData:
    ops = [Opening(o["label"], o["width_m"], o["height_m"], o["count"], o["kind"], o["external"], o.get("assumed_height", False)) for o in d.get("openings", [])]
    return FloorData(d["name"], d["ext_m"], d["int_m"], d["junctions"], d["length_m"], d["width_m"], d["wall_plan_area_m2"], ops, d.get("rooms", []), d.get("void_m2", 0.0), d.get("tagged", False), d.get("unplaced") or {})


def compute_boq(run: Run) -> dict:
    """The priced estimate. Needs every floor read (read_floor, or assume_floor_like_ground) and the storey height and roof type the user entered. Lines are marked measured
    (from the plans) or estimated (from coefficients, with a low to high range). Report the range and which part is estimated; never present the typical value as exact."""
    inputs = run.inputs
    problems = []
    if not inputs.get("storey_height_m") or not 2.0 <= float(inputs["storey_height_m"]) <= 6.0:
        problems.append("The storey height (floor to floor, in metres) is missing or implausible.")
    if inputs.get("roof_type") not in ROOF_TYPES:
        problems.append(f"The roof type must be one of {ROOF_TYPES}.")
    unread = [f["name"] for f in run.floors if f["name"] not in (run.data.get("floors") or {})]
    if unread:
        problems.append(f"Floors not read yet: {unread}. Call read_floor for each, or assume_floor_like_ground.")
    if problems:
        return {"error": " ".join(problems)}
    floors = [_floor(run.data["floors"][f["name"]]) for f in run.floors]
    bad = [f.name for f in floors if f.ext_m <= 0 or f.int_m < 0]
    if bad:
        return {"error": f"Implausible walls on {bad}. Re-read the plan or ask the user for a clearer one."}
    rates = load_rates(inputs.get("finish_level"))
    items, assumptions, working = estimate(floors, inputs, rates["rates"])
    for a in assumptions:
        if not any(x["name"] == a["name"] for x in run.assumptions):
            run.assumptions.append(a)
    priced = price_boq(items, rates)
    run.data["boq"] = {"items": [i.__dict__ for i in items], **priced, "working": working, "inputs": inputs, "rates": {"label": rates["label"], "tier": rates["tier"], "tier_notes": rates["tier_notes"]}, "structure": structure()}
    run.data["materials"] = bill_of_materials(run.data["boq"]["items"])
    for name, v, u in (("storey_height_m", inputs["storey_height_m"], "m"), ("roof_type", inputs["roof_type"], "")):
        add_fact(run, name, v, u, "user", "entered by the user")
    settle(run, run.checklist[-1]["id"])
    cov = coverage([i.key for i in items], floors=len(floors))
    out = {"lines": len(items), "total": priced["total"], "total_range": [priced["total_low"], priced["total_high"]], "currency": priced["currency"],
           "estimated_share": priced["estimated_share"], "materials_and_labour": run.data["materials"]["total"], "gross_floor_area_m2": working["gross_floor_area_m2"], "unpriced": priced["unpriced"]}
    if cov:
        run.data["boq"]["coverage"] = {k: v for k, v in cov.items() if k != "items"} | {"statement": statement(cov), "items": cov["items"]}
        out["coverage"] = statement(cov)
    return out


TOOLS = {
    "compute_boq": (compute_boq, "no args: the priced estimate from the floors read and the storey height and roof type entered (after every floor is read)"),
}
