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


LOOK = """This is a small part of a floor plan. Is there an opening tag printed in it that reads "{tag}" (usually inside a small circle beside a door or window)? If there is, give the centre
of the circle as a fraction of this picture's width and height (x from the left, y from the top, each 0 to 1). Judge only what you can see; if the tag is not in this picture, say so.
Return only JSON: {{"found": true or false, "x": 0.5, "y": 0.5}}"""
REFINE_REACH_MM = 3500  # the model's first place for a tag is off by a few metres on a large sheet; the look at a 7 m square finds the tag itself


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


def refine(img, scale: float, tags: list[tuple[str, float, float]], ask=None, workers: int = 10, reach_frac: float | None = None) -> list[tuple[str, float, float]]:
    """Put each tag at its true place: look at a 7 m square around where it was first placed and ask where the tag is in it. A tag that is not there was misread or read twice and is
    dropped. The first places are good to a few metres on a large sheet, which is too coarse to say which opening a tag belongs to; this is good to a few tenths of a metre."""
    from plan2cost.kit.client import chat_json, image_part

    ask = ask or (lambda prompt, path: chat_json([{"type": "text", "text": prompt}, image_part(path)]))
    h, w = img.shape[:2]
    folder = tempfile.mkdtemp()
    reach = int(reach_frac * max(h, w)) if reach_frac else int(REFINE_REACH_MM * scale)  # without the scale of the drawing yet, a fraction of the sheet (7% each way is about 3.5 m on a 50 m sheet)

    def one(i):
        tag, x, y = tags[i]
        cx, cy = int(x * scale), int(y * scale)
        x0, y0, x1, y1 = max(cx - reach, 0), max(cy - reach, 0), min(cx + reach, w), min(cy + reach, h)
        if x1 - x0 < 50 or y1 - y0 < 50:
            return None
        crop = img[y0:y1, x0:x1]
        small = cv2.resize(crop, None, fx=min(800 / max(crop.shape[:2]), 1.0), fy=min(800 / max(crop.shape[:2]), 1.0), interpolation=cv2.INTER_AREA)
        try:
            r = ask(LOOK.format(tag=tag), _save(small, f"{folder}/look{i}.jpg"))
        except Exception:
            return (tag, x, y)  # the look failed: keep the first place rather than lose the tag
        try:
            fx, fy = float(r["x"]), float(r["y"])
        except (KeyError, TypeError, ValueError):
            fx = fy = -1.0
        if not r.get("found") or not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        return (tag, (x0 + fx * (x1 - x0)) / scale, (y0 + fy * (y1 - y0)) / scale)
    with ThreadPoolExecutor(workers) as ex:
        out = [t for t in ex.map(one, range(len(tags))) if t]
    return dedupe(out, radius_mm=800)


def has_text_tags(text: str, minimum: int = 4) -> bool:
    """Does a PDF page's text layer carry opening tags (W1, D2...)? Then they are read from it, not by the model."""
    return sum(1 for w in re.findall(r"\b[A-Z]{1,3}\d{1,2}[A-Za-z]?\b", text) if re.match(r"^(?:[STP]?D|[AST]?W)\d", w)) >= minimum


def read_tags_fractional(img, ask=None) -> list[tuple[str, float, float]]:
    """Tags as fractions of the picture (x from the left, y from the top), found and put at their true place without needing the drawing's scale, so this can run while the walls are
    being traced. Convert with the picture's size and scale once the scale is known."""
    h, w = img.shape[:2]
    first = read_tags(img, 1.0, ask=ask)
    placed = refine(img, 1.0, first, ask=ask, reach_frac=0.07) if first else first
    return [(tag, x / w, y / h) for tag, x, y in placed]
