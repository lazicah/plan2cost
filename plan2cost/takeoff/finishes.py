"""Rules for finishes and lintels, by BESMM4 section 1.28 and 1.29. Rules applied (book pages 232 and 236):
M1 area is net, in contact with the base; M3 no deduction for voids of 1.00 m2 or less; M5 work is internal unless stated external;
M8 wall finish height runs to the finished ceiling height. Openings are deducted from a room's walls only above 1.00 m2: an external opening
once, an internal opening twice (it is in the wall of two rooms). Quantities are whole units, minimum 1 (BESMM4 1.5)."""
import math

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


def lintels(openings: list[Opening], bearing_mm: float) -> list[tuple[str, float, int]]:
    """Precast lintels over openings (BESMM4 1.13.2.2.2, number, dimensioned description): one per opening, as long as the opening plus a bearing at each end."""
    return [(o.label, round(o.width_m + 2 * bearing_mm / 1000, 2), o.count) for o in openings]


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
