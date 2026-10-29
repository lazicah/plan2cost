"""The estimate from floor plans alone. What the plans give is measured by code (walls, openings, building size, wet rooms); what they cannot give is estimated from
coefficients (data/coefficients.json), as a low, typical and high quantity. Every line says which: basis "measured" or "estimated", with the coefficient ids behind it.
The user supplies two things the plans do not carry: the storey height (floor to floor) and the roof type, with an optional pitch and overhang."""
import math
from dataclasses import dataclass, field

from plan2cost.takeoff import coefficients as C
from plan2cost.takeoff.boq import (BoqItem, foundation_boq, foundation_extras, strip_inputs, substructure_extras, superstructure_boq)
from plan2cost.takeoff.sections import order
from plan2cost.takeoff.finishes import deductible, lintel_items, whole
from plan2cost.takeoff.foundation import GridLine, foundation_takeoff
from plan2cost.takeoff.walls import Opening

PAD_KEYS = {"pit_excavation_column_bases_m3", "column_base_concrete_m3", "formwork_foundation_sides_m"}
WET = ("bath", "wc", "toilet", "shower", "vis.", "w.c", "powder", "ensuite", "en-suite")


@dataclass
class FloorData:
    name: str
    ext_m: float  # external wall girth
    int_m: float  # internal wall girth
    junctions: int
    length_m: float  # outer overall size, centre-line joints plus one wall thickness
    width_m: float
    wall_plan_area_m2: float  # sum of wall length x thickness
    openings: list = field(default_factory=list)  # Opening
    rooms: list = field(default_factory=list)  # room names read from the plan

    @property
    def footprint_m2(self) -> float:
        return self.length_m * self.width_m

    @property
    def net_area_m2(self) -> float:
        return max(self.footprint_m2 - self.wall_plan_area_m2, 0.0)

    def wet_rooms(self) -> int:
        return sum(1 for r in self.rooms if any(w in r.lower() for w in WET))

    def has_kitchen(self) -> bool:
        return any("kitchen" in r.lower() for r in self.rooms)


def _rng(id: str, base: float) -> tuple[float, float, float]:
    lo, typ, hi = C.spread(id)
    return base * lo, base * typ, base * hi


def _est(key: str, desc: str, unit: str, q: tuple[float, float, float], coef: list[str], whole_units: bool = True) -> BoqItem:
    r = (lambda x: whole(x)) if whole_units else (lambda x: round(x, 2))
    return BoqItem(key, desc, unit, r(q[1]), basis="estimated", qty_low=r(q[0]), qty_high=r(q[2]), coef=coef)


def _mul(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] * b[0], a[1] * b[1], a[2] * b[2]


def pitch_range(inputs: dict, n_floors: int) -> tuple[float, float, float]:
    if inputs.get("pitch_deg"):
        p = float(inputs["pitch_deg"])
        return p, p, p
    return C.spread("roof_pitch_bungalow_deg" if n_floors == 1 else "roof_pitch_duplex_deg")


def roof_items(floors: list[FloorData], inputs: dict) -> tuple[list[BoqItem], dict]:
    """Roof from the ground floor envelope, the roof type and the pitch. Area is (length + 2 x overhang) x (width + 2 x overhang) over cos(pitch); the trims and timbers
    come from the author's own bills per m2 of roof. A flat roof is a slab with screed and membrane instead."""
    g = max(floors, key=lambda f: f.footprint_m2)
    typ = inputs["roof_type"]
    ov = C.spread("roof_eaves_overhang_m") if not inputs.get("overhang_m") else (float(inputs["overhang_m"]),) * 3
    plan = [(g.length_m + 2 * o) * (g.width_m + 2 * o) for o in ov]
    work = {"roof_type": typ, "ground_envelope_m": [round(g.length_m, 2), round(g.width_m, 2)], "plan_area_m2": [round(x, 1) for x in plan]}
    if typ == "flat":
        slab = tuple(a * t for a, t in zip(plan, C.spread("plans_suspended_slab_m3_per_m2_upper_floor")))
        return [_est("roof_slab_concrete_m3", "Reinforced in situ concrete (1:2:4); horizontal work not exceeding 300mm thick; roof slab", "m3", slab, ["plans_suspended_slab_m3_per_m2_upper_floor", "roof_eaves_overhang_m"]),
                _est("roof_screed_m2", "Screeds, beds and toppings to falls; over 600mm wide; roof", "m2", tuple(plan), ["roof_flat_screed_membrane_m2_per_m2_roof"]),
                _est("roof_membrane_m2", "Waterproofing membrane; coverings over 500mm wide; horizontal; roof", "m2", tuple(plan), ["roof_flat_screed_membrane_m2_per_m2_roof"])], work
    pitch = pitch_range(inputs, len(floors))
    slope = tuple(1 / math.cos(math.radians(p)) for p in pitch)
    complexity = C.spread("roof_complex_hip_factor") if typ == "hip" else (1.0, 1.0, 1.0)
    area = tuple(plan[i] * slope[i] * complexity[i] for i in range(3))
    work.update(pitch_deg=[round(p, 1) for p in pitch], slope_area_m2=[round(a, 1) for a in area])
    timbers = _mul(area, C.spread("plans_roof_timber_m_per_m2_roof"))
    fascia = _mul(area, C.spread("roof_fascia_m_per_m2_roof"))
    cov = f"{round(pitch[1])} degree pitch; {typ} roof"
    return [_est("roof_covering_m2", f"Roof coverings; type to be stated; sloping, {cov}; over 500mm wide; including ridges, hips, valleys and eaves", "m2", area, ["roof_pitch_duplex_deg", "roof_eaves_overhang_m", "roof_complex_hip_factor"]),
            _est("roof_timbers_m", "Primary or structural timbers; sawn hardwood; wall plates, tie beams, rafters, struts and purlins; sizes to be stated", "m", timbers, ["plans_roof_timber_m_per_m2_roof"]),
            _est("roof_fascia_m", "Fascia and barge boards; fixed to rafter feet", "m", fascia, ["roof_fascia_m_per_m2_roof"])], work


def frame_items(floors: list[FloorData]) -> tuple[list[BoqItem], dict]:
    """Columns, beams, suspended slabs, stairs and their steel and formwork, from the upper floor areas and the author's own ratios."""
    upper = sum(f.footprint_m2 for f in floors[1:])
    steel_kg = C.spread("plans_steel_kg_per_m3_structural_concrete")
    if upper:
        slab = _rng("plans_suspended_slab_m3_per_m2_upper_floor", upper)
        beams, cols = _mul(slab, C.spread("plans_beams_m3_per_slab_m3")), _mul(slab, C.spread("plans_columns_m3_per_slab_m3"))
        stairs = _rng("plans_staircase_concrete_m3_per_flight", len(floors) - 1)
        conc = tuple(slab[i] + beams[i] + cols[i] + stairs[i] for i in range(3))
        form = _mul(tuple(b + c for b, c in zip(beams, cols)), C.spread("frame_formwork_m2_per_m3"))
        items = [_est("suspended_slab_concrete_m3", "Reinforced in situ concrete (1:2:4); horizontal work not exceeding 300mm thick; suspended floor slabs", "m3", slab, ["plans_suspended_slab_m3_per_m2_upper_floor"]),
                 _est("frame_beams_concrete_m3", "Reinforced in situ concrete (1:2:4); horizontal work; floor and roof beams", "m3", beams, ["plans_beams_m3_per_slab_m3"]),
                 _est("frame_columns_concrete_m3", "Reinforced in situ concrete (1:2:4); vertical work not exceeding 300mm thick; columns", "m3", cols, ["plans_columns_m3_per_slab_m3"]),
                 _est("staircase_concrete_m3", "Reinforced in situ concrete (1:2:4); sloping work in staircases", "m3", stairs, ["plans_staircase_concrete_m3_per_flight"]),
                 _est("frame_formwork_soffit_m2", "Plain formwork to soffits of horizontal work; suspended slabs", "m2", tuple([upper * C.value("suspended_slab_soffit_formwork_m2_per_m2")] * 3), ["suspended_slab_soffit_formwork_m2_per_m2"]),
                 _est("frame_formwork_beams_columns_m2", "Plain formwork to sides of beams and columns", "m2", form, ["frame_formwork_m2_per_m3"])]
    else:  # a single-storey building: a ring beam on the walls
        g = floors[0]
        beams = _rng("ring_beam_section_m2", g.ext_m + g.int_m)
        conc, items = beams, [_est("frame_beams_concrete_m3", "Reinforced in situ concrete (1:2:4); ring beam 230 x 450", "m3", beams, ["ring_beam_section_m2"])]
    steel = tuple(conc[i] * steel_kg[i] / 1000 for i in range(3))
    items.append(_est("frame_steel_t", "High yield steel bar reinforcement; straight and bent; frame, slabs and stairs", "t", steel, ["plans_steel_kg_per_m3_structural_concrete"], whole_units=False))
    return items, {"upper_floor_area_m2": round(upper, 1), "frame_concrete_m3": [round(x, 1) for x in conc]}


def missing_openings(floors: list[FloorData], rates: dict) -> tuple[list[BoqItem], list[dict]]:
    """A plan read can miss openings (a wall the reader lost has none). When far fewer windows or doors are found than the author's own plans have per m2 of floor, the rest are
    added as estimated lines, at a standard size, and the estimate says so. Lintels follow the openings."""
    gfa = sum(f.footprint_m2 for f in floors)
    ops = [o for f in floors for o in f.openings]
    items, notes, extra_total = [], [], (0.0, 0.0, 0.0)
    for kind, coef, label, key, w, h, side in (("window", "plans_windows_per_m2_floor", "Windows", "windows_estimated_nr", 1.2, 1.2, True),
                                               ("door", "plans_doors_per_m2_floor", "Doors", "doors_estimated_nr", 0.9, 2.1, False)):
        found = sum(o.count for o in ops if o.kind == kind)
        want = _rng(coef, gfa)
        if found >= 0.6 * want[0]:
            continue
        extra = tuple(max(x - found, 0.0) for x in want)
        it = _est(key, f"{label} not found on the plans; estimated from the floor area; standard size {int(w * 1000)} x {int(h * 1000)}mm", "nr", extra, [coef])
        r = rates.get("window_base_nr", 0) + rates.get("window_per_m2", 0) * w * h if kind == "window" else rates.get("door_internal_nr")
        it.rate = round(r, -2) if r else None
        items.append(it)
        extra_total = tuple(a + b for a, b in zip(extra_total, extra))
        notes.append({"name": f"{kind}s_estimated", "value": f"{found:g} found, about {want[1]:.0f} expected", "basis": f"only {found:g} {kind}s were found on the plans for {gfa:.0f} m2 of floor; the rest are estimated from the author's own plans"})
    if items:
        lint = _est("lintels_estimated_nr", "Lintels over the estimated openings; precast concrete", "nr", extra_total, ["plans_windows_per_m2_floor", "plans_doors_per_m2_floor"])
        lint.rate = rates.get("lintel_nr")
        items.append(lint)
    return items, notes


def service_items(floors: list[FloorData]) -> list[BoqItem]:
    """One WC, basin, shower, water point and heater point for each wet room named on the plans, a sink for each kitchen."""
    wet = sum(f.wet_rooms() for f in floors)
    kitchens = sum(f.has_kitchen() for f in floors)
    items = []
    for key, desc, n in (("sanitary_wc_nr", "Water closet suite with cistern, seat and cover; supply and fix", wet), ("sanitary_basin_nr", "Wash hand basin with taps; supply and fix", wet),
                         ("sanitary_shower_nr", "Shower set with mixer and rose; supply and fix", wet), ("water_point_nr", "Cold water supply points complete with pipework and fittings", wet + kitchens),
                         ("sanitary_heater_nr", "Water heater points; supply and install", wet), ("sanitary_trap_nr", "Floor traps with gratings to wet areas", wet),
                         ("sanitary_sink_nr", "Kitchen sink unit with taps; supply and fix", kitchens)):
        if n:
            items.append(BoqItem(key, desc, "nr", n, coef=["wet_room_fixture_sets_per_wet_room"]))
    return items


def electrical_items(floors: list[FloorData]) -> list[BoqItem]:
    """Cable and points from the floor area, as ranges (the two bills the author supplied differ, so there is a spread). A plan cannot show the wiring, so all of it is estimated."""
    gfa = sum(f.footprint_m2 for f in floors)
    items = []
    for key, desc, unit, coef, whole_n in (("electrical_cable_m", "PVC insulated twin cable drawn in conduit; final circuits", "m", "electrical_cable_m_per_m2_gfa", True),
                                           ("electrical_socket_nr", "13A switched socket outlet points; complete", "nr", "electrical_socket_per_m2", True),
                                           ("electrical_switch_nr", "Lighting switch points; complete", "nr", "electrical_switch_per_m2", True),
                                           ("electrical_light_nr", "Lighting points complete with luminaire", "nr", "electrical_light_per_m2", True),
                                           ("electrical_ac_nr", "Air-conditioner power points; complete", "nr", "electrical_ac_per_m2", True),
                                           ("electrical_fan_nr", "Ceiling fan points; complete", "nr", "electrical_fan_per_m2", True),
                                           ("electrical_tv_nr", "TV and data outlet points; complete", "nr", "electrical_tv_per_m2", True),
                                           ("electrical_external_light_nr", "External lighting points complete with weatherproof fitting", "nr", "electrical_external_light_per_m2", True)):
        items.append(_est(key, desc, unit, _rng(coef, gfa), [coef], whole_n))
    return items


def finishes_items(floors: list[FloorData], h: float, openings_by_floor: dict[str, list[Opening]], t_wall: float) -> tuple[list[BoqItem], dict]:
    """Floor, ceiling and inside wall finishes and skirting from the plan dimensions: floor area is the building envelope less the walls; wall faces are the external
    girth plus both faces of the partitions less a thickness at each junction; voids over 1.00 m2 come off (BESMM4 1.28 M3, an internal opening twice)."""
    floor = sum(f.net_area_m2 for f in floors)
    faces = lambda f: max(f.ext_m + 2 * f.int_m - t_wall * f.junctions, 0.0)  # noqa: E731
    wall = 0.0
    doors = 0.0
    for f in floors:
        ops = openings_by_floor.get(f.name, [])
        wall += faces(f) * h - sum(o.area_m2 for o in deductible([o for o in ops if o.external])) - 2 * sum(o.area_m2 for o in deductible([o for o in ops if not o.external]))
        doors += sum(o.width_m * o.count * (1 if o.external else 2) for o in ops if o.kind == "door")
    skirt = sum(faces(f) for f in floors) - doors
    items = [BoqItem("floor_finish_m2", "Finish to floors; type of finish and overall thickness to be stated; over 600mm wide", "m2", whole(floor)),
             BoqItem("ceiling_finish_m2", "Ceilings, type of finish and overall thickness to be stated; over 600mm wide", "m2", whole(floor)),
             BoqItem("internal_wall_finish_m2", "Finish to walls; type of finish and overall thickness to be stated; internal; over 600mm wide; height to ceiling", "m2", whole(wall)),
             BoqItem("internal_wall_paint_m2", "Painting to general surfaces; internal walls; over 300mm girth", "m2", whole(wall)),
             BoqItem("skirting_m", "Skirtings, net height to be stated; net girth on face", "m", whole(skirt))]
    return items, {"net_floor_area_m2": round(floor, 1), "internal_wall_finish_m2": round(wall, 1)}


def foundation_items_from(floors: list[FloorData], block_mm: int = 230) -> tuple[list[BoqItem], list[dict]]:
    """Strip foundation from the ground floor walls, as before: trench girth is the wall girth less the overlaps at the joints, the trench is three block thicknesses
    wide, depths are flagged defaults. Column bases cannot be seen on a floor plan and are not included."""
    g = floors[0]
    total = g.ext_m + g.int_m
    overlaps = g.junctions * block_mm / 1000
    section, log, grade = strip_inputs(drawn={"block_mm": block_mm})
    assumptions = [{"name": f"foundation_{a.name}", "value": a.value, "basis": a.basis} for a in log if a.source == "assumed"]
    t = foundation_takeoff([GridLine("ground floor walls", runs=[(total, 1)], deductions=[(overlaps, 1)] if overlaps else [])], [], section)
    items = foundation_boq(t, section, grade)
    slab = g.length_m * g.width_m
    items += foundation_extras([], grade, slab_area_m2=slab, fill_area_m2=slab - total * block_mm / 1000)
    extras = {i.key: i.qty for i in items}
    items += substructure_extras(t, section, [], total - overlaps, g.length_m, g.width_m, extras)
    items = [i for i in items if i.key not in PAD_KEYS]  # with no pads these would only be the "minimum 1" of the whole-unit rule
    assumptions.append({"name": "column_bases", "value": "not included", "basis": "column bases cannot be seen on a floor plan; the strip footing is measured from the ground floor walls"})
    return items, assumptions


def set_opening_rates(items: list[BoqItem], openings: list[Opening], rates: dict) -> None:
    """Doors, windows and lintels are priced per piece from the rates in the author's bill: a window by its area, a door by the side of the wall it is in."""
    for i in items:
        o = next((x for x in openings if i.key == f"opening_{x.label.lower()}_nr" and f"{'external' if x.external else 'internal'}" in i.description), None)
        if i.key.startswith("lintel_") and rates.get("lintel_nr"):
            i.rate = rates["lintel_nr"]
        elif o and o.kind == "window" and rates.get("window_per_m2"):
            i.rate = round(rates.get("window_base_nr", 0) + rates["window_per_m2"] * o.width_m * o.height_m, -2)
        elif o and o.kind == "door" and rates.get("door_external_nr"):
            i.rate = rates["door_external_nr"] if o.external else rates["door_internal_nr"]


def estimate(floors: list[FloorData], inputs: dict, rates: dict | None = None) -> tuple[list[BoqItem], list[dict], dict]:
    """All the BoQ lines, the assumptions behind them, and the working (areas, pitch, ranges) for the user to see."""
    h = float(inputs["storey_height_m"])
    assumptions: list[dict] = []
    by_floor = {f.name: f.openings for f in floors}
    allops = [o for f in floors for o in f.openings]
    items = superstructure_boq({f.name: f.ext_m for f in floors}, {f.name: f.int_m for f in floors}, {f.name: h for f in floors}, allops)
    t_wall = 0.23
    fin, fw = finishes_items(floors, h, by_floor, t_wall)
    items += fin
    bearing = C.value("lintel_bearing_mm")
    lint, _ = lintel_items(allops, bearing)
    items += lint
    if lint:
        assumptions.append({"name": "lintel_bearing_mm", "value": bearing, "basis": "lintel bearing is not on a floor plan; assumed (see coefficients)"})
    found, fa = foundation_items_from(floors)
    items += found
    assumptions += fa
    set_opening_rates(items, allops, rates or {})
    more, notes = missing_openings(floors, rates or {})
    items += more
    assumptions += notes
    fr, frw = frame_items(floors)
    items += fr
    rf, rw = roof_items(floors, inputs)
    items += rf
    items += service_items(floors)
    items += electrical_items(floors)
    for o in allops:
        if o.assumed_height:
            assumptions.append({"name": f"opening_height_{o.label}", "value": o.height_m, "basis": "no height on the floor plan; the standard height was used"})
            break
    assumptions.append({"name": "storey_height_m", "value": h, "basis": "entered by the user: floor to floor"})
    assumptions.append({"name": "wall_finish_height", "value": h, "basis": "wall finish height taken as the storey height; BESMM4 measures it to the finished ceiling"})
    working = {"floors": [{"name": f.name, "envelope_m": [round(f.length_m, 2), round(f.width_m, 2)], "footprint_m2": round(f.footprint_m2, 1), "net_area_m2": round(f.net_area_m2, 1),
                           "wet_rooms": f.wet_rooms()} for f in floors], "gross_floor_area_m2": round(sum(f.footprint_m2 for f in floors), 1), **fw, **frw, "roof": rw}
    return order(items), assumptions, working
