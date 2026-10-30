"""Where openings might be: the candidate finders. Each returns candidate stretches of a wall as dicts (the wall's id, its direction, the stretch's ends in millimetres on the sheet,
its measured width, whether the wall is external and its thickness, and `source`, which finder found it). None of them says what a candidate is: `openings.locate_openings` has the
model look at a crop of each and decide, and a printed tag is evidence for or against it. The finders, from the strongest evidence to the weakest:
- `candidates`: a gap where both faces of a wall are broken;
- `dimension_candidates`: a printed dimension that equals a schedule width, placed on the nearest wall (vector PDFs with a schedule);
- `jamb_candidates`: a stretch between two heavy jamb lines with a sill line between its faces (a window drawn inside a thick wall);
- `thin_face_candidates`: a stretch where the wall is drawn lighter than the rest (a window drawn as thin lines with a dot at each end);
- `end_gap_candidates`: the clear stretch from a wall end that meets nothing to the wall ahead of it (a door between two walls).
`text_tags` reads the opening tags (W1, D2...) from a PDF's text layer."""
import re

import cv2
import numpy as np

from plan2cost.drawing.model import DrawingModel

TAG = re.compile(r"^(?:[A-Z]{1,3}\d{1,2}[A-Za-z]?)$")  # an opening tag as printed: W1, D2, SD1, AW1
MIN_MM, MAX_MM = 450, 3700  # narrower is a jamb or a break in a face line, wider is a gap in the detection


def stretch_ink(img, scale: float, c: dict) -> float:
    """How much of the wall's thickness is drawn dark along a candidate's stretch (0 to 1). A door gap is nearly empty (a leaf and a threshold line at most); a stretch of wall
    drawn with thick faces and hatching is not."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    half = int(c["thickness"] / 2 * scale)
    if c["orient"] == "h":
        a, b = sorted((int(c["x0"] * scale), int(c["x1"] * scale)))
        y = int(c["y0"] * scale)
        band = gray[max(y - half, 0):y + half + 1, max(a, 0):b + 1]
    else:
        a, b = sorted((int(c["y0"] * scale), int(c["y1"] * scale)))
        x = int(c["x0"] * scale)
        band = gray[max(a, 0):b + 1, max(x - half, 0):x + half + 1]
    return float((band < 140).mean()) if band.size else 0.0


def candidates(model: DrawingModel) -> list[dict]:
    """Every stretch of a wall where both faces are broken and that is a plausible opening width, with its place on the sheet."""
    out = []
    for e in model.walls():
        for a, b in e.gaps_mm:
            if not MIN_MM <= b - a <= MAX_MM:
                continue
            x0, y0, x1, y1 = (a, e.y0_mm, b, e.y0_mm) if e.orient == "h" else (e.x0_mm, a, e.x0_mm, b)
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(b - a), "external": e.external_share >= 0.5,
                        "thickness": e.thickness_mm})
    return out


def end_gap_candidates(model: DrawingModel, have: list, reach_mm: float = 2400, tol_mm: float = 150) -> list[dict]:
    """A door is often a gap between the end of a wall and the wall it would meet (or the next wall on the same line), not a gap inside one run. For each wall end that
    meets nothing, the stretch from that end to the nearest wall ahead of it (450 to 2400 mm of clear space) is a candidate. Most will not be openings (a partition that
    simply stops), so the model decides from a crop; stretches that overlap a gap already found are left out."""
    from plan2cost.drawing.model import wall_of
    from plan2cost.drawing.qc import end_meets_wall

    els = model.walls()
    walls = [wall_of(e) for e in els]
    out: list[dict] = []
    for e, w in zip(els, walls):
        for sign, end in ((1, w.end_mm), (-1, w.start_mm)):
            if end_meets_wall(w, end, walls, tol_mm):
                continue
            best = None
            for o, v in zip(els, walls):
                if o is e:
                    continue
                if v.orient != w.orient:  # a wall across the line: its near face is the stop
                    face = v.centre_mm - sign * v.thickness_mm / 2
                    covers = v.start_mm - tol_mm <= w.centre_mm <= v.end_mm + tol_mm
                else:  # the next wall on the same line: where it starts
                    face = v.start_mm if sign == 1 else v.end_mm
                    covers = abs(v.centre_mm - w.centre_mm) <= max(v.thickness_mm, w.thickness_mm)
                clear = (face - end) * sign
                if covers and 450 <= clear <= reach_mm and (best is None or clear < best[0]):
                    best = (clear, face)
            if not best:
                continue
            a, b = sorted((end, best[1]))
            x0, y0, x1, y1 = (a, e.y0_mm, b, e.y0_mm) if e.orient == "h" else (e.x0_mm, a, e.x0_mm, b)
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            if any(abs((h["x0"] + h["x1"]) / 2 - mid[0]) < 450 and abs((h["y0"] + h["y1"]) / 2 - mid[1]) < 450 for h in have + out):
                continue
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(best[0]), "external": e.external_share >= 0.5,
                        "thickness": e.thickness_mm, "source": "between a wall end and the next wall"})
    return out


def _heavy_lines(band, c0: int, c1: int, margin: int = 6) -> int:
    """How many separate heavy lines run along the wall between two columns of its band (rows of the band mostly ink, groups of adjacent rows counted once)."""
    rows = band[:, c0 + margin:max(c1 - margin, c0 + margin + 1)].mean(axis=1) >= 0.7
    return int(np.count_nonzero(np.diff(np.concatenate([[0], rows.astype(np.int8)])) == 1))


def jamb_candidates(model: DrawingModel, img, scale: float, have: list, min_px: int = 3, require_sill: bool = True) -> list[dict]:
    """Openings drawn inside the wall with no break in its faces (a window shown as a sill and jamb lines across the wall): the stretches of a wall between two
    consecutive heavy lines that cross the whole thickness of the wall. Most of these stretches are plain wall, so they are only candidates; the model looks at each
    and says what it is. Stretches that overlap a gap already found are left out."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    dark = gray < 140
    out = []
    for e in model.walls():
        half = e.thickness_mm / 2 * scale + 1.5
        if e.orient == "h":
            a, b = sorted((int(e.x0_mm * scale), int(e.x1_mm * scale)))
            r0, r1 = int(e.y0_mm * scale - half), int(e.y0_mm * scale + half)
            band = dark[max(r0, 0):r1 + 1, max(a, 0):b + 1]
        else:
            a, b = sorted((int(e.y0_mm * scale), int(e.y1_mm * scale)))
            c0, c1 = int(e.x0_mm * scale - half), int(e.x0_mm * scale + half)
            band = dark[max(a, 0):b + 1, max(c0, 0):c1 + 1].T
        if band.size == 0 or band.shape[1] < 10:
            continue
        full = band.mean(axis=0) >= 0.85  # a column that is ink across the whole wall thickness
        runs, n = [], band.shape[1]
        i = 0
        while i < n:
            if full[i]:
                j = i
                while j + 1 < n and full[j + 1]:
                    j += 1
                if j - i + 1 >= min_px:
                    runs.append((i, j))
                i = j + 1
            else:
                i += 1
        if len(runs) > 12:
            continue  # a wall drawn solid, or hatched so densely that every column is full: no jamb lines to read
        for (s1, e1), (s2, e2) in zip(runs, runs[1:]):
            lo, hi = (e1 + 1) / scale, s2 / scale  # the stretch between the two lines, in mm along the wall
            width = hi - lo
            if not MIN_MM <= width <= MAX_MM:
                continue
            if require_sill and _heavy_lines(band, int(lo * scale), int(hi * scale)) < 3:
                continue  # two heavy face lines and nothing between them is plain wall; a window symbol has a third line (the sill) between its faces
            lo, hi = lo + max(a, 0) / scale, hi + max(a, 0) / scale  # the band starts at pixel max(a, 0) of the sheet
            x0, y0, x1, y1 = (lo, e.y0_mm, hi, e.y0_mm) if e.orient == "h" else (e.x0_mm, lo, e.x0_mm, hi)
            if any(h["wall"] == e.id and min(hi, h["x1"] if e.orient == "h" else h["y1"]) - max(lo, h["x0"] if e.orient == "h" else h["y0"]) > 0.5 * width for h in have):
                continue
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(width), "external": e.external_share >= 0.5,
                        "thickness": e.thickness_mm, "source": "between jamb lines"})
    return out


def thin_face_candidates(model: DrawingModel, img, scale: float, have: list, min_run_mm: float = 300, jamb_mm: float = 60) -> list[dict]:
    """Windows drawn as lighter lines inside the wall, with a dot or a short line at each end: along a wall the ink across its thickness drops from the heavy face lines to the
    thin lines of the symbol. A stretch of 300 to 2400 mm where the wall is drawn at under 60% of its usual weight, but still drawn, is a candidate (widened by the jamb at each end).
    Most such stretches are not openings (hatching, a notch), so the model looks at each; stretches that overlap an opening already found are left out."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    dark = gray < 140
    out = []
    for e in model.walls():
        half = int(e.thickness_mm / 2 * scale + 2)
        if e.orient == "h":
            a, b = sorted((int(e.x0_mm * scale), int(e.x1_mm * scale)))
            c = int(e.y0_mm * scale)
            band = dark[max(c - half, 0):c + half + 1, max(a, 0):b + 1]
        else:
            a, b = sorted((int(e.y0_mm * scale), int(e.y1_mm * scale)))
            c = int(e.x0_mm * scale)
            band = dark[max(a, 0):b + 1, max(c - half, 0):c + half + 1].T
        if band.size == 0 or band.shape[1] < 20 or band.shape[0] < 4:
            continue
        frac = band.mean(axis=0)
        solid = frac[frac >= 0.3]
        if len(solid) < 0.3 * len(frac):
            continue  # a wall that is not drawn heavily for most of its length has no weight to drop from
        heavy = float(np.median(solid))
        thin = (frac > 0.06) & (frac < 0.6 * heavy)
        edges = np.diff(np.concatenate([[0], thin.astype(np.int8), [0]]))
        for s, f in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            run = (f - s) / scale
            if run < min_run_mm or run + 2 * jamb_mm > MAX_MM - 1000:
                continue
            lo, hi = max(a, 0) / scale + s / scale - jamb_mm, max(a, 0) / scale + f / scale + jamb_mm
            x0, y0, x1, y1 = (lo, e.y0_mm, hi, e.y0_mm) if e.orient == "h" else (e.x0_mm, lo, e.x0_mm, hi)
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            if any(h["wall"] == e.id and abs((h["x0"] + h["x1"]) / 2 - mid[0]) < 450 and abs((h["y0"] + h["y1"]) / 2 - mid[1]) < 450 for h in have + out):
                continue
            out.append({"wall": e.id, "orient": e.orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": round(hi - lo), "external": e.external_share >= 0.5, "thickness": e.thickness_mm,
                        "source": "where the wall faces are drawn lighter"})
    return out


def _mm_per_pt(model: DrawingModel) -> float | None:
    """Millimetres of building to a point of the PDF page, or None when the model came from an image (no text layer to place)."""
    cal = model.calibrations[0]
    if cal.unit == "pt":
        return cal.mm_per_unit
    return cal.mm_per_unit * cal.detail["dpi"] / 72 if cal.detail.get("dpi") else None


def dimension_candidates(model: DrawingModel, pdf: str, page: int, widths_mm: set, have: list, reach_mm: float = 4500) -> list[dict]:
    """A printed dimension equal to a schedule width marks a place where an opening may be: put a candidate on the nearest wall (running the
    same way as the dimension chain) at that position. Walls where a gap was already found at that place are not doubled up."""
    from plan2cost.drawing.dims import dimension_tokens

    k = _mm_per_pt(model)
    if not k or not widths_mm:
        return []
    out = []
    for t in dimension_tokens(pdf, page):
        if not any(abs(t.value - w) <= 5 for w in widths_mm):
            continue
        along, across = t.along * k, t.across * k
        orient = "v" if t.vertical else "h"  # a vertical chain dimensions openings in a vertical wall
        walls = [e for e in model.walls() if e.orient == orient]
        best = None
        for e in walls:
            lo, hi = (e.x0_mm, e.x1_mm) if orient == "h" else (e.y0_mm, e.y1_mm)
            pos = e.y0_mm if orient == "h" else e.x0_mm
            if lo - 100 <= along <= hi + 100 and abs(pos - across) <= reach_mm:
                d = abs(pos - across) - (400 if e.external_share >= 0.5 else 0)  # the chains outside the building dimension its outer walls
                if best is None or d < best[0]:
                    best = (d, e)
        if not best:
            continue
        e = best[1]
        a, b = along - t.value / 2, along + t.value / 2
        if any(h["wall"] == e.id and abs((h["x0"] + h["x1"] + h["y0"] + h["y1"]) / 2 - (a + b) / 2 - (e.y0_mm if orient == "h" else e.x0_mm)) < 450 for h in have):
            continue
        x0, y0, x1, y1 = (a, e.y0_mm, b, e.y0_mm) if orient == "h" else (e.x0_mm, a, e.x0_mm, b)
        out.append({"wall": e.id, "orient": orient, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_mm": int(t.value), "external": e.external_share >= 0.5, "thickness": e.thickness_mm,
                    "source": "printed dimension"})
    uniq: list[dict] = []  # the same dimension is often printed on two chains
    for c in out:
        if not any(u["wall"] == c["wall"] and abs(u["x0"] - c["x0"]) + abs(u["y0"] - c["y0"]) < 300 for u in uniq):
            uniq.append(c)
    return uniq


def text_tags(pdf: str, page: int, model: DrawingModel) -> list[tuple[str, float, float]]:
    """Tags like W3 or D2 from the page's text layer with their position in the model's frame (mm). Empty for an image or a page with no text."""
    import subprocess

    from plan2cost.kit.pdf import pdftoppm

    mm_per_pt = _mm_per_pt(model)
    if not mm_per_pt:
        return []
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    html = subprocess.run([exe, "-f", str(page), "-l", str(page), "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    out = []
    for x0, y0, x1, y1, w in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)</word>', html):
        if TAG.match(w):
            out.append((w, (float(x0) + float(x1)) / 2 * mm_per_pt, (float(y0) + float(y1)) / 2 * mm_per_pt))
    return out
