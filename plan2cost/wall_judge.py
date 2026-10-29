"""Candidate walls judged by the model. Geometry proposes (every pair of same-weight parallel lines at a block-thickness spacing, whatever
the weight: no style is assumed); the Meta vision model looks at the plan with every candidate numbered and says which are walls and what the
others are (grid line, dimension, window frame, stair, furniture...). Code then measures the ones kept. The model never gives a length."""
import tempfile
from dataclasses import dataclass

import cv2

from plan2cost.pdf import render_pages
from plan2cost.vector_walls import bridge_lines, pair_walls, to_walls
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


def overlay(pdf: str, page: int, cands: list[Cand], mm_per_pt: float, out_dir: str | None = None, dpi: int = 130) -> str:
    """The page with each candidate drawn and numbered, cropped to where the candidates are. Returns the image path."""
    out_dir = out_dir or tempfile.mkdtemp()
    img = cv2.imread(render_pages(pdf, [page], out_dir, dpi=dpi)[0])
    k = dpi / 72
    xs, ys = [], []
    for c in cands:
        w = c.wall
        cp, a, b = w.centre_mm / mm_per_pt * k, w.start_mm / mm_per_pt * k, w.end_mm / mm_per_pt * k
        p1, p2 = ((int(a), int(cp)), (int(b), int(cp))) if w.orient == "h" else ((int(cp), int(a)), (int(cp), int(b)))
        col = COLOURS[c.id % len(COLOURS)]
        cv2.line(img, p1, p2, col, 4)
        mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
        off = 14 if c.id % 2 else -14
        pos = (mid[0] + (off if w.orient == "v" else 0), mid[1] + (off if w.orient == "h" else 0))
        label = str(c.id)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img, (pos[0] - 2, pos[1] - th - 3), (pos[0] + tw + 2, pos[1] + 3), (255, 255, 255), -1)
        cv2.putText(img, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        xs += [p1[0], p2[0]]
        ys += [p1[1], p2[1]]
    m = int(150 * k / 2)
    x0, y0, x1, y1 = max(min(xs) - m, 0), max(min(ys) - m, 0), min(max(xs) + m, img.shape[1]), min(max(ys) + m, img.shape[0])
    path = f"{out_dir}/judge_p{page}.jpg"
    cv2.imwrite(path, img[y0:y1, x0:x1])
    return path


def judge(image_path: str) -> dict:
    from plan2cost.client import image_part
    from plan2cost.document import _chat

    return _chat([{"type": "text", "text": JUDGE_PROMPT}, image_part(image_path)])
