"""Rules for finishes and lintels, by BESMM4 section 1.28 and 1.29. Rules applied (book pages 232 and 236):
M1 area is net, in contact with the base; M3 no deduction for voids of 1.00 m2 or less; M5 work is internal unless stated external;
M8 wall finish height runs to the finished ceiling height. Openings are deducted from a room's walls only above 1.00 m2: an external opening
once, an internal opening twice (it is in the wall of two rooms). Quantities are whole units, minimum 1 (BESMM4 1.5)."""
import math

from plan2cost.takeoff.walls import Opening

VOID_M2 = 1.00  # BESMM4 1.28 M3


def whole(x: float) -> int:
    """Round up to whole units, at least 1 for anything above zero (BESMM4 1.5)."""
    return max(1, math.ceil(round(x, 6))) if x > 0 else 0


def deductible(openings: list[Opening]) -> list[Opening]:
    """Only a void larger than 1.00 m2 is deducted; each opening is judged on its own size, not the total of its type."""
    return [o for o in openings if o.width_m * o.height_m > VOID_M2]


def external_finish_area(facade_m2: float, openings: list[Opening]) -> int:
    """External render or paint: the facade less each external opening over 1.00 m2."""
    return whole(facade_m2 - sum(o.area_m2 for o in deductible([o for o in openings if o.external])))





def lintel_length_m(openings: list[Opening], bearing_mm: float) -> float:
    """Total length of lintel over the openings: each opening's width plus the bearing on the wall at both ends."""
    return sum(o.count * (o.width_m + 2 * bearing_mm / 1000) for o in openings)


def lintel_items(length_m: tuple[float, float, float], measured_m: float, thickness_m: float, depth_mm: float, steel_kg_per_m3: tuple[float, float, float], bearing_mm: float) -> list:
    """Lintels as the work they are, not as pieces: reinforced concrete, formwork to the sides and soffit, and reinforcement, from the total length of lintel (a chain lintel along the
    external walls, and each internal opening's width plus the bearing at both ends). `measured_m` is the part of the length measured from the plan; the rest of `length_m`
    (low, typical, high) is over openings estimated from the floor area. Concrete and formwork follow the section; the steel is estimated from a ratio."""
    from plan2cost.takeoff.boq import BoqItem

    if length_m[1] <= 0:
        return []
    depth = depth_mm / 1000
    conc = tuple(x * thickness_m * depth for x in length_m)
    form = tuple(x * (2 * depth + thickness_m) for x in length_m)
    steel = tuple(conc[i] * steel_kg_per_m3[i] for i in range(3))
    basis = "measured" if length_m[0] == length_m[2] else "estimated"
    sect = f"{int(thickness_m * 1000)} x {int(depth_mm)}mm section, {int(bearing_mm)}mm bearing each end"
    items = []
    for key, desc, unit, q, b in (("lintel_concrete_m3", f"Reinforced in situ concrete (1:2:4); chain lintel along the external walls and lintels over internal openings; {sect}", "m3", conc, basis),
                                  ("lintel_formwork_m2", "Plain formwork to sides and soffit of lintels", "m2", form, basis),
                                  ("lintel_steel_kg", "High yield steel bar reinforcement to lintels", "kg", steel, "estimated")):
        it = BoqItem(key, desc, unit, whole(q[1]), basis=b)
        if b == "estimated":
            it.qty_low, it.qty_high, it.coef = whole(q[0]), whole(q[2]), ["lintel_steel_kg_per_m3"] if key.endswith("kg") else ["plans_windows_per_m2_floor", "plans_doors_per_m2_floor"]
        items.append(it)
    return items
