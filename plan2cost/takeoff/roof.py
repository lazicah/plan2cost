"""Roof quantities from the measured plan (drawing/roof.py) and the printed levels and specification (facts/roof_spec.py). Every plane is taken at one pitch,
from the printed rise (apex level less eaves level) over the plan's run from the main ridge to its eave; a plan whose hips are not at 45 degrees is flagged.
BESMM4: coverings on the slope in m2 with the pitch stated (1.17.1.1.2); eaves, ridges and hips as boundary work in m (1.17.1.4.1); valleys in m (1.17.1.7.1);
structural timbers by nominal size in m (1.16.1.1.1). A length of rafter or purlin is the slope area over the spacing: every row across the slope is that long in total."""
import math
from dataclasses import dataclass

from plan2cost.drawing.roof import Roof
from plan2cost.facts.roof_spec import RoofSpec
from plan2cost.takeoff.finishes import whole


@dataclass
class Pitch:
    degrees: float
    rise_mm: float
    run_mm: float
    slope_factor: float  # slope area over plan area
    hip_factor: float  # true length over plan length of a hip or valley at 45 degrees in plan


def pitch_from(rise_mm: float, run_mm: float) -> Pitch | None:
    if not (rise_mm > 0 and run_mm > 0):
        return None
    t = rise_mm / run_mm
    return Pitch(round(math.degrees(math.atan(t)), 1), rise_mm, run_mm, math.sqrt(1 + t * t), math.sqrt(1 + t * t / 2))


def roof_boq(roof: Roof, spec: RoofSpec | None, facts: dict, top_floor_ext_girth_m: float | None) -> tuple[list, list[str], dict]:
    """BoQ lines, the questions a person must answer, and the working that was used (pitch and areas)."""
    from plan2cost.takeoff.boq import BoqItem

    ask: list[str] = []
    lv = (spec.levels if spec else {}) or {}
    p = pitch_from(lv["apex_mm"] - lv["eaves_mm"], roof.half_span_mm) if lv.get("apex_mm") and lv.get("eaves_mm") and roof.half_span_mm else None
    if not p:
        return [], ["The roof pitch could not be read from the drawings (the apex and eaves levels on the section, and the roof plan). What is the pitch of the roof in degrees?"], {}
    if not 10 <= p.degrees <= 55:
        ask.append(f"The roof pitch worked out at {p.degrees:.0f} degrees, which is unusual. Is that right?")
    slope_m2 = roof.plan_area_m2 * p.slope_factor
    hips, valleys, rest = roof.hips_m * p.hip_factor, roof.valleys_m * p.hip_factor, roof.unsorted_m * p.hip_factor
    cover = f"{spec.covering}" if spec and spec.covering else "roof covering to be stated"
    items = [BoqItem("roof_covering_m2", f"Roof coverings; {cover}; sloping, {p.degrees:.0f} degree pitch; over 500mm wide", "m2", whole(slope_m2)),
             BoqItem("roof_eaves_m", "Boundary work; eaves to roof covering", "m", whole(roof.eaves_m)),
             BoqItem("roof_ridge_m", "Boundary work; ridges to roof covering", "m", whole(roof.ridges_m)),
             BoqItem("roof_hips_m", "Boundary work; hips to roof covering", "m", whole(hips)),
             BoqItem("roof_valleys_m", "Valleys to roof covering", "m", whole(valleys)),
             BoqItem("roof_hips_or_valleys_m", "Boundary work; hips or valleys not told apart on the plan, to roof covering", "m", whole(rest))]
    items = [i for i in items if i.qty > 0]
    members = (spec.members if spec else {}) or {}
    for key, label in (("rafters", "Rafters"), ("purlins", "Purlins")):
        m = members.get(key)
        spacing = (m or {}).get("spacing_mm") or (float(facts[f"{key[:-1]}_spacing_mm"]) if facts.get(f"{key[:-1]}_spacing_mm") else None)
        if not m:
            continue
        if not spacing:
            ask.append(f"What is the spacing of the {key} (centre to centre, in mm)? The drawing gives the size ({m['section_mm'][0]} x {m['section_mm'][1]}mm) but not the spacing.")
            continue
        items.append(BoqItem(f"roof_{key}_m", f"Primary or structural timbers; {m['section_mm'][0]} x {m['section_mm'][1]}mm {key} at {int(spacing)}mm centres; sloping", "m", whole(slope_m2 / (spacing / 1000))))
    wp = members.get("wall_plates")
    if wp and top_floor_ext_girth_m:
        items.append(BoqItem("roof_wall_plates_m", f"Primary or structural timbers; {wp['section_mm'][0]} x {wp['section_mm'][1]}mm wall plates; along the top of the external walls", "m", whole(top_floor_ext_girth_m)))
    if members.get("trusses") or members.get("tie_beam"):
        ask.append("How many trusses and tie beams does the roof have? The drawing gives their sizes but not their number, and it cannot be counted from the plan.")
    if spec:
        ask.append(f"The section shows a concrete fascia. Is there also a timber fascia board or a gutter along the {roof.eaves_m:.0f} m of eaves?")
    working = {"pitch_degrees": p.degrees, "rise_mm": p.rise_mm, "run_mm": p.run_mm, "plan_area_m2": roof.plan_area_m2, "slope_area_m2": round(slope_m2, 1), "eaves_m": roof.eaves_m,
               "ridges_m": roof.ridges_m, "hips_m": round(hips, 2), "valleys_m": round(valleys, 2), "unclassified_m": round(rest, 2)}
    return items, ask, working
