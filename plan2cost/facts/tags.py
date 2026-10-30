"""The opening tags printed on a plan (W1, W2, D1, D2, ...), read by the model with a rough place on the sheet. Each tag marks exactly one opening, so the tags are evidence that
does not depend on the wall reading: an opening with no tag nearby on a drawing that tags its openings is probably not one, and a tag with no opening near it is one that was missed.
The model only reads the tags and where they are; code matches them to walls, measures the opening and decides."""
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

import cv2

TAG = re.compile(r"^[A-Z]{1,3}\d{1,2}[A-Za-z]?$")
OVERVIEW = """Does this floor plan label its windows and doors with printed tags such as W1, W2, D1, D2 (often inside small circles or boxes beside the opening)?
Return only JSON: {"tagged": true or false, "examples": ["W1", "D2"]}"""
TILE = """This is part of a floor plan. List every window or door tag printed in it (labels like W1, W2, W3, D1, D2, SD1, often inside a small circle or box beside the opening). Ignore room names,
dimensions, grid bubbles with only a number or a single letter, and notes. For each tag give the text exactly as printed and the centre of the tag as a fraction of this picture's width and height
(x from the left, y from the top, each 0 to 1). If a tag is cut off by the edge of the picture, leave it out. Judge only what you can see.
Return only JSON: {"tags": [{"tag": "W3", "x": 0.42, "y": 0.18}]}"""


def _save(img, path: str) -> str:
    cv2.imwrite(path, img)
    return path


def tiles(h: int, w: int, rows: int = 2, cols: int = 2, overlap: float = 0.10) -> list[tuple[int, int, int, int]]:
    """Overlapping tiles (x0, y0, x1, y1) in pixels covering the page, so a tag cut by one edge is whole in the next tile."""
    th, tw = h / rows, w / cols
    return [(max(int(c * tw - overlap * tw), 0), max(int(r * th - overlap * th), 0), min(int((c + 1) * tw + overlap * tw), w), min(int((r + 1) * th + overlap * th), h))
            for r in range(rows) for c in range(cols)]


def to_sheet_mm(tile: tuple, fx: float, fy: float, scale: float) -> tuple[float, float]:
    """A place given as fractions of a tile, as millimetres on the sheet (scale is pixels to a millimetre)."""
    x0, y0, x1, y1 = tile
    return (x0 + fx * (x1 - x0)) / scale, (y0 + fy * (y1 - y0)) / scale


def clean(raw: list, tile: tuple, scale: float) -> list[tuple[str, float, float]]:
    """Keep well-formed tags with a place on the tile."""
    out = []
    for t in raw or []:
        try:
            tag, fx, fy = str(t["tag"]).strip().upper(), float(t["x"]), float(t["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if TAG.match(tag) and 0 <= fx <= 1 and 0 <= fy <= 1:
            out.append((tag, *to_sheet_mm(tile, fx, fy, scale)))
    return out


def dedupe(tags: list[tuple[str, float, float]], radius_mm: float = 1500) -> list[tuple[str, float, float]]:
    """The same tag seen in two overlapping tiles is one tag."""
    out: list = []
    for t in tags:
        if not any(t[0] == u[0] and ((t[1] - u[1]) ** 2 + (t[2] - u[2]) ** 2) ** 0.5 <= radius_mm for u in out):
            out.append(t)
    return out


def read_tags(img, scale: float, ask=None, workers: int = 6) -> list[tuple[str, float, float]]:
    """Tags on the plan with their place in sheet millimetres. A first look at the whole page says whether the plan tags its openings at all, so plans without tags cost one call."""
    from plan2cost.kit.client import chat_json, image_part

    ask = ask or (lambda prompt, path: chat_json([{"type": "text", "text": prompt}, image_part(path)]))
    h, w = img.shape[:2]
    k = min(1600 / max(h, w), 1.0)
    folder = tempfile.mkdtemp()
    over = ask(OVERVIEW, _save(cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), f"{folder}/overview.jpg"))
    if not over.get("tagged"):
        return []
    ts = tiles(h, w)

    def one(i):
        try:
            crop = img[ts[i][1]:ts[i][3], ts[i][0]:ts[i][2]]
            small = cv2.resize(crop, None, fx=min(1300 / max(crop.shape[:2]), 1.0), fy=min(1300 / max(crop.shape[:2]), 1.0), interpolation=cv2.INTER_AREA)  # tags stay legible and the upload stays small
            return clean(ask(TILE, _save(small, f"{folder}/tile{i}.jpg")).get("tags"), ts[i], scale)
        except Exception:  # a tile that could not be read leaves its tags unread; the others still count
            return []
    with ThreadPoolExecutor(workers) as ex:
        return dedupe([t for part in ex.map(one, range(len(ts))) for t in part])
