"""Deterministic quantity take-off. The model extracts dimensions; code does the maths."""
from dataclasses import dataclass, field


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
