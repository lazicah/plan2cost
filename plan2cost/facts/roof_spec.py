"""What the drawings print about the roof, read from the text layer with no model: the roof levels on a section (apex and fascia or eaves, a number
printed just under its label) and the specification note (covering, and the timber members with their sizes and spacing). Every value is a printed number
or phrase, kept with the page it came from."""
import re
import subprocess
from dataclasses import dataclass, field

from plan2cost.kit.pdf import page_count, page_text, pdftoppm

MEMBERS = {"purlins": "purlins", "rafters": "rafters", "trusses": "trusses", "tie beam": "tie_beam", "tie beams": "tie_beam", "wall plates": "wall_plates"}
LEVEL_LABELS = {"apex_mm": ("apex",), "eaves_mm": ("fascia", "eaves")}  # the last word of the label is what the number sits under


@dataclass
class RoofSpec:
    page: int
    covering: str = ""
    members: dict = field(default_factory=dict)  # name -> {"section_mm": [w, d], "spacing_mm": n|None, "quote": str}
    levels: dict = field(default_factory=dict)  # apex_mm, eaves_mm


def _words(pdf: str, page: int) -> list[dict]:
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    html = subprocess.run([exe, "-f", str(page), "-l", str(page), "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    return [{"x0": float(a), "y0": float(b), "x1": float(c), "y1": float(d), "t": w}
            for a, b, c, d, w in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', html)]


def levels(words: list[dict]) -> dict:
    """A level is the 4 or 5 digit number printed directly under its label and right-aligned with it."""
    out = {}
    for key, labels in LEVEL_LABELS.items():
        for w in words:
            if w["t"].lower().strip(".,:") in labels:
                label_end = next((x for x in words if x["y0"] == w["y0"] and x["x0"] >= w["x0"] and x["t"].lower() == "level"), w)  # "Fascia level": the number sits under "level"
                near = [n for n in words if re.fullmatch(r"\d{4,5}", n["t"]) and label_end["y1"] - 2 <= n["y0"] <= label_end["y1"] + 25 and abs(n["x1"] - label_end["x1"]) <= 15]
                if near:
                    out[key] = float(min(near, key=lambda n: n["y0"])["t"])
                    break
    return out


def parse_spec(text: str) -> tuple[str, dict]:
    flat = re.sub(r"\s+", " ", text)
    cov = re.search(r"(\d+(?:\.\d+)?\s*mm[^.@]{0,40}?(?:roofing sheet|roofing tiles?|roof sheet|sheeting))", flat, re.I)
    members = {}
    for m in re.finditer(r"(\d+)\s*x\s*(\d+)\s*mm\s+(?:timber\s+)?(purlins|rafters|trusses|tie beams?|wall plates)(?:\s*@\s*(\d+)\s*mm\s*centres)?", flat, re.I):
        members[MEMBERS[m.group(3).lower()]] = {"section_mm": [int(m.group(1)), int(m.group(2))], "spacing_mm": int(m.group(4)) if m.group(4) else None, "quote": m.group(0)}
    return (cov.group(1).strip() if cov else ""), members


def read_roof_spec(pdf: str, pages: list[int] | None = None) -> RoofSpec | None:
    """The roof specification and levels, gathered over the given pages (default: every page): the covering and each timber member from the first page that
    prints them, the apex and eaves levels from the first page that prints them. Elevations print levels and sections print the note, so both are needed."""
    spec = RoofSpec(0)
    for p in pages or range(1, page_count(pdf) + 1):
        text = page_text(pdf, p)
        cov, members = parse_spec(text)
        lv = levels(_words(pdf, p)) if re.search(r"apex|fascia", text, re.I) else {}
        if (cov or members) and not spec.page:
            spec.page = p
        spec.covering = spec.covering or cov
        for k, v in members.items():
            spec.members.setdefault(k, v)
        for k, v in lv.items():
            spec.levels.setdefault(k, v)
    return spec if (spec.covering or spec.members or spec.levels) else None
