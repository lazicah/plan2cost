"""Candidate-and-verify opening finder. The PDF text layer gives every printed width with its position (dims.py); for each
candidate the model looks at a slice of the plan through that position and says what is there. Labelled example symbols are
loaded from reference/symbols/ when present (they are other people's drawings, so they stay local and out of git)."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from plan2cost.client import get_client, image_part, model_name
from plan2cost.dims import DimToken, dimension_tokens, width_candidates
from plan2cost.extract import parse_json
from plan2cost.pdf import render_pages
from plan2cost.symbols import DOORS, WALLS_AND_HATCH, WINDOWS

SYMBOL_DIR = Path("reference/symbols")
KINDS = ("window", "door", "wall_piece", "other")

VERIFY_PROMPT = """You are checking one printed dimension on a floor plan, for a quantity surveyor.
The strip image is a slice through the plan at the position of a printed dimension of {value}mm on the {side} dimension chain.
Look at the {side} wall of the building in this strip, at the position that dimension spans, and say what is there.

""" + DOORS + "\n\n" + WINDOWS + "\n\n" + WALLS_AND_HATCH + """

Answer with one of: "window", "door", "wall_piece" (solid hatched wall of that length, so the dimension is not an opening) or "other"
(anything else, or you cannot tell). Do not guess: if the strip is unclear, answer "other".
Reply with JSON only: {{"kind": "window"|"door"|"wall_piece"|"other", "evidence": str}}
"""


def examples() -> list[tuple[str, str]]:
    """(caption, path) for each local example symbol; the file name says what it shows (example_<kind>_<where>.png)."""
    out = []
    for p in sorted(SYMBOL_DIR.glob("example_*.png")):
        kind = p.stem.split("_")[1]
        out.append((f"Example of a {kind} symbol from this kind of drawing:", str(p)))
    return out


def slice_image(page_img: Image.Image, token: DimToken, scale: float, half_pts: float = 40.0) -> Image.Image:
    """A band through the whole drawing, centred on the token along the wall, so the wall it dimensions is inside it."""
    w, h = page_img.size
    a0, a1 = int((token.along - half_pts) * scale), int((token.along + half_pts) * scale)
    box = (a0, int(h * 0.05), a1, int(h * 0.95)) if not token.vertical else (int(w * 0.03), a0, int(w * 0.88), a1)
    return page_img.crop(box)


def tight_slice(page_img: Image.Image, token: DimToken, scale: float, side: str, half_pts: float = 40.0, depth_pts: float = 190.0) -> Image.Image:
    """A small box on the wall nearest the chain: the chains sit outside the building, so the wall lies just inward of the token.
    Enlarged so the thin symbol lines are legible."""
    sign = 1 if side in ("top", "left") else -1
    a0, a1 = (token.along - half_pts) * scale, (token.along + half_pts) * scale
    c0, c1 = sorted((token.across - sign * 10 * scale / scale, token.across + sign * depth_pts))
    box = (a0, c0 * scale, a1, c1 * scale) if not token.vertical else (c0 * scale, a0, c1 * scale, a1)
    img = page_img.crop(tuple(int(v) for v in box))
    return img.resize((img.width * 2, img.height * 2), Image.LANCZOS)


def side_of(token: DimToken, page_w: float, page_h: float) -> str:
    if token.vertical:
        return "left" if token.across < page_w * 0.45 else "right"
    return "top" if token.across < page_h * 0.5 else "bottom"


def verify(token: DimToken, strip_path: str, side: str) -> dict:
    content = [{"type": "text", "text": VERIFY_PROMPT.format(value=token.value, side=side)}]
    for caption, path in examples():
        content += [{"type": "text", "text": caption}, image_part(path)]
    content += [{"type": "text", "text": "The strip to check:"}, image_part(strip_path)]
    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=[{"role": "user", "content": content}])
    try:
        out = parse_json(resp.choices[0].message.content)
    except ValueError:
        out = {"kind": "other", "evidence": "unparseable reply"}
    return {"kind": out.get("kind") if out.get("kind") in KINDS else "other", "evidence": out.get("evidence", "")}


def find_openings(pdf: str, page: int, floor: str, widths: tuple[int, ...], scratch: str, dpi: int = 200, workers: int = 4) -> list[dict]:
    tokens = dimension_tokens(pdf, page)
    whole = render_pages(pdf, [page], scratch, dpi=dpi)[0]
    img = Image.open(whole)
    scale = dpi / 72.0
    page_w, page_h = img.width / scale, img.height / scale
    jobs = []
    for value in widths:
        for t in width_candidates(tokens, value):
            side = side_of(t, page_w, page_h)
            path = Path(scratch) / f"cand_{page}_{value}_{int(t.x0)}_{int(t.y0)}.jpg"
            slice_image(img, t, scale).save(path, quality=90)
            jobs.append((t, side, str(path)))
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda j: verify(j[0], j[2], j[1]), jobs))
    # second pass: whatever came back unclear is re-asked on a tight crop of the wall beside the chain
    again = [i for i, r in enumerate(results) if r["kind"] == "other"]
    tight_paths = []
    for i in again:
        t, side, _ = jobs[i]
        path = Path(scratch) / f"tight_{page}_{t.value}_{int(t.x0)}_{int(t.y0)}.jpg"
        tight_slice(img, t, scale, side).save(path, quality=92)
        tight_paths.append(str(path))
    with ThreadPoolExecutor(workers) as ex:
        second = list(ex.map(lambda i_p: verify(jobs[i_p[0]][0], i_p[1], jobs[i_p[0]][1]), zip(again, tight_paths)))
    passes = [1] * len(results)
    for i, r in zip(again, second):
        results[i], passes[i] = r, 2
    return [{"floor": floor, "width_mm": t.value, "side": side, "kind": r["kind"], "evidence": r["evidence"], "count": 1, "pass": ps,
             "along_pts": round(t.along, 1), "across_pts": round(t.across, 1), "page_w_pts": round(page_w, 1)}
            for (t, side, _), r, ps in zip(jobs, results, passes)]


def flat_of(rec: dict) -> str:
    """Which half of a mirrored building an opening is in. Left and right chains are the two outer walls; for top and bottom
    chains the mirror axis is the centre of the drawing area (the title-block column is excluded)."""
    if rec["side"] == "left":
        return "A"
    if rec["side"] == "right":
        return "B"
    return "A" if rec["along_pts"] < rec["page_w_pts"] * 0.9 / 2 + rec["page_w_pts"] * 0.03 else "B"


def mirror_check(records: list[dict]) -> dict:
    """For a building made of two mirrored flats, each flat must have the same windows. Returns per floor and width the counts
    in each flat; a mismatch means a candidate was missed or misjudged and the user is asked, not guessed for."""
    out: dict = {}
    for r in records:
        if r["kind"] != "window":
            continue
        cell = out.setdefault(r["floor"], {}).setdefault(str(r["width_mm"]), {"A": 0, "B": 0})
        cell[flat_of(r)] += 1
    return out
