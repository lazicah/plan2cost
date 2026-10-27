"""Deterministic foundation take-off (strip + pad). The model extracts dimensions; code does the maths.

Follows the author's method: girth is built grid line by grid line, pad-base widths are deducted from the
trench girth (pits are excavated separately) but not from the blockwork girth, which runs through the pads.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from plan2cost.tools.takeoff import to_10mm


def whole_units(x: float) -> int:
    """BESMM4 1.5.3: nearest whole unit, and anything under one unit is given as one."""
    return max(1, int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


@dataclass
class GridLine:
    name: str
    runs: list[tuple[float, int]] = field(default_factory=list)  # (length_m, number) full trench runs
    deductions: list[tuple[float, int]] = field(default_factory=list)  # pad-base widths, wall overlaps


@dataclass
class PadBase:
    type: str
    length_m: float
    width_m: float
    count: int


@dataclass
class StripSection:
    """Read from the foundation section on the structural drawing."""

    width_mm: float  # strip footing width as drawn; used via 10mm rounding (675 -> 0.68)
    footing_thickness_m: float
    trench_depth_m: float  # from ground level, topsoil included
    topsoil_m: float = 0.15
    below_blockwork_m: float = 0.35  # footing and bed below the foundation blockwork, from the section
    working_space_m: float = 0.6  # each side
    block_mm: int = 230

    @property
    def width_m(self) -> float:
        return to_10mm(self.width_mm / 1000)

    @property
    def dig_depth_m(self) -> float:
        return round(self.trench_depth_m - self.topsoil_m, 2)

    @property
    def blockwork_height_m(self) -> float:
        return round(self.dig_depth_m - self.below_blockwork_m, 2)


def trench_girth(lines: list[GridLine]) -> float:
    return sum(l * n for g in lines for l, n in g.runs) - sum(l * n for g in lines for l, n in g.deductions)


def blockwork_girth(lines: list[GridLine]) -> float:
    return sum(l * n for g in lines for l, n in g.runs)


def pit_excavation_m3(pads: list[PadBase], depth_m: float, round_each: bool = True) -> int:
    """The author rounds each pit's volume to a whole m3 before multiplying by the number of bases."""
    total = 0.0
    for p in pads:
        vol = p.length_m * p.width_m * depth_m
        total += (whole_units(vol) if round_each and vol >= 0.5 else vol) * p.count
    return whole_units(total)


def foundation_takeoff(lines: list[GridLine], pads: list[PadBase], s: StripSection) -> dict:
    t_girth, b_girth = whole_units(trench_girth(lines)), whole_units(blockwork_girth(lines))
    depth = s.dig_depth_m
    pad_perimeter = [(2 * (p.length_m + p.width_m), p.count) for p in pads]
    working = 2 * t_girth * s.working_space_m * depth + sum(per * s.working_space_m * depth * n for per, n in pad_perimeter)
    support = 2 * t_girth * depth + sum(per * depth * n for per, n in pad_perimeter)
    return {
        f"strip_trench_girth_{s.block_mm}_m": t_girth,
        f"fdn_blockwork_girth_{s.block_mm}_m": b_girth,
        "trench_excavation_strip_m3": whole_units(t_girth * s.width_m * depth),
        "pit_excavation_column_bases_m3": pit_excavation_m3(pads, depth),
        "working_space_m3": whole_units(working),
        "earthwork_support_m2": round(support, 2),
        "strip_footing_concrete_m3": whole_units(t_girth * s.width_m * s.footing_thickness_m),
        f"fdn_blockwork_{s.block_mm}_m2": whole_units(b_girth * s.blockwork_height_m),
    }
