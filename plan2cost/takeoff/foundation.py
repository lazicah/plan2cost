"""Deterministic foundation take-off (strip + pad). The model reads printed values; code does the maths.

Follows the author's method: girth is built grid line by grid line, pad-base widths are deducted from the
trench girth (pits are excavated separately) but not from the blockwork girth, which runs through the pads.
"""
import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from plan2cost.takeoff.units import to_10mm


def whole_units(x: float) -> int:
    """BESMM4 1.5.3: nearest whole unit, and anything under one unit is given as one."""
    return max(1, int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


@dataclass
class GridLine:
    """One grid line's trench runs (length in metres, how many) and the deductions from them (pad-base widths, wall overlaps)."""
    name: str
    runs: list[tuple[float, int]] = field(default_factory=list)  # (length_m, number) full trench runs
    deductions: list[tuple[float, int]] = field(default_factory=list)  # pad-base widths, wall overlaps


@dataclass
class PadBase:
    """A pad foundation under a column: its type, size, thickness and how many."""
    type: str
    length_m: float
    width_m: float
    count: int
    thickness_m: float = 0.25  # as drawn on the pad base detail
    rebar: tuple[str, ...] = ()  # notes as printed, e.g. "06-Y1202@200c/c B"


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
    """Total length of trench: the runs less the deductions."""
    return sum(l * n for g in lines for l, n in g.runs) - sum(l * n for g in lines for l, n in g.deductions)


def blockwork_girth(lines: list[GridLine]) -> float:
    """Total length of foundation blockwork: the full runs."""
    return sum(l * n for g in lines for l, n in g.runs)


def pit_excavation_m3(pads: list[PadBase], depth_m: float, round_each: bool = True) -> int:
    """The author rounds each pit's volume to a whole m3 before multiplying by the number of bases."""
    total = 0.0
    for p in pads:
        vol = p.length_m * p.width_m * depth_m
        total += (whole_units(vol) if round_each and vol >= 0.5 else vol) * p.count
    return whole_units(total)


def foundation_takeoff(lines: list[GridLine], pads: list[PadBase], s: StripSection) -> dict:
    """The quantities of a strip foundation from its grid lines, pads and section: trench and blockwork girth, excavation, filling and concrete."""
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


def pad_concrete_m3(pads: list[PadBase]) -> int:
    """Concrete in the pad bases, rounded up to whole cubic metres."""
    return whole_units(sum(p.length_m * p.width_m * p.thickness_m * p.count for p in pads))


BAR_NOTE = re.compile(r"(\d+)\s*-\s*Y(\d{2})\d{2}\s*@\s*(\d+)")  # "06-Y1202@200c/c B": 6 bars, Y12, mark 02, 200 centres


def pad_rebar_kg(pads: list[PadBase], cover_m: float = 0.05) -> dict[int, float]:
    """Mass of base reinforcement by bar diameter (mm). Each note is one direction of a square base; bars run the full
    length less cover with both ends turned up the depth of the base less cover (assumed; not dimensioned on the drawing)."""
    kg: dict[int, float] = {}
    for p in pads:
        for note in p.rebar[:1]:  # the two directions are repeated notes for the same bars; take one and double it
            m = BAR_NOTE.search(note)
            if not m:
                continue
            n, d = int(m.group(1)), int(m.group(2))
            length = (p.length_m - 2 * cover_m) + 2 * (p.thickness_m - 2 * cover_m)
            kg[d] = kg.get(d, 0) + 2 * n * length * (d * d / 162.0) * p.count  # d^2/162 kg/m
    return kg


def ground_bed_takeoff(slab_area_m2: float, fill_area_m2: float | None = None, slab_t: float = 0.15, blinding_t: float = 0.05,
                       hardcore_t: float = 0.15, laterite_t: float = 0.15) -> dict:
    """Ground floor bed: slab concrete from the footprint; mesh and DPM from the rounded slab volume (as the author does);
    fills from the net bed area (footprint less the wall girth), rounded up."""
    fill = fill_area_m2 if fill_area_m2 is not None else slab_area_m2
    slab_m3 = whole_units(slab_area_m2 * slab_t)
    area = whole_units(slab_m3 / slab_t)
    up = lambda x: int(math.ceil(round(x, 6)))
    return {"ground_slab_m3": slab_m3, "brc_mesh_part1_m2": area, "dpm_polythene_m2": area,
            "blinding_on_hardcore_m3": up(fill * blinding_t), "hardcore_m3": up(fill * hardcore_t), "laterite_m3": up(fill * laterite_t)}
