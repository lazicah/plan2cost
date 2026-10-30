"""Deterministic blockwork area: girth x storey height less openings that have block above or beneath (author's method)."""
import math
from dataclasses import dataclass

DEFAULT_STOREY_HEIGHT_M = 3.0  # used when no elevation or section gives the height


@dataclass
class Opening:
    """A type of door or window on a floor: label, width, height, how many, kind, whether it is in an external wall, and whether the height is the standard (not on the plan)."""
    label: str
    width_m: float
    height_m: float
    count: int = 1
    kind: str = "window"  # "door" or "window"
    external: bool = True
    assumed_height: bool = False  # the height was not on the plan; the standard height was used

    @property
    def area_m2(self) -> float:
        return self.width_m * self.height_m * self.count


def facade_area_m2(girth_by_floor: dict[str, float], height_by_floor: dict[str, float] | None = None) -> float:
    """Wall area of the facade: girth times height for each floor (the default storey height where none is given)."""
    heights = height_by_floor or {}
    return sum(g * heights.get(floor, DEFAULT_STOREY_HEIGHT_M) for floor, g in girth_by_floor.items())


def blockwork_area_m2(girth_by_floor: dict[str, float], height_by_floor: dict[str, float] | None,
                      openings: list[Opening]) -> int:
    """Facade area less openings, rounded up to a whole m2 (the author's ROUNDUP)."""
    net = facade_area_m2(girth_by_floor, height_by_floor) - sum(o.area_m2 for o in openings)
    return max(0, math.ceil(round(net, 6)))
