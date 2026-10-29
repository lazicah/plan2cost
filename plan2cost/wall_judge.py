"""Candidate walls judged by the model. Geometry proposes (every pair of same-weight parallel lines at a block-thickness spacing, whatever
the weight: no style is assumed); the Meta vision model looks at the plan with every candidate numbered and says which are walls and what the
others are (grid line, dimension, window frame, stair, furniture...). Code then measures the ones kept. The model never gives a length."""
import tempfile
from dataclasses import dataclass

import cv2

from plan2cost.pdf import render_pages
from plan2cost.vector_walls import bridge_lines, drop_centreline_halves, pair_walls, to_walls
from plan2cost.walls_cv import Wall, _merge

JUDGE_PROMPT = """This is part of a floor plan from a building drawing set. Coloured numbered segments mark CANDIDATE wall centre-lines found by
software. For each number say whether it is a WALL (a cut masonry or concrete wall, external or internal, including a wall that is interrupted
by doors or windows) or something else. Things that are not walls: grid lines, dimension and extension lines, window or door frames and sills,
stair treads, furniture and fixtures, hatching, balcony or terrace rails, annotation, borders, landscaping.
Judge only from what the drawing shows. A number on a long line that runs outside the building, or through rooms with no wall beside it, is
probably a grid or dimension line.
Return only JSON: {"walls": [numbers], "not_walls": {"number": "short reason"}, "unsure": [numbers]}"""

COLOURS = [(0, 0, 255), (255, 0, 0), (0, 150, 0), (200, 0, 200), (0, 140, 255), (160, 100, 0)]  # BGR


@dataclass
class Cand:
    id: int
    wall: Wall
    weight: float


def candidates(lines, mm_per_pt: float, bridge_mm: float = 3600) -> list[Cand]:
    """Wall-like runs from every line weight that forms pairs; nothing is assumed about which weight the walls use."""
    found: list[Cand] = []
    for w in sorted({round(l.w, 2) for l in lines}, reverse=True):
        cls = [l for l in lines if round(l.w, 2) == w and l.length * mm_per_pt >= 300]
        if len(cls) < 4:
            continue
        pieces = drop_centreline_halves(pair_walls(bridge_lines(cls, mm_per_pt, bridge_mm), mm_per_pt, min_run_mm=350))
        base = to_walls(pieces, mm_per_pt)
        merged = [m for n in sorted({b.thickness_mm for b in base}) for m in _merge([b for b in base if b.thickness_mm == n], bridge_mm=bridge_mm)]
        found += [Cand(0, m, w) for m in merged if m.length_mm >= 500]
    out: list[Cand] = []
    for c in sorted(found, key=lambda c: -c.weight):  # a run found at two weights is one candidate: keep the heavier
        if not any(o.wall.orient == c.wall.orient and abs(o.wall.centre_mm - c.wall.centre_mm) <= 80 and
                   min(o.wall.end_mm, c.wall.end_mm) - max(o.wall.start_mm, c.wall.start_mm) >= 0.6 * c.wall.length_mm for o in out):
            out.append(c)
    for i, c in enumerate(out, 1):
        c.id = i
    return out


def building_candidates(lines, mm_per_pt: float, bridge_mm: float = 3600) -> list[Cand]:
    """Candidates from every weight, kept to the building: the connected group with walls both ways (a title block table, a legend or a
    detail forms a different group)."""
    from plan2cost.vector_walls import largest_cluster

    cs = candidates(lines, mm_per_pt, bridge_mm)
    keep = {id(w) for w in largest_cluster([c.wall for c in cs])}
    out = [c for c in cs if id(c.wall) in keep]
    for i, c in enumerate(out, 1):
        c.id = i
    return out


def tiles(cands: list[Cand], max_per_tile: int = 45) -> list[list[Cand]]:
    """Split the candidates into spatial groups of at most `max_per_tile` so each image stays readable."""
    def centre(c: Cand) -> tuple[float, float]:
        w = c.wall
        mid = (w.start_mm + w.end_mm) / 2
        return (mid, w.centre_mm) if w.orient == "h" else (w.centre_mm, mid)

    def split(group: list[Cand]) -> list[list[Cand]]:
        if len(group) <= max_per_tile:
            return [group]
        xs, ys = [centre(c)[0] for c in group], [centre(c)[1] for c in group]
        axis = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
        group = sorted(group, key=lambda c: centre(c)[axis])
        half = len(group) // 2
        return split(group[:half]) + split(group[half:])

    return split(cands)


def overlay(pdf: str, page: int, cands: list[Cand], mm_per_pt: float, out_dir: str | None = None, dpi: int = 150, margin_m: float = 2.5, name: str = "judge") -> str:
    """The page cropped to where the given candidates are, each drawn thin and numbered beside it so the hatching stays visible."""
    out_dir = out_dir or tempfile.mkdtemp()
    img = cv2.imread(render_pages(pdf, [page], out_dir, dpi=dpi)[0])
    k = dpi / 72
    xs, ys = [], []
    for c in cands:
        w = c.wall
        cp, a, b = w.centre_mm / mm_per_pt * k, w.start_mm / mm_per_pt * k, w.end_mm / mm_per_pt * k
        p1, p2 = ((int(a), int(cp)), (int(b), int(cp))) if w.orient == "h" else ((int(cp), int(a)), (int(cp), int(b)))
        col = COLOURS[c.id % len(COLOURS)]
        cv2.line(img, p1, p2, col, 3)
        mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
        off = 16 if c.id % 2 else -16
        pos = (mid[0] + (off if w.orient == "v" else 0), mid[1] + (off if w.orient == "h" else 0))
        label = str(c.id)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (pos[0] - 2, pos[1] - th - 3), (pos[0] + tw + 2, pos[1] + 3), (255, 255, 255), -1)
        cv2.putText(img, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
        xs += [p1[0], p2[0]]
        ys += [p1[1], p2[1]]
    m = int(margin_m * 1000 / mm_per_pt * k)
    x0, y0, x1, y1 = max(min(xs) - m, 0), max(min(ys) - m, 0), min(max(xs) + m, img.shape[1]), min(max(ys) + m, img.shape[0])
    path = f"{out_dir}/{name}_p{page}.jpg"
    cv2.imwrite(path, img[y0:y1, x0:x1])
    return path


def judge(image_path: str) -> dict:
    from plan2cost.client import image_part
    from plan2cost.document import _chat

    return _chat([{"type": "text", "text": JUDGE_PROMPT}, image_part(image_path)])


def judge_page(pdf: str, page: int, cands: list[Cand], mm_per_pt: float, out_dir: str | None = None, workers: int = 4) -> dict:
    """Judge every candidate, tile by tile. Returns the ids kept as walls, the ids judged otherwise with the reason, and the ones unsure."""
    from concurrent.futures import ThreadPoolExecutor

    out_dir = out_dir or tempfile.mkdtemp()
    groups = tiles(cands)
    paths = [overlay(pdf, page, g, mm_per_pt, out_dir, name=f"tile{i}") for i, g in enumerate(groups)]
    with ThreadPoolExecutor(workers) as ex:
        verdicts = list(ex.map(judge, paths))
    walls, other, unsure = set(), {}, set()
    for g, v in zip(groups, verdicts):
        ids = {c.id for c in g}
        walls |= {int(x) for x in v.get("walls", []) if int(x) in ids}
        unsure |= {int(x) for x in v.get("unsure", []) if int(x) in ids}
        other.update({int(k): r for k, r in v.get("not_walls", {}).items() if int(k) in ids})
    return {"walls": walls, "not_walls": other, "unsure": unsure, "tiles": len(groups)}


def overlay_image(img, cands: list[Cand], mm_per_px: float, out_path: str, margin_m: float = 2.5):
    """The same numbered overlay for a raster plan: candidates are in millimetres and the image is in pixels."""
    img = img.copy()
    xs, ys = [], []
    for c in cands:
        w = c.wall
        cp, a, b = w.centre_mm / mm_per_px, w.start_mm / mm_per_px, w.end_mm / mm_per_px
        p1, p2 = ((int(a), int(cp)), (int(b), int(cp))) if w.orient == "h" else ((int(cp), int(a)), (int(cp), int(b)))
        col = COLOURS[c.id % len(COLOURS)]
        cv2.line(img, p1, p2, col, 6)
        mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
        off = 26 if c.id % 2 else -26
        pos = (mid[0] + (off if w.orient == "v" else 0), mid[1] + (off if w.orient == "h" else 0))
        label = str(c.id)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
        cv2.rectangle(img, (pos[0] - 3, pos[1] - th - 5), (pos[0] + tw + 3, pos[1] + 5), (255, 255, 255), -1)
        cv2.putText(img, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 1.4, col, 3)
        xs += [p1[0], p2[0]]
        ys += [p1[1], p2[1]]
    m = int(margin_m * 1000 / mm_per_px)
    x0, y0, x1, y1 = max(min(xs) - m, 0), max(min(ys) - m, 0), min(max(xs) + m, img.shape[1]), min(max(ys) + m, img.shape[0])
    crop = img[y0:y1, x0:x1]
    k = 2200 / max(crop.shape[:2])
    if k < 1:
        crop = cv2.resize(crop, (int(crop.shape[1] * k), int(crop.shape[0] * k)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out_path, crop)
    return out_path


def judge_image_walls(img, walls: list[Wall], mm_per_px: float, max_per_tile: int = 45, workers: int = 4) -> dict:
    """Judge the walls found on a raster plan. Returns the indexes (into `walls`) kept as walls, rejected with a reason, and unsure."""
    from concurrent.futures import ThreadPoolExecutor

    cands = [Cand(i + 1, w, 0.0) for i, w in enumerate(walls)]
    groups = tiles(cands, max_per_tile)
    out_dir = tempfile.mkdtemp()
    paths = [overlay_image(img, g, mm_per_px, f"{out_dir}/tile{i}.jpg") for i, g in enumerate(groups)]
    with ThreadPoolExecutor(workers) as ex:
        verdicts = list(ex.map(judge, paths))
    keep, other, unsure = set(), {}, set()
    for g, v in zip(groups, verdicts):
        ids = {c.id for c in g}
        keep |= {int(x) - 1 for x in v.get("walls", []) if int(x) in ids}
        unsure |= {int(x) - 1 for x in v.get("unsure", []) if int(x) in ids}
        other.update({int(k) - 1: r for k, r in v.get("not_walls", {}).items() if int(k) in ids})
    return {"keep": keep, "not_walls": other, "unsure": unsure, "tiles": len(groups)}
