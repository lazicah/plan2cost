"""Walls from exact vector lines: a wall is two parallel face lines a wall-thickness apart that run alongside each other. Candidates only;
the weight of the lines and what else is drawn around them is kept so the next stage (model and cross-checks) can judge each one."""
from collections import defaultdict
from dataclasses import dataclass

from plan2cost.vector import Seg
from plan2cost.walls_cv import Wall

AXIS_TOL_PT = 0.06
THICKNESS_MM = {100: (85, 135), 150: (135, 190), 230: (195, 270)}  # nominal block thickness -> accepted face spacing


@dataclass
class Line:
    orient: str  # "h" or "v"
    pos: float  # y for "h", x for "v" (points)
    a: float
    b: float
    w: float

    @property
    def length(self) -> float:
        return self.b - self.a


def axis_lines(segs: list[Seg], min_len_pt: float = 2.0) -> list[Line]:
    """Axis-aligned segments, with collinear overlapping or touching ones of the same weight joined into one maximal line."""
    raw = []
    for s in segs:
        if s.dashed:
            continue
        if abs(s.y0 - s.y1) <= AXIS_TOL_PT:
            raw.append(Line("h", (s.y0 + s.y1) / 2, min(s.x0, s.x1), max(s.x0, s.x1), s.w))
        elif abs(s.x0 - s.x1) <= AXIS_TOL_PT:
            raw.append(Line("v", (s.x0 + s.x1) / 2, min(s.y0, s.y1), max(s.y0, s.y1), s.w))
    groups: dict = defaultdict(list)
    for l in raw:
        groups[(l.orient, round(l.pos / 0.1), round(l.w, 2))].append(l)
    out = []
    for g in groups.values():
        g.sort(key=lambda l: l.a)
        cur = None
        for l in g:
            if cur and l.a <= cur.b + 0.3:
                cur.b = max(cur.b, l.b)
            else:
                cur = Line(l.orient, l.pos, l.a, l.b, l.w)
                out.append(cur)
    return [l for l in out if l.length >= min_len_pt]


def pair_walls(lines: list[Line], mm_per_pt: float, min_run_mm: float = 350, windows: dict | None = None) -> list[dict]:
    """Candidate wall pieces: every pair of parallel lines whose spacing is a block thickness and that overlap for at least `min_run_mm`.
    Each carries the line weights so the caller can tell face lines from fixtures and hatching."""
    windows = windows or THICKNESS_MM
    out = []
    for orient in ("h", "v"):
        ls = sorted((l for l in lines if l.orient == orient), key=lambda l: l.pos)
        for i, l1 in enumerate(ls):
            for l2 in ls[i + 1:]:
                gap = (l2.pos - l1.pos) * mm_per_pt
                if gap > max(hi for _, hi in windows.values()):
                    break
                nominal = next((n for n, (lo, hi) in windows.items() if lo <= gap <= hi), None)
                a, b = max(l1.a, l2.a), min(l1.b, l2.b)
                if nominal and (b - a) * mm_per_pt >= min_run_mm:
                    out.append({"orient": orient, "centre_pt": (l1.pos + l2.pos) / 2, "a_pt": a, "b_pt": b, "nominal": nominal, "gap_mm": gap, "gap_pt": l2.pos - l1.pos, "w": (l1.w, l2.w)})
    return out


def to_walls(pieces: list[dict], mm_per_pt: float) -> list[Wall]:
    return [Wall(p["orient"], p["centre_pt"] * mm_per_pt, p["a_pt"] * mm_per_pt, p["b_pt"] * mm_per_pt, p["nominal"]) for p in pieces]


def wall_weight_classes(pieces: list[dict], tol: float = 0.02) -> dict[float, float]:
    """Total candidate length (points) per line weight, counting only pairs whose two face lines have the same weight: that is how a CAD
    export draws a cut wall. Fixtures, text and dimension ticks pair lines of different weights."""
    out: dict[float, float] = defaultdict(float)
    for p in pieces:
        if abs(p["w"][0] - p["w"][1]) <= tol:
            out[round(p["w"][0], 2)] += p["b_pt"] - p["a_pt"]
    return dict(out)


def extend_to_centrelines(walls: list[Wall], tol_mm: float = 60) -> list[Wall]:
    """Face lines end at the faces of the walls they meet; the surveyor's run goes to the centre line of the wall it joins. Each end that
    meets a perpendicular wall is extended by half that wall's thickness. Free ends (a wall ending at an opening or an end) are left alone."""
    out = []
    for w in walls:
        ext = [0.0, 0.0]
        for i, end in enumerate((w.start_mm, w.end_mm)):
            for v in walls:
                if v is w or v.orient == w.orient:
                    continue
                if abs(end - (v.centre_mm - v.thickness_mm / 2 if (i == 1) else v.centre_mm + v.thickness_mm / 2)) <= tol_mm and v.start_mm - tol_mm <= w.centre_mm <= v.end_mm + tol_mm:
                    ext[i] = v.thickness_mm / 2
                    break
        out.append(Wall(w.orient, w.centre_mm, w.start_mm - ext[0], w.end_mm + ext[1], w.thickness_mm))
    return out


def class_network(lines: list[Line], weight: float, mm_per_pt: float, bridge_mm: float = 3600) -> tuple[list[Wall], dict]:
    """The wall network one line weight would make: pair its lines, merge into runs, keep the biggest connected group, and report how
    building-like it is (length, joints between perpendicular runs)."""
    from plan2cost.walls_cv import _merge, junctions

    cls = [l for l in bridge_lines([l for l in lines if round(l.w, 2) == weight], mm_per_pt, bridge_mm) if l.length * mm_per_pt >= 600]
    if len(cls) < 4:
        return [], {"length_m": 0.0, "joints": 0}
    base = to_walls(pair_walls(cls, mm_per_pt, min_run_mm=600), mm_per_pt)
    walls = largest_cluster([m for n in sorted({b.thickness_mm for b in base}) for m in _merge([b for b in base if b.thickness_mm == n], bridge_mm=bridge_mm)])
    return walls, {"length_m": round(sum(w.length_mm for w in walls) / 1000, 1), "joints": junctions(walls)}


def wall_weight(lines: list[Line], mm_per_pt: float, min_length_m: float = 40.0, min_joints: int = 10) -> tuple[float | None, dict]:
    """The weight cut walls are drawn at: the heaviest stroke weight whose lines pair up into a building-sized, jointed, connected network
    (at least `min_length_m` of wall with `min_joints` T and L joints). Fixtures, hatching and annotation are lighter and do not form such a
    network at the heavy weights; sheet borders do not either, because they carry no joints."""
    nets = {}
    for w in sorted({round(l.w, 2) for l in lines}, reverse=True):
        walls, stats = class_network(lines, w, mm_per_pt)
        nets[w] = stats
        if stats["length_m"] >= min_length_m and stats["joints"] >= min_joints:
            return w, nets
    return None, nets


def bridge_lines(lines: list[Line], mm_per_pt: float, bridge_mm: float = 3600) -> list[Line]:
    """Join collinear face lines across the gaps left by openings (a window or door interrupts the face line)."""
    out: list[Line] = []
    for orient in ("h", "v"):
        groups: dict = defaultdict(list)
        for l in lines:
            if l.orient == orient:
                groups[round(l.pos / 0.3)].append(l)
        for g in groups.values():
            g.sort(key=lambda l: l.a)
            cur = None
            for l in g:
                if cur and (l.a - cur.b) * mm_per_pt <= bridge_mm:
                    cur.b = max(cur.b, l.b)
                else:
                    cur = Line(orient, l.pos, l.a, l.b, l.w)
                    out.append(cur)
    return out


def find_walls_vector(lines: list[Line], mm_per_pt: float, bridge_mm: float = 3600) -> tuple[list[Wall], dict]:
    """Walls from face lines: take the wall weight, bridge the lines across openings, pair them at block thickness, merge into runs and
    take each to the centre line of the wall it meets. Returns the walls and what was used, for the caller to report."""
    w, nets = wall_weight(lines, mm_per_pt)
    if w is None:
        return [], {"wall_weight": None, "networks": nets}
    bridged = bridge_lines([l for l in lines if abs(l.w - w) <= 0.02], mm_per_pt, bridge_mm)  # a corner stub next to a window joins its wall first
    heavy = [l for l in bridged if l.length * mm_per_pt >= 600]  # then a face line is long; hatch and fixture strokes are not
    pieces = pair_walls(heavy, mm_per_pt, min_run_mm=350)
    from plan2cost.walls_cv import _merge

    base = to_walls(pieces, mm_per_pt)
    walls = extend_to_centrelines([m for n in sorted({b.thickness_mm for b in base}) for m in _merge([b for b in base if b.thickness_mm == n], bridge_mm=bridge_mm)])
    walls = largest_cluster(walls)
    return walls, {"wall_weight": w, "pieces": len(pieces), "networks": nets}


def largest_cluster(walls: list[Wall], link_mm: float = 1500) -> list[Wall]:
    """The walls of the building: walls linked to one another (their extents come within `link_mm`), keeping the biggest group. A detail, a
    legend or a second drawing on the same sheet forms its own small group and is dropped."""
    n = len(walls)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def box(w):
        return (w.start_mm, w.centre_mm - w.thickness_mm / 2, w.end_mm, w.centre_mm + w.thickness_mm / 2) if w.orient == "h" else (w.centre_mm - w.thickness_mm / 2, w.start_mm, w.centre_mm + w.thickness_mm / 2, w.end_mm)

    boxes = [box(w) for w in walls]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if a[0] - link_mm <= b[2] and b[0] - link_mm <= a[2] and a[1] - link_mm <= b[3] and b[1] - link_mm <= a[3]:
                parent[find(i)] = find(j)
    groups: dict[int, list[Wall]] = defaultdict(list)
    for i, w in enumerate(walls):
        groups[find(i)].append(w)
    return max(groups.values(), key=lambda g: sum(w.length_mm for w in g)) if groups else []
