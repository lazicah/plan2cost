"""Finishes from the rooms of a floor, by BESMM4 section 1.28 and 1.29. Rules applied (book pages 232 and 236):
M1 area is net, in contact with the base; M3 no deduction for voids of 1.00 m2 or less; M5 work is internal unless stated external;
M8 wall finish height runs to the finished ceiling height. Openings are deducted from a room's walls only above 1.00 m2: an external opening
once, an internal opening twice (it is in the wall of two rooms). Quantities are whole units, minimum 1 (BESMM4 1.5)."""
import math
from dataclasses import dataclass

from plan2cost.facts.rooms import Room
from plan2cost.takeoff.walls import Opening

VOID_M2 = 1.00  # BESMM4 1.28 M3


def whole(x: float) -> int:
    return max(1, math.ceil(round(x, 6))) if x > 0 else 0


def deductible(openings: list[Opening]) -> list[Opening]:
    """Only a void larger than 1.00 m2 is deducted; each opening is judged on its own size, not the total of its type."""
    return [o for o in openings if o.width_m * o.height_m > VOID_M2]


def external_finish_area(facade_m2: float, openings: list[Opening]) -> int:
    """External render or paint: the facade less each external opening over 1.00 m2."""
    return whole(facade_m2 - sum(o.area_m2 for o in deductible([o for o in openings if o.external])))


@dataclass
class FloorFinishes:
    floor: str
    rooms: int
    floor_area_m2: float
    ceiling_area_m2: float
    perimeter_m: float
    wall_area_m2: float
    door_width_m: float
    open_spaces: list
    unmeasured: list  # rooms without both dimensions printed
    wet_perimeter_m: float


def floor_finishes(floor: str, rooms: list[Room], height_m: float, openings: list[Opening], include_open: bool = False) -> FloorFinishes:
    """Quantities for one floor. Open spaces (porch, terrace, balcony) are left out unless asked for: they have a different finish."""
    enclosed = [r for r in rooms if r.area_m2 and (include_open or not r.open_space)]
    perimeter = sum(r.perimeter_m for r in enclosed)
    internal_voids = deductible([o for o in openings if not o.external])
    external_voids = deductible([o for o in openings if o.external])
    wall = perimeter * height_m - sum(o.area_m2 for o in external_voids) - 2 * sum(o.area_m2 for o in internal_voids)
    doors = sum(o.width_m * o.count * (1 if o.external else 2) for o in openings if o.kind == "door")
    return FloorFinishes(floor, len(enclosed), round(sum(r.area_m2 for r in enclosed), 2), round(sum(r.area_m2 for r in enclosed), 2), round(perimeter, 2), round(wall, 2),
                         round(doors, 2), [r.name for r in rooms if r.open_space], [r.name for r in rooms if not r.area_m2],
                         round(sum(r.perimeter_m for r in enclosed if r.wet), 2))


def lintels(openings: list[Opening], bearing_mm: float) -> list[tuple[str, float, int]]:
    """Precast lintels over openings (BESMM4 1.13.2.2.2, number, dimensioned description): one per opening, as long as the opening plus a bearing at each end."""
    return [(o.label, round(o.width_m + 2 * bearing_mm / 1000, 2), o.count) for o in openings]


def finishes_boq(floors: dict[str, FloorFinishes], facts: dict) -> tuple[list, list[str]]:
    """BoQ lines for floor, ceiling and internal wall finishes and skirting, with the questions a person must answer (a finish with no
    specification is still measured, worded 'to be stated', and asked about once). `facts` are the recorded facts by name."""
    from plan2cost.takeoff.boq import BoqItem

    if not floors:
        return [], []
    floor_m2 = whole(sum(f.floor_area_m2 for f in floors.values()))
    ceil_m2 = whole(sum(f.ceiling_area_m2 for f in floors.values()))
    wall_m2 = whole(sum(f.wall_area_m2 for f in floors.values()))
    skirt_m = whole(sum(f.perimeter_m - f.door_width_m for f in floors.values()))
    ask = []
    spec = {k: facts.get(k) for k in ("floor_finish_spec", "wall_finish_spec", "skirting_height_mm")}
    for k, q in (("floor_finish_spec", "What is the floor finish (for example ceramic tiles 400 x 400mm), and is it the same in every room?"),
                 ("wall_finish_spec", "What is the finish to the inside walls (for example cement-sand plaster, 15mm)?"),
                 ("skirting_height_mm", "What height is the skirting, and is it tile or another material?")):
        if not spec[k]:
            ask.append(q)
    items = [
        BoqItem("floor_finish_m2", f"Finish to floors; {spec['floor_finish_spec'] or 'type of finish and overall thickness to be stated'}; over 600mm wide", "m2", floor_m2),
        BoqItem("internal_wall_finish_m2", f"Finish to walls; {spec['wall_finish_spec'] or 'type of finish and overall thickness to be stated'}; internal; over 600mm wide; height to ceiling", "m2", wall_m2),
        BoqItem("internal_wall_paint_m2", "Painting to general surfaces; internal walls; over 300mm girth", "m2", wall_m2),
        BoqItem("ceiling_finish_m2", "Ceilings, type of finish and overall thickness to be stated; over 600mm wide", "m2", ceil_m2),
        BoqItem("skirting_m", f"Skirtings, net height {spec['skirting_height_mm'] or 'to be stated'}{'mm' if spec['skirting_height_mm'] else ''}; net girth on face", "m", skirt_m),
    ]
    return items, ask


def lintel_items(openings: list[Opening], bearing_mm: float | None) -> tuple[list, list[str]]:
    """Precast concrete lintels, one per opening. The bearing at each end is the surveyor's or designer's choice, so it is asked about, never assumed."""
    from plan2cost.takeoff.boq import BoqItem

    if not openings:
        return [], []
    if not bearing_mm:
        return [], ["How much bearing does each lintel have on the wall at each end (for example 225mm)?"]
    out: dict = {}
    for o in openings:
        key = f"lintel_{o.label.lower()}_nr"
        desc = f"Lintels; precast concrete; over {o.label} {o.kind} {int(o.width_m * 1000)}mm; {int((o.width_m + 2 * bearing_mm / 1000) * 1000)}mm long, {int(bearing_mm)}mm bearing each end"
        n = out[key].qty if key in out else 0
        out[key] = BoqItem(key, desc, "nr", n + o.count)
    return list(out.values()), []
