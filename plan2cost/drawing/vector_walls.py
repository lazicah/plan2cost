"""Walls from exact vector lines: a wall is two parallel face lines a wall-thickness apart that run alongside each other. Candidates only;
the weight of the lines and what else is drawn around them is kept so the next stage (model and cross-checks) can judge each one."""
from collections import defaultdict
from dataclasses import dataclass, field

from plan2cost.drawing.vector import Seg
from plan2cost.drawing.walls_cv import Wall

AXIS_TOL_PT = 0.06
THICKNESS_MM = {100: (85, 135), 150: (135, 190), 230: (195, 270)}  # nominal block thickness -> accepted face spacing


@dataclass
class Line:
    """A horizontal or vertical run of line work after collinear segments are merged: its direction, its position across (points), its start and end along it, and its stroke width (or the measured thickness for a raster line)."""
    orient: str  # "h" or "v"
    pos: float  # y for "h", x for "v" (points)
    a: float
    b: float
    w: float
    raw: float = 0.0  # the measured thickness when `w` has been grouped into a weight class (raster); 0 means w is exact
    gaps: list = field(default_factory=list)  # (a, b) stretches this line was bridged across: where the face is broken

    @property
    def length(self) -> float:
        return self.b - self.a

    @property
    def thickness(self) -> float:
        return self.raw or self.w


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


def _both_broken(g1: list, g2: list, lo: float, hi: float) -> list:
    """Stretches within lo..hi where both faces are broken: an opening interrupts a wall's two faces together."""
    out = []
    for a1, b1 in g1:
        for a2, b2 in g2:
            a, b = max(a1, a2, lo), min(b1, b2, hi)
            if b > a:
                out.append((a, b))
    return out


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
                    out.append({"orient": orient, "centre_pt": (l1.pos + l2.pos) / 2, "a_pt": a, "b_pt": b, "nominal": nominal, "gap_mm": gap, "gap_pt": l2.pos - l1.pos, "w": (l1.w, l2.w),
                                "gaps_pt": _both_broken(l1.gaps, l2.gaps, a, b)})
    return out


def to_walls(pieces: list[dict], mm_per_pt: float) -> list[Wall]:
    """Wall pieces in points as `Wall` runs in millimetres."""
    return [Wall(p["orient"], p["centre_pt"] * mm_per_pt, p["a_pt"] * mm_per_pt, p["b_pt"] * mm_per_pt, p["nominal"],
                 [(a * mm_per_pt, b * mm_per_pt) for a, b in p.get("gaps_pt", [])]) for p in pieces]


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
        out.append(Wall(w.orient, w.centre_mm, w.start_mm - ext[0], w.end_mm + ext[1], w.thickness_mm, list(w.gaps)))
    return out


def drop_centreline_halves(pieces: list[dict]) -> list[dict]:
    """A grid or centre line drawn down the middle of a wall pairs with each face at half the thickness. When a full-thickness pair lies over
    the same span with that line in the middle, the two half-pairs are not walls."""
    keep = []
    for p in pieces:
        half = False
        for q in pieces:
            if q is p or q["orient"] != p["orient"] or abs(q["gap_pt"] - 2 * p["gap_pt"]) > 0.1 * q["gap_pt"]:
                continue
            over = min(p["b_pt"], q["b_pt"]) - max(p["a_pt"], q["a_pt"])
            if over >= 0.5 * (p["b_pt"] - p["a_pt"]) and abs(abs(q["centre_pt"] - p["centre_pt"]) - p["gap_pt"] / 2) <= 0.3:
                half = True
                break
        if not half:
            keep.append(p)
    return keep


BAR_MM = (80, 450)  # a solid band this wide on the drawing is a wall drawn as one bar (a block thickness, a little under or over)


def _is_bar(l: Line, mm_per_unit: float, upper_mm: float = BAR_MM[1]) -> bool:
    return BAR_MM[0] <= l.thickness * mm_per_unit <= upper_mm and l.length * mm_per_unit >= 600 and l.thickness >= 3


def bar_walls(lines: list[Line], mm_per_unit: float, min_weight: float = 0.0, paired: list[Wall] | None = None, dominant: float | None = None) -> list[Wall]:
    """Walls drawn as a single solid bar: one thick run whose width is a block thickness. Its position is the centre line already. A thick
    face line that belongs to a pair is not a bar, so runs lying on an already paired wall are skipped."""
    out = []
    for l in lines:
        if round(l.w, 2) >= min_weight - 1e-6 and _is_bar(l, mm_per_unit):
            if any(p.orient == l.orient and abs(p.centre_mm - l.pos * mm_per_unit) <= p.thickness_mm * 0.9 + l.thickness * mm_per_unit / 2 and
                   min(p.end_mm, l.b * mm_per_unit) - max(p.start_mm, l.a * mm_per_unit) >= 0.4 * l.length * mm_per_unit for p in (paired or [])):
                continue
            gap = l.thickness * mm_per_unit
            if dominant:  # drawn bars carry their outline: class a bar by its width against the dominant bar (the dominant one is the main wall)
                ratio = l.thickness / dominant
                nominal = 230 if ratio >= 0.8 else 150 if ratio >= 0.5 else 100
            else:
                nominal = next((n for n, (lo, hi) in THICKNESS_MM.items() if lo * 0.85 <= gap <= hi * 1.25), None)
            if nominal:
                out.append(Wall(l.orient, l.pos * mm_per_unit, l.a * mm_per_unit, l.b * mm_per_unit, float(nominal)))
    return out


def class_network(lines: list[Line], weight: float, mm_per_pt: float, bridge_mm: float = 3600, primitive: str = "pair", dominant_bar: float | None = None) -> tuple[list[Wall], dict]:
    """The wall network one line weight would make: pair its lines, merge into runs, keep the biggest connected group, and report how
    building-like it is (length, joints between perpendicular runs)."""
    from plan2cost.drawing.walls_cv import merge_runs, junctions

    cls = [l for l in bridge_lines([l for l in lines if round(l.w, 2) >= weight - 1e-6], mm_per_pt, bridge_mm) if l.length * mm_per_pt >= 600]
    if len(cls) < 4 and primitive == "pair":
        return [], {"length_m": 0.0, "joints": 0}
    pairs = to_walls(drop_centreline_halves(pair_walls(cls, mm_per_pt, min_run_mm=600)), mm_per_pt) if primitive == "pair" else []
    base = pairs + (bar_walls(lines, mm_per_pt, weight, pairs, dominant_bar) if primitive == "bar" else [])
    walls = largest_cluster([m for n in sorted({b.thickness_mm for b in base}) for m in merge_runs([b for b in base if b.thickness_mm == n], bridge_mm=bridge_mm)])
    return walls, {"length_m": round(sum(w.length_mm for w in walls) / 1000, 1), "joints": junctions(walls)}


def wall_weight(lines: list[Line], mm_per_pt: float, min_length_m: float = 40.0, min_joints: int = 10, primitive: str = "pair") -> tuple[float | None, dict]:
    """The weight cut walls are drawn at: the heaviest stroke weight whose lines pair up into a building-sized, jointed, connected network
    (at least `min_length_m` of wall with `min_joints` T and L joints). Fixtures, hatching and annotation are lighter and do not form such a
    network at the heavy weights; sheet borders do not either, because they carry no joints."""
    nets = {}
    for w in sorted({round(l.w, 2) for l in lines}, reverse=True):  # a threshold: all lines at least this heavy
        walls, stats = class_network(lines, w, mm_per_pt, primitive=primitive)
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
                    if l.a > cur.b + 0.3:
                        cur.gaps.append((cur.b, l.a))
                    cur.gaps.extend(l.gaps)
                    cur.b = max(cur.b, l.b)
                else:
                    cur = Line(orient, l.pos, l.a, l.b, l.w, l.raw, list(l.gaps))
                    out.append(cur)
    return out


def find_walls_vector(lines: list[Line], mm_per_pt: float, bridge_mm: float = 3600, primitive: str = "pair", min_length_m: float = 40.0, min_joints: int = 10, dominant_bar: float | None = None) -> tuple[list[Wall], dict]:
    """Walls from face lines: take the wall weight, bridge the lines across openings, pair them at block thickness, merge into runs and
    take each to the centre line of the wall it meets. Returns the walls and what was used, for the caller to report."""
    if primitive == "bar":  # a bar's width already says it is a wall (any block thickness): no weight threshold
        w, nets = 0.0, {}
    else:
        w, nets = wall_weight(lines, mm_per_pt, min_length_m=min_length_m, min_joints=min_joints, primitive=primitive)
    if w is None:
        return [], {"wall_weight": None, "networks": nets}
    bridged = bridge_lines([l for l in lines if round(l.w, 2) >= w - 1e-6], mm_per_pt, bridge_mm)  # a corner stub next to a window joins its wall first
    heavy = [l for l in bridged if l.length * mm_per_pt >= 600]  # then a face line is long; hatch and fixture strokes are not
    pieces = drop_centreline_halves(pair_walls(heavy, mm_per_pt, min_run_mm=350)) if primitive == "pair" else []
    from plan2cost.drawing.walls_cv import merge_runs

    pairs = to_walls(pieces, mm_per_pt)
    base = pairs + (bar_walls(lines, mm_per_pt, w, pairs, dominant_bar) if primitive == "bar" else [])
    walls = extend_to_centrelines([m for n in sorted({b.thickness_mm for b in base}) for m in merge_runs([b for b in base if b.thickness_mm == n], bridge_mm=bridge_mm)])
    walls = largest_cluster(walls)
    return walls, {"wall_weight": w, "pieces": len(pieces), "networks": nets}


def largest_cluster(walls: list[Wall], link_mm: float = 1500) -> list[Wall]:
    """The walls of the building: walls linked to one another (their extents come within `link_mm`), keeping the biggest group. A detail, a
    legend, a title block table or a second drawing on the same sheet forms its own group and is dropped."""
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

    def building_score(g: list[Wall]) -> float:
        """A building has walls both ways; a table or a title block is nearly all one direction. Score by the shorter direction's length."""
        h = sum(w.length_mm for w in g if w.orient == "h")
        v = sum(w.length_mm for w in g if w.orient == "v")
        return min(h, v) + 0.01 * (h + v)

    return max(groups.values(), key=building_score) if groups else []
