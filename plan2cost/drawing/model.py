"""The verified drawing model: what the interpreter found on a plan page, as a register that can be saved, checked, drawn on the plan and read by
later steps. Nothing here measures from pixels or asks a model; it holds what code measured, with where each thing came from and how far to
trust it. Every number carries an evidence label, and what could not be settled is kept as an issue, not hidden in a total."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from plan2cost.drawing.walls_cv import Wall, building_size_m

# How a fact is known. A printed dimension is read, a length is measured from traced geometry, a classification is inferred from conventions.
EVIDENCE = ("directly labelled", "geometrically measured", "inferred", "approximate", "unresolved")


@dataclass
class Calibration:
    id: str
    view: str
    method: str
    mm_per_unit: float
    unit: str  # "pt" (vector page) or "px" (raster image)
    basis: str
    annotated_mm: list = field(default_factory=list)  # printed dimensions the scale was checked against
    agreement: float | None = None  # share of the printed dimensions that agree (vector) or the fit error (raster)
    evidence: str = "directly labelled"
    confidence: str = "medium"
    detail: dict = field(default_factory=dict)


@dataclass
class Element:
    id: str
    category: str  # wall
    subtype: str  # external, internal
    page: int
    floor: str
    orient: str  # "h" or "v" in the sheet frame
    x0_mm: float
    y0_mm: float
    x1_mm: float
    y1_mm: float
    length_m: float
    thickness_mm: float
    convention: str = "centre-line"
    external_share: float = 0.0  # part of the run with the outdoors on one side
    connected: list = field(default_factory=list)  # ids of the walls it meets
    evidence: str = "geometrically measured"
    confidence: str = "medium"
    notes: list = field(default_factory=list)
    gaps_mm: list = field(default_factory=list)  # stretches along the run (sheet frame) where both faces are broken: candidate openings
    parent: str = ""  # for a door, window or opening: the id of the wall it is in
    mark: str = ""  # the tag on the drawing (W3, D2...) and the schedule type it was matched to
    width_mm: float = 0.0  # measured from the drawing, for an opening


@dataclass
class Issue:
    code: str
    severity: str  # error, warn, info
    message: str
    elements: list = field(default_factory=list)
    check: str = ""  # what a person should look at
    source: str = "code"  # code or model review


@dataclass
class DrawingModel:
    page: int
    floor: str
    route: str  # vector, raster
    confidence: str
    calibrations: list = field(default_factory=list)
    elements: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    markup: str = ""  # file name of the annotated plan, relative to the model file

    def walls(self) -> list:
        return [e for e in self.elements if e.category == "wall"]

    def openings(self) -> list:
        return [e for e in self.elements if e.category in ("door", "window", "opening")]

    def summary(self) -> dict:
        return {"floor": self.floor, "page": self.page, "route": self.route, "confidence": self.confidence, **self.totals, "walls": len(self.walls()),
                "issues": [{"severity": i.severity, "code": i.code, "message": i.message, "source": i.source} for i in self.issues if i.severity != "info"],
                "markup": self.markup}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=1))

    @classmethod
    def load(cls, path: str | Path) -> "DrawingModel":
        d = json.loads(Path(path).read_text())
        return cls(**{**d, "calibrations": [Calibration(**c) for c in d["calibrations"]], "elements": [Element(**e) for e in d["elements"]],
                      "issues": [Issue(**i) for i in d["issues"]]})


def touching(a: Wall, b: Wall, tol_mm: float = 150) -> bool:
    """Do two runs meet (a joint, a corner or a crossing)? Parallel runs never do."""
    if a.orient == b.orient:
        return False
    h, v = (a, b) if a.orient == "h" else (b, a)
    return h.start_mm - tol_mm <= v.centre_mm <= h.end_mm + tol_mm and v.start_mm - tol_mm <= h.centre_mm <= v.end_mm + tol_mm


def merge_gaps(gaps: list, start: float, end: float, join_mm: float = 60) -> list:
    """One interval per opening: overlapping or touching gaps are joined, and a gap at the very end of a run is not an opening (it is where the run stops)."""
    out: list = []
    for a, b in sorted(gaps):
        if out and a <= out[-1][1] + join_mm:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[round(a, 1), round(b, 1)] for a, b in out if a > start + 100 and b < end - 100]


def stable_order(walls: list[Wall]) -> list[int]:
    """Indexes in a fixed order, so the same drawing always gives the same ids: horizontal runs top to bottom, then vertical runs left to right,
    each by where it starts. Positions are rounded to 50mm so a one-pixel wobble does not reshuffle ids."""
    return sorted(range(len(walls)), key=lambda i: (walls[i].orient != "h", round(walls[i].centre_mm / 50), round(walls[i].start_mm / 50)))


def build_model(result: dict, floor: str, page: int, printed_mm: list | None = None) -> DrawingModel:
    """Make the register from an interpreter result that kept its walls (`keep=True`)."""
    walls: list[Wall] = result["_walls"]
    fractions = result["_fractions"]
    unit, mm_unit = result["_unit"], result["_mm_per_unit"]
    conf = result.get("confidence", "medium")
    order = stable_order(walls)
    ids = {i: f"W-{n:03d}" for n, i in enumerate(order, 1)}
    elements = []
    for i in order:
        w, f = walls[i], fractions[i]
        x0, y0, x1, y1 = (w.start_mm, w.centre_mm, w.end_mm, w.centre_mm) if w.orient == "h" else (w.centre_mm, w.start_mm, w.centre_mm, w.end_mm)
        notes = ["part of this run has the outdoors on one side and part does not"] if 0.15 < f < 0.85 else []
        elements.append(Element(ids[i], "wall", "external" if f >= 0.5 else "internal", page, floor, w.orient, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1),
                                round(w.length_mm / 1000, 3), float(w.thickness_mm), external_share=round(float(f), 2),
                                connected=sorted(ids[j] for j, v in enumerate(walls) if j != i and touching(w, v)), confidence=conf, notes=notes,
                                gaps_mm=merge_gaps(w.gaps, w.start_mm, w.end_mm)))
    cal = result.get("_calibration", {})
    method = cal.get("method", "unknown")
    strong = method.startswith("printed dimensions") or "overall dimensions" in method
    calibration = Calibration("C-001", f"page {page}, {floor} floor plan", method, round(float(mm_unit), 4), unit, cal.get("basis", result.get("scale", "")),
                              annotated_mm=cal.get("printed_overall_mm", []), agreement=cal.get("agree", cal.get("fit_error")),
                              evidence="directly labelled" if strong else "approximate", confidence="high" if strong and conf == "high" else "medium" if strong else "low",
                              detail={k: v for k, v in cal.items() if k not in ("basis", "method", "readings")})
    ext = sum(e.length_m * e.external_share for e in elements)
    total = sum(e.length_m for e in elements)
    by_thickness: dict = {}
    for e in elements:
        by_thickness[int(e.thickness_mm)] = round(by_thickness.get(int(e.thickness_mm), 0) + e.length_m, 2)
    size = building_size_m(walls)  # between the outermost joints: a run overshooting the building does not inflate it
    model = DrawingModel(page, floor, result.get("route", result.get("source", "")), conf, [calibration], elements,
                         totals={"total_m": round(total, 2), "external_m": round(ext, 2), "internal_m": round(total - ext, 2), "by_thickness_m": by_thickness,
                                 "length_m": round(size[0], 2), "width_m": round(size[1], 2)})
    from plan2cost.drawing.qc import run_checks

    model.issues = run_checks(model, printed_mm if printed_mm is not None else cal.get("printed_overall_mm", []))
    return model
