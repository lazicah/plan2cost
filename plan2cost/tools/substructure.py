"""The substructure items beyond the strip, pits and ground bed: topsoil, surface treatment, levelling, blinding, columns in the
foundation, formwork, disposal and backfill, void filling and foundation wall finishes. Formulas follow the author's method (each one
reproduces his plan2 sheet, see tests). Deterministic: inputs come from the drawings, never from the model's arithmetic."""
import math
from dataclasses import dataclass

from plan2cost.tools.foundation import PadBase, whole_units


def roundup(x: float) -> int:
    return int(math.ceil(round(x, 6)))


@dataclass
class FoundationColumn:
    """A column from its base to the ground floor level: section in metres and the number of columns of this size."""
    width_m: float
    depth_m: float
    count: int
    height_m: float = 1.5


def topsoil_strip_m2(length_m: float, width_m: float, working_space_m: float = 0.6, factor: float = 1.0) -> int:
    """BESMM4 (Excavating and filling, site preparation): remove topsoil, m2, depth stated. Area taken as the building's overall length and width
    plus working space both sides. `factor` exists only because the author's plan2 sheet gives 226: he multiplied by 0.95 by hand to reduce the area
    (his own words: a decision at the time, not a convention), so it stays 1.0."""
    return whole_units((length_m + 2 * working_space_m) * (width_m + 2 * working_space_m) * factor)


def levelling_compaction_m2(trench_girth_m: float, trench_width_m: float, pads: list[PadBase]) -> int:
    return roundup(trench_girth_m * trench_width_m + sum(p.length_m * p.width_m * p.count for p in pads))


def blinding_foundations_m3(trench_girth_m: float, trench_width_m: float, pads: list[PadBase], strip_mm: float = 50, base_mm: float = 100) -> int:
    """50mm under the strip, 100mm under the column bases."""
    return roundup(trench_girth_m * trench_width_m * strip_mm / 1000 + sum(p.length_m * p.width_m * base_mm / 1000 * p.count for p in pads))


def columns_in_foundation(cols: list[FoundationColumn]) -> dict:
    return {"column_concrete_m3": round(sum(c.width_m * c.depth_m * c.height_m * c.count for c in cols), 2),
            "formwork_column_sides_m2": whole_units(sum((c.width_m + c.depth_m) * 2 * c.height_m * c.count for c in cols))}


def formwork_foundation_sides_m2(pads: list[PadBase]) -> int:
    """Column bases only: the strip footing is cast against the trench sides."""
    return whole_units(sum(2 * (p.length_m + p.width_m) * p.thickness_m * p.count for p in pads))


def formwork_foundation_sides_m(pads: list[PadBase]) -> int:
    """BESMM4 1.11.6.13.1: sides of foundations and bases up to 500mm high are measured in metres, width (height of the side) stated.
    Column bases only; the strip footing is cast against the trench sides."""
    return whole_units(sum(2 * (p.length_m + p.width_m) * p.count for p in pads))


def disposal_and_backfill(excavation_m3: float, blockwork_girth_m: float, blockwork_height_m: float, block_mm: int, blinding_m3: float,
                          footing_m3: float, bases_m3: float, columns_m3: float) -> dict:
    """Disposal is what the permanent works below ground displace; backfill is the excavation less that disposal."""
    disposal = whole_units(blockwork_girth_m * blockwork_height_m * block_mm / 1000 + blinding_m3 + footing_m3 + bases_m3 + columns_m3)
    return {"disposal_off_site_m3": disposal, "backfill_around_foundations_m3": whole_units(excavation_m3 - disposal)}


BLOCKS_PER_M2 = 10  # the author's count of 450 x 225 blocks per m2 of wall face, the same for every thickness
VOID_PER_BLOCK_M3 = 0.01153  # the author's constant for the 225mm block; other thicknesses scale from it
BASE_BLOCK_MM = 225


def void_filling_m3(blockwork_area_m2: float, block_mm: int = BASE_BLOCK_MM, blocks_per_m2: float = BLOCKS_PER_M2) -> float:
    """Mass concrete in the cores of the hollow blocks below DPC: blocks x void per block. 10 blocks per m2 for 225, 150 and 100mm blocks alike;
    the void per block is the author's 0.01153 m3 for the 225mm block, scaled by thickness for the others (the width changes the volume).
    225mm: 89 m2 gives his 10.26 m3."""
    return round(blockwork_area_m2 * blocks_per_m2 * VOID_PER_BLOCK_M3 * block_mm / BASE_BLOCK_MM, 2)
