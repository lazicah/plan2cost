"""Deterministic quantity take-off. The model extracts dimensions; code does the maths."""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum


@dataclass
class Room:
    name: str
    length_m: float
    width_m: float


@dataclass
class Plan:
    rooms: list[Room]
    wall_height_m: float = 3.0
    external_wall_thickness_m: float = 0.225
    openings_area_m2: float = 0.0  # doors + windows
    notes: list[str] = field(default_factory=list)


def floor_area(plan: Plan) -> float:
    return round(sum(r.length_m * r.width_m for r in plan.rooms), 2)


def wall_area(plan: Plan) -> float:
    """Gross internal perimeter wall area minus openings (simple first-pass rule)."""
    perimeter = sum(2 * (r.length_m + r.width_m) for r in plan.rooms)
    return round(perimeter * plan.wall_height_m - plan.openings_area_m2, 2)


def takeoff(plan: Plan) -> dict:
    return {"floor_area_m2": floor_area(plan), "wall_area_m2": wall_area(plan)}


def missing_inputs(plan: Plan) -> list[str]:
    """Self-check: what the agent must ask the user instead of guessing."""
    gaps = []
    if not plan.rooms:
        gaps.append("no rooms extracted")
    if plan.openings_area_m2 == 0:
        gaps.append("door/window schedule missing")
    return gaps


class DimKind(str, Enum):
    """How a drawn dimension was taken. It decides how girth is derived."""

    CENTRE_LINE = "centre_line"  # wall centre to wall centre
    END_TO_END = "end_to_end"  # overall, external face to external face
    IN_TO_IN = "in_to_in"  # clear distance between internal faces


@dataclass
class WallRun:
    label: str
    length_m: float
    kind: DimKind
    thickness_mm: int  # as drawn, used as-is (230 stays 230)
    end_thickness_mm: tuple[int, int] | None = None  # walls met at each end; defaults to thickness_mm
    count: int = 1
    external: bool = False


def to_10mm(x: float) -> float:
    """BESMM4 1.5.2: dimensions to the nearest 10mm (5mm and over rounds up)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def centre_line_m(run: WallRun) -> float:
    """BESMM4 masonry M1: walls are measured on the centre line."""
    a, b = run.end_thickness_mm or (run.thickness_mm, run.thickness_mm)
    half_ends = (a + b) / 2 / 1000
    if run.kind is DimKind.CENTRE_LINE:
        cl = run.length_m
    elif run.kind is DimKind.END_TO_END:
        cl = run.length_m - half_ends
    else:
        cl = run.length_m + half_ends
    return to_10mm(cl)


def girth(runs: list[WallRun]) -> dict:
    """Centre-line girth by location and drawn thickness, e.g. {"ext_girth_230_m": 98.62}."""
    out: dict[str, float] = {}
    for r in runs:
        key = f"{'ext' if r.external else 'int'}_girth_{r.thickness_mm}_m"
        out[key] = out.get(key, 0.0) + centre_line_m(r) * r.count
    out = {k: round(v, 2) for k, v in out.items()}
    for t in sorted({r.thickness_mm for r in runs}):
        out[f"total_girth_{t}_m"] = round(sum(v for k, v in out.items() if k.endswith(f"_girth_{t}_m")), 2)
    return out
