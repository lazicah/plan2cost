"""Drawing scale from the drawing itself, with no grid and no stated scale needed.
A printed dimension sits between the two tick marks that end it on its dimension line, so (printed value) / (distance between those ticks in
points) is the scale in mm per point. Every dimension on the sheet votes; the right scale is the one most of them agree on."""
import math
import re
from collections import Counter

from plan2cost.drawing.dims import DimToken
from plan2cost.drawing.vector import Seg


def ticks(segs: list[Seg], min_pt: float = 8.0, max_pt: float = 18.0) -> list[tuple[float, float]]:
    """Centres of short slanted strokes: the tick marks (or arrowheads drawn as slashes) that end dimension lines."""
    out = []
    for s in segs:
        if min_pt <= s.length <= max_pt and abs(s.x0 - s.x1) > 0.3 and abs(s.y0 - s.y1) > 0.3:
            out.append(((s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2))
    return out


def votes(tokens: list[DimToken], tick_pts: list[tuple[float, float]], reach_pt: float = 12.0, min_value_mm: int = 300) -> list[float]:
    """For each printed value, the mm-per-point implied by the nearest tick on each side of it along its dimension line."""
    out = []
    for t in tokens:
        if t.value < min_value_mm:
            continue
        cx, cy = (t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2
        if t.vertical:  # rotated text: the dimension line is vertical, ticks lie at about the same x
            near = sorted(y for x, y in tick_pts if abs(x - cx) <= reach_pt)
            before, after = [y for y in near if y < cy], [y for y in near if y > cy]
        else:
            near = sorted(x for x, y in tick_pts if abs(y - cy) <= reach_pt)
            before, after = [x for x in near if x < cx], [x for x in near if x > cx]
        if before and after:
            length = after[0] - before[-1]
            if length > 8:
                out.append(t.value / length)
    return out


def line_votes(tokens: list[DimToken], lines, min_value_mm: int = 600, min_len_pt: float = 10.0) -> list[float]:
    """Independent of how dimension ends are drawn: for each printed value, the nearest line on each side of it that crosses its row (an
    extension line, or the wall face a room dimension runs between). Value over that spacing is the scale it implies."""
    out = []
    for t in tokens:
        if t.value < min_value_mm:
            continue
        cx, cy = (t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2
        # a horizontal chain reads across: lines are vertical; rotated text reads down: lines are horizontal
        orient, along, lo, hi = ("v", cx, t.x0, t.x1) if not t.vertical else ("h", cy, t.y0, t.y1)
        across = cy if not t.vertical else cx
        cand = [l for l in lines if l.orient == orient and l.length >= min_len_pt and l.a - 3 <= across <= l.b + 3]
        left = [l.pos for l in cand if l.pos < lo - 1]
        right = [l.pos for l in cand if l.pos > hi + 1]
        if left and right:
            out.append(t.value / (min(right) - max(left)))
    return out


def _mode(v: list[float], bin_pct: float = 0.012) -> dict:
    if len(v) < 4:
        return {"mm_per_pt": None, "votes": len(v), "agree": 0.0, "dominance": 0.0}
    key = lambda x: int(math.log(x) / math.log(1 + bin_pct))
    counts = Counter(key(x) for x in v)
    best = counts.most_common(1)[0][0]
    near = sorted(x for x in v if abs(key(x) - best) <= 1)
    rest = [c for k, c in counts.items() if abs(k - best) > 2]
    runner = max(rest, default=0)
    return {"mm_per_pt": round(near[len(near) // 2], 3), "votes": len(v), "agree": round(len(near) / len(v), 2), "dominance": round(len(near) / max(runner, 1), 1)}


def stated_scale(text: str) -> int | None:
    """The scale denominator the title block states ("SCALE 1:100"), from the page's text layer."""
    flat = re.sub(r"\s+", " ", text)
    m = re.search(r"scale\W{0,12}1\s*[:/]\s*(\d{2,3})\b", flat, re.I)
    if not m:
        found = [int(x) for x in re.findall(r"\b1\s*:\s*(\d{2,3})\b", flat) if int(x) in (20, 25, 50, 75, 100, 125, 150, 200, 250, 500)]
        return Counter(found).most_common(1)[0][0] if found else None
    return int(m.group(1))


def within_stated(votes_: list[float], denominator: int | None) -> list[float]:
    """A sheet is plotted near its stated scale, smaller or larger (an A4 drawing sent out on A3 is 41 percent bigger): keep votes between 55
    and 160 percent of it. A loose bound; it only removes values that cannot be right."""
    if not denominator:
        return votes_
    s0 = denominator * 25.4 / 72
    return [v for v in votes_ if 0.55 * s0 <= v <= 1.6 * s0]


def fit_scale(tokens: list[DimToken], segs: list[Seg], lines=None, denominator: int | None = None) -> dict:
    """Mode of the votes (tick marks when the drawing has them, nearest lines otherwise), bounded by the stated scale when there is one.
    `agree` is the share of votes in the winning bin."""
    best = _mode(within_stated(votes(tokens, ticks(segs)), denominator))
    if lines is not None:
        alt = _mode(within_stated(line_votes(tokens, lines), denominator))
        if alt["mm_per_pt"] and (not best["mm_per_pt"] or alt["agree"] * alt["votes"] > best["agree"] * best["votes"]):
            best = alt
    return best


STANDARD_THICKNESS_MM = (100, 150, 225, 230)


def modal_wall_gap_pt(lines, min_len_pt: float = 20.0) -> tuple[float, int] | None:
    """The most common spacing between two long parallel lines of the heaviest weight that forms pairs: the wall thickness on paper."""
    from collections import defaultdict

    gaps: dict[float, Counter] = defaultdict(Counter)
    for w in {round(l.w, 2) for l in lines}:
        cls = sorted((l for l in lines if round(l.w, 2) == w and l.length >= min_len_pt), key=lambda l: (l.orient, l.pos))
        for i, a in enumerate(cls):
            for b in cls[i + 1:]:
                if b.orient != a.orient or b.pos - a.pos > 14:
                    break
                if b.pos - a.pos > 1.5 and min(a.b, b.b) - max(a.a, b.a) > min_len_pt:
                    gaps[w][round((b.pos - a.pos) / 0.25) * 0.25] += 1
    best = None
    for w, c in gaps.items():
        if sum(c.values()) >= 10 and (best is None or w > best[0]):  # the heaviest weight with a real number of pairs
            best = (w, c)
    if not best:
        return None
    g, n = best[1].most_common(1)[0]
    return g, n


def scale_from_wall_thickness(lines, stated_denominator: float | None = None) -> dict:
    """Weakest source, used when no printed dimension can be read. The wall thickness on paper is one of the standard block thicknesses
    (225, 230, 150, 100 mm); the stated scale (1:100 and so on, read from the title block) picks which, and a sheet plotted a little smaller than
    stated (up to about 12 percent) still fits. Without a stated scale only the 225 reading is offered, as a guess."""
    m = modal_wall_gap_pt(lines)
    if not m:
        return {"mm_per_pt": None}
    gap, n = m
    cands = {t: t / gap for t in STANDARD_THICKNESS_MM}
    if stated_denominator:
        s0 = stated_denominator * 25.4 / 72
        fit = {t: s for t, s in cands.items() if 0.86 * s0 <= s <= 1.03 * s0}
        if fit:
            t, s = min(fit.items(), key=lambda kv: abs(kv[1] - s0))
            return {"mm_per_pt": round(s, 3), "wall_mm": t, "gap_pt": gap, "pairs": n, "basis": f"wall thickness {t}mm on paper with stated scale 1:{int(stated_denominator)}"}
    return {"mm_per_pt": round(cands[225], 3), "wall_mm": 225, "gap_pt": gap, "pairs": n, "basis": "assumed 225mm wall thickness (no stated scale): a guess"}
