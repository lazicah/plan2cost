"""Strip footing runs from a structural foundation layout drawn as vectors.

Code measures, nothing is guessed: the grid bubbles and printed bay chains give the scale and the bay lengths; the dashed footing edges
drawn either side of a grid line show which bays carry a strip; the column bases (labelled BT.n, black column squares) are excavated
as pits, so the part of a run that lies inside a base is taken out of the trench. Strips that do not follow a grid line are not measured
here; the bases they serve are returned in `unmatched_bases` so the caller can flag them."""
import re
import subprocess
from dataclasses import dataclass, field

from plan2cost.drawing.dims import dimension_tokens
from plan2cost.drawing.grid import calibrate, find_grid, snap_bays
from plan2cost.kit.pdf import pdftoppm

PRESENT = 0.3  # share of a bay covered by dashed footing edges that counts as a strip
EDGE_OFFSET_PTS = (5.0, 12.0)  # the two edges lie this far either side of the grid line (a 675mm strip at about 1:36 per point)


@dataclass
class Base:
    type: str
    x: float
    y: float


@dataclass
class Run:
    line: str
    axis: str  # "x": runs along a horizontal grid line, "y": along a vertical one
    start: str
    end: str
    length_m: float
    bases_m: float
    basis: str  # "printed" when every bay matched a printed dimension, else "scaled"

    @property
    def net_m(self) -> float:
        return round(self.length_m - self.bases_m, 2)


@dataclass
class StripLayout:
    runs: list[Run] = field(default_factory=list)
    unmatched_bases: list[Base] = field(default_factory=list)
    floating_base_types: list[str] = field(default_factory=list)  # labelled bases with no column square (off the grid, e.g. porch)
    scale_basis: str = ""

    @property
    def gross_m(self) -> float:
        return round(sum(r.length_m for r in self.runs), 2)

    @property
    def net_m(self) -> float:
        return round(sum(r.net_m for r in self.runs), 2)


def vector_segments(pdf: str, page: int) -> tuple[list, list]:
    """Straight stroked segments and small filled squares, in page points. Needs a vector page; a raster page returns nothing."""
    exe = pdftoppm().replace("pdftoppm", "pdftocairo")
    svg = subprocess.run([exe, "-svg", "-f", str(page), "-l", str(page), pdf, "-"], capture_output=True, text=True).stdout
    segs, squares = [], []
    for m in re.finditer(r'<path ([^>]*?)d="([^"]*)" transform="matrix\(([^)]*)\)"', svg):
        attrs, d, t = m.groups()
        if re.search(r"[A-KN-Za-ln-z]", d.replace("Z", "").replace("M", "").replace("L", "")):
            continue
        a, _, _, dd, e, f = [float(x) for x in t.split(",")]
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", d)]
        pts = [(a * nums[i] + e, dd * nums[i + 1] + f) for i in range(0, len(nums) - 1, 2)]
        if 'fill="none"' in attrs:
            segs += list(zip(pts, pts[1:]))
        elif 'fill="rgb(0%, 0%, 0%)"' in attrs and 4 <= len(pts) <= 10:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            if 4 <= max(xs) - min(xs) <= 12 and 4 <= max(ys) - min(ys) <= 12:
                squares.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    return segs, squares


def _coverage(segs: list, pos: float, a: float, b: float, horizontal: bool) -> float:
    """Share of the span a..b along a grid line at `pos` covered by dashes lying 5 to 12 points off the line (both edges together)."""
    lo, hi = EDGE_OFFSET_PTS
    total = 0.0
    for p, q in segs:
        k, o = (1, 0) if horizontal else (0, 1)
        if abs(p[k] - q[k]) > 0.05 or not lo <= abs(p[k] - pos) <= hi:
            continue
        s, e = sorted((p[o], q[o]))
        total += max(0.0, min(e, b) - max(s, a))
    return total / (2 * (b - a)) if b > a else 0.0


def _bases(pdf: str, page: int, squares: list) -> tuple[list[Base], list[str]]:
    from subprocess import run

    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    html = run([exe, "-f", str(page), "-l", str(page), "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    labels = [((float(x0) + float(x1)) / 2, (float(y0) + float(y1)) / 2, n)
              for x0, y0, x1, y1, n in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">BT\.(\d)</word>', html)]
    pairs = sorted(((lx - sx) ** 2 + (ly - sy) ** 2, i, j) for i, (lx, ly, _) in enumerate(labels) for j, (sx, sy) in enumerate(squares))
    out, got_label, got_square = [], set(), set()
    for d2, i, j in pairs:  # each label takes its nearest free column square, within 35 points
        if d2 <= 35 ** 2 and i not in got_label and j not in got_square:
            got_label.add(i), got_square.add(j)
            out.append(Base(labels[i][2], squares[j][0], squares[j][1]))
    return out, [labels[i][2] for i in range(len(labels)) if i not in got_label]  # bases with a label but no column square on the grid


def measure_strips(pdf: str, page: int, base_size_m: dict[str, float]) -> StripLayout:
    """`base_size_m` maps a base type ("1".."5") to its plan size along a grid line (read from the base detail sheets)."""
    grid = find_grid(pdf, page)
    printed = [t.value for t in dimension_tokens(pdf, page)]
    grid = calibrate(grid, printed)
    if not grid.mm_per_pt:
        return StripLayout(scale_basis="no scale could be fitted to the printed dimensions")
    segs, squares = vector_segments(pdf, page)
    bases, floating = _bases(pdf, page, squares)
    layout = StripLayout(scale_basis=grid.scale_basis)
    used: set[int] = set()
    for axis, lines, crossing in (("x", grid.horizontals, grid.verticals), ("y", grid.verticals, grid.horizontals)):
        cross_pos = [c.pos_pts for c in crossing]
        bays = snap_bays([(a.label, b.label, (b.pos_pts - a.pos_pts) * grid.mm_per_pt) for a, b in zip(crossing, crossing[1:])], printed)
        for line in lines:
            present = [_coverage(segs, line.pos_pts, a, b, axis == "x") >= PRESENT for a, b in zip(cross_pos, cross_pos[1:])]
            i = 0
            while i < len(present):
                if not present[i]:
                    i += 1
                    continue
                j = i
                while j + 1 < len(present) and present[j + 1]:
                    j += 1
                span = bays[i:j + 1]
                a_pt, b_pt = cross_pos[i], cross_pos[j + 1]
                inside = 0.0
                for n, base in enumerate(bases):
                    along, across = (base.x, base.y) if axis == "x" else (base.y, base.x)
                    if abs(across - line.pos_pts) <= 8 and a_pt - 2 <= along <= b_pt + 2:
                        half = base_size_m.get(base.type, 0) * 1000 / grid.mm_per_pt / 2
                        inside += (min(along + half, b_pt) - max(along - half, a_pt)) * grid.mm_per_pt / 1000
                        used.add(n)
                layout.runs.append(Run(line.label, axis, span[0][0], span[-1][1], round(sum(s[2] for s in span) / 1000, 3), round(inside, 3),
                                       "printed" if all(s[3] == "printed" for s in span) else "scaled"))
                i = j + 1
    layout.unmatched_bases = [b for n, b in enumerate(bases) if n not in used]
    layout.floating_base_types = floating
    return layout
