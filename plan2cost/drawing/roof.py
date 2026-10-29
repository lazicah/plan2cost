"""The roof from a vector roof plan: eaves outline, ridges, hips and valleys, and the plan area under the roof. The heaviest line weight on the sheet is the roof
skeleton. Scale comes from the printed overall dimensions matching the outline on both axes (the stated scale is only a loose bound). Code measures; the pitch
comes from the printed levels on the section (takeoff/roof.py), not from the plan."""
import math
from collections import defaultdict
from dataclasses import dataclass, field

import cv2
import numpy as np

from plan2cost.drawing.dims import chains, dimension_tokens
from plan2cost.drawing.scale import stated_scale
from plan2cost.drawing.vector import Seg, read_page
from plan2cost.kit.pdf import page_text

PX = 4  # raster pixels per point when filling the outline
DUP_PT = 7.0  # parallel lines closer than this are one drawn line (a doubled edge, a valley strip)
ANGLE_TOL = 3.0


@dataclass
class Roof:
    mm_per_pt: float
    scale_basis: str
    plan_area_m2: float
    eaves_m: float
    ridges_m: float
    diagonals_m: float
    hips_m: float
    valleys_m: float
    unsorted_m: float  # hips or valleys that could not be told apart
    main_ridge_m: float
    half_span_mm: float | None  # eaves to the main ridge, from the plan
    diagonal_angles_ok: bool
    warnings: list = field(default_factory=list)
    confidence: str = "medium"
    lines: list = field(default_factory=list)  # (x0, y0, x1, y1, kind) in page points, kind: eaves, ridge, hip, valley, unsorted, for the annotated plan


def skeleton(segs: list[Seg]) -> list[Seg]:
    """The roof's lines: the heaviest stroke weight that has real length on the sheet."""
    by_w: dict = defaultdict(list)
    for s in segs:
        if not s.dashed and not s.filled and s.w > 0:
            by_w[round(s.w, 2)].append(s)
    for w in sorted(by_w, reverse=True):
        if len(by_w[w]) >= 8 and sum(s.length for s in by_w[w]) >= 400:
            return by_w[w]
    return []


def _angle(s: Seg) -> float:
    return math.degrees(math.atan2(s.y1 - s.y0, s.x1 - s.x0)) % 180


def dedupe(segs: list[Seg]) -> list[Seg]:
    """One line per drawn line: a doubled edge (two parallel strokes a few points apart) counts once."""
    kept: list[Seg] = []
    for s in sorted(segs, key=lambda s: -s.length):
        a = _angle(s)
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        dup = False
        for k in kept:
            da = abs(a - _angle(k))
            if min(da, 180 - da) > 2:
                continue
            off = abs((s.x0 - k.x0) * -uy + (s.y0 - k.y0) * ux)  # perpendicular distance of s from the line of k
            t0, t1 = sorted(((s.x0 - k.x0) * ux + (s.y0 - k.y0) * uy, (s.x1 - k.x0) * ux + (s.y1 - k.y0) * uy))
            over = min(t1, k.length) - max(t0, 0)
            if off <= DUP_PT and over >= 0.5 * s.length:
                dup = True
                break
        if not dup:
            kept.append(s)
    return kept


def fit_extent_scale(bx_pt: float, by_pt: float, values_mm: list[float], stated: float | None, tol: float = 0.015) -> tuple[float | None, str]:
    """mm per point from the outline's two extents against printed overall dimensions: a scale counts only if some printed value fits each axis at the same
    scale (to 1.5%). Both axes agreeing is what makes it trustworthy; a single dimension is not enough."""
    nominal = stated * 25.4 / 72 if stated else None
    best = None
    for a in values_mm:
        s = a / bx_pt
        if nominal and not 0.55 * nominal <= s <= 1.6 * nominal:
            continue
        for b in values_mm:
            if abs(b / by_pt - s) / s <= tol and (best is None or abs(b / by_pt - s) < best[2]):
                best = (s, (a, b), abs(b / by_pt - s))
    if not best:
        return None, "no printed overall dimension fits the roof outline on both axes"
    s, (a, b), err = best
    return (a / bx_pt + b / by_pt) / 2, f"roof outline matches printed overall dimensions {a:g} x {b:g} mm (axes agree to {err / s * 100:.2f}%)"


def measure_roof(pdf: str, page: int) -> Roof | None:
    pg = read_page(pdf, page)
    sk = skeleton(pg.segs)
    if not sk:
        return None
    xs = [v for s in sk for v in (s.x0, s.x1)]
    ys = [v for s in sk for v in (s.y0, s.y1)]
    x0, y0, bx, by = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    # the filled outline: draw the skeleton, close small gaps, flood the outside, what is left is under the roof
    pad = 6
    mask = np.zeros((int((by + 2 * pad) * PX), int((bx + 2 * pad) * PX)), np.uint8)
    for s in sk:
        cv2.line(mask, (int((s.x0 - x0 + pad) * PX), int((s.y0 - y0 + pad) * PX)), (int((s.x1 - x0 + pad) * PX), int((s.y1 - y0 + pad) * PX)), 255, 2)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    flood = mask.copy()
    ff = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8)
    cv2.floodFill(flood, ff, (0, 0), 255)
    outside = flood == 255
    outside &= mask == 0
    area_pt2 = (outside.size - int(outside.sum())) / (PX * PX)

    toks = dimension_tokens(pdf, page)
    values = [float(t.value) for t in toks if t.value >= 2000]
    for ch in chains(toks, min_tokens=3):
        values.append(float(sum(t.value for t in ch)))
    scale, basis = fit_extent_scale(bx, by, sorted(set(values)), stated_scale(page_text(pdf, page)))
    warnings = []
    if scale is None:
        return Roof(0.0, basis, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, False, ["the scale of the roof plan could not be fixed: ask the user for one overall dimension"], "low")

    def is_outside(x: float, y: float) -> bool:
        px, py = int((x - x0 + pad) * PX), int((y - y0 + pad) * PX)
        return not (0 <= py < outside.shape[0] and 0 <= px < outside.shape[1]) or bool(outside[py, px])

    edge, interior = [], []
    for s in sk:
        if s.length < 3:
            continue
        mx, my = (s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2
        nx, ny = -(s.y1 - s.y0) / s.length, (s.x1 - s.x0) / s.length
        sides = [is_outside(mx + nx * d, my + ny * d) for d in (3.0, -3.0)]
        (edge if sum(sides) == 1 else interior if sum(sides) == 0 else []).append(s)
    edge, interior = dedupe(edge), dedupe(interior)
    straight = lambda s: min(_angle(s) % 90, 90 - _angle(s) % 90) < ANGLE_TOL
    diag = [s for s in interior if not straight(s)]
    ridges = [s for s in interior if straight(s)]
    ok = all(abs(_angle(s) % 90 - 45) <= ANGLE_TOL for s in diag)
    if not ok:
        warnings.append("some hips or valleys are not at 45 degrees in plan, so the planes may not share one pitch")
    m = scale / 1000  # metres per point
    # hips and valleys: each plane slopes down toward the eave it can reach in a straight axis line without crossing another roof line. A diagonal is a hip
    # when both planes beside it slope away from it, a valley when both slope toward it; anything else stays unclassified.
    planes = _planes(mask, outside, sk, edge, x0, y0, pad, is_outside)
    hips = valleys = other = 0.0
    drawn = [(s.x0, s.y0, s.x1, s.y1, "eaves") for s in edge] + [(s.x0, s.y0, s.x1, s.y1, "ridge") for s in ridges]
    for s in diag:
        kind = _hip_or_valley(s, planes, x0, y0, pad)
        drawn.append((s.x0, s.y0, s.x1, s.y1, kind if kind != "unknown" else "unsorted"))
        if kind == "hip":
            hips += s.length
        elif kind == "valley":
            valleys += s.length
        else:
            other += s.length
    main = max(ridges, key=lambda s: s.length, default=None)
    half = None
    if main:
        ux, uy = (main.x1 - main.x0) / main.length, (main.y1 - main.y0) / main.length
        offs = []
        for e in edge:
            da = abs(_angle(e) - _angle(main))
            if min(da, 180 - da) >= 2:
                continue
            t0, t1 = sorted(((e.x0 - main.x0) * ux + (e.y0 - main.y0) * uy, (e.x1 - main.x0) * ux + (e.y1 - main.y0) * uy))
            if min(t1, main.length) - max(t0, 0) > 0.5 * main.length:  # an eave that runs alongside the ridge for most of its length
                offs.append((e.x0 - main.x0) * -uy + (e.y0 - main.y0) * ux)
        left, right = [-o for o in offs if o < 0], [o for o in offs if o > 0]
        if left and right:
            a, b = min(left) * scale, min(right) * scale
            half = round((a + b) / 2, 0)
            if abs(a - b) > 0.1 * max(a, b):
                warnings.append(f"the main ridge is not centred between its eaves ({a:.0f} and {b:.0f} mm): the pitch is read from the average")
    if other:
        warnings.append(f"{other * m:.1f} m of hips or valleys could not be told apart; they are measured as their own line")
    reach = {k: sum(v.values()) for k, v in planes[2].items()}
    sizes = np.bincount(planes[0].ravel(), minlength=planes[3]) / (PX * PX)  # plane areas in square points
    weak = [k for k in range(1, planes[3]) if sizes[k] * scale * scale / 1e6 >= 1.0 and reach.get(k, 0) < 10]
    if weak:
        warnings.append(f"{len(weak)} roof plane(s) do not reach an eave of their own (a raised or sunk area such as a central diamond), so the hips and valleys around them are uncertain")
    return Roof(scale, basis, round(area_pt2 * scale * scale / 1e6, 2), round(sum(s.length for s in edge) * m, 2), round(sum(s.length for s in ridges) * m, 2),
                round(sum(s.length for s in diag) * m, 2), round(hips * m, 2), round(valleys * m, 2), round(other * m, 2), round(main.length * m, 2) if main else 0.0, half, ok, warnings,
                "high" if ok and not warnings else "medium", drawn)


def _planes(mask: np.ndarray, outside: np.ndarray, sk: list[Seg], edge: list[Seg], x0: float, y0: float, pad: float, is_outside) -> tuple:
    """The roof planes: what is inside the outline once the drawn roof lines are cut out. Each plane slopes down toward the eave it touches for the most
    length, so its downslope direction is that eave's outward normal."""
    lines = np.zeros_like(mask)
    for s in sk:
        cv2.line(lines, (int((s.x0 - x0 + pad) * PX), int((s.y0 - y0 + pad) * PX)), (int((s.x1 - x0 + pad) * PX), int((s.y1 - y0 + pad) * PX)), 255, 3)
    free = ((~outside) & (lines == 0)).astype(np.uint8)
    n, label = cv2.connectedComponents(free, connectivity=4)
    contact: dict = defaultdict(lambda: defaultdict(float))
    for e in edge:
        nx, ny = -(e.y1 - e.y0) / e.length, (e.x1 - e.x0) / e.length
        if not is_outside(e.x0 + (e.x1 - e.x0) / 2 + nx * 3, e.y0 + (e.y1 - e.y0) / 2 + ny * 3):
            nx, ny = -nx, -ny  # make it point outward
        for f in np.linspace(0.1, 0.9, 9):
            px, py = e.x0 + (e.x1 - e.x0) * f - nx * 4, e.y0 + (e.y1 - e.y0) * f - ny * 4  # just inside the eave
            ix, iy = int((px - x0 + pad) * PX), int((py - y0 + pad) * PX)
            if 0 <= iy < label.shape[0] and 0 <= ix < label.shape[1] and label[iy, ix] > 0:
                contact[int(label[iy, ix])][(round(nx), round(ny))] += e.length / 9
    down = {k: max(v, key=v.get) for k, v in contact.items()}
    return label, down, contact, n


def _hip_or_valley(s: Seg, planes: tuple, x0: float, y0: float, pad: float) -> str:
    """A diagonal is a hip when both planes beside it slope away from it, a valley when both slope toward it."""
    label, down = planes[0], planes[1]
    nx, ny = -(s.y1 - s.y0) / s.length, (s.x1 - s.x0) / s.length
    mx, my = (s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2
    votes = []
    for sign in (1, -1):
        d = None
        for off in (9, 12, 16):
            ix, iy = int((mx + sign * nx * off - x0 + pad) * PX), int((my + sign * ny * off - y0 + pad) * PX)
            lab = int(label[iy, ix]) if 0 <= iy < label.shape[0] and 0 <= ix < label.shape[1] else 0
            if lab in down:
                d = down[lab]
                break
        if d is None:
            return "unknown"
        votes.append((d[0] * nx + d[1] * ny) * sign)  # > 0: this plane slopes away from the line
    return "hip" if all(v > 0.3 for v in votes) else "valley" if all(v < -0.3 for v in votes) else "unknown"


COLOURS = {"eaves": (40, 40, 220), "ridge": (200, 90, 20), "hip": (60, 150, 60), "valley": (200, 0, 200), "unsorted": (0, 0, 0)}  # BGR


def draw_roof(pdf: str, page: int, roof: Roof, out_path: str, dpi: int = 100) -> str:
    """The roof plan with what was measured drawn on it: eaves red, ridges blue, hips green, valleys magenta, unclassified black."""
    import tempfile

    from plan2cost.kit.pdf import render_pages

    img = cv2.imread(render_pages(pdf, [page], tempfile.mkdtemp(), dpi=dpi)[0])
    k = dpi / 72
    for x0_, y0_, x1_, y1_, kind in roof.lines:
        cv2.line(img, (int(x0_ * k), int(y0_ * k)), (int(x1_ * k), int(y1_ * k)), COLOURS[kind], 4)
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), (255, 255, 255), -1)
    cv2.putText(img, "roof plan: red eaves, blue ridges, green hips, magenta valleys, black not told apart", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1)
    cv2.imwrite(out_path, img)
    return out_path
