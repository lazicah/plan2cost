"""Plan -> BoQ: BESMM4-style items from a take-off, with every assumed input flagged and no invented prices."""
import json
from dataclasses import dataclass
from pathlib import Path

from plan2cost.tools.foundation import StripSection


@dataclass
class Assumption:
    name: str
    value: float
    basis: str
    source: str  # "drawing" or "assumed"


@dataclass
class BoqItem:
    key: str  # take-off / rate key, e.g. trench_excavation_strip_m3
    description: str
    unit: str
    qty: float
    rate: float | None = None
    amount: float | None = None


def load_defaults(path: str = "data/defaults.json") -> dict:
    return json.loads(Path(path).read_text())["foundation_strip"]


def strip_inputs(drawn: dict | None = None, defaults: dict | None = None) -> tuple[StripSection, list[Assumption], float]:
    """Merge what the drawing states with defaults. Returns the section, the assumption log and the concrete grade."""
    drawn, defaults = drawn or {}, defaults or load_defaults()
    log, vals = [], {}
    for name, d in defaults.items():
        if name in drawn:
            vals[name] = drawn[name]
            log.append(Assumption(name, drawn[name], "stated on the drawing", "drawing"))
        else:
            vals[name] = d["value"]
            log.append(Assumption(name, d["value"], d["basis"], "assumed"))
    grade = vals.pop("concrete_grade")
    return StripSection(**vals), log, grade


def foundation_boq(t: dict, s: StripSection, grade: float) -> list[BoqItem]:
    depth = f"maximum depth not exceeding 2.00m; commencing surface {int(s.topsoil_m * 1000)}mm below existing ground level"
    block = f"{s.block_mm}mm thick; 225 x 450 nominal blocks; laid stretcher bond; cement mortar (1:6); filled solid with weak concrete"
    rows = [
        ("trench_excavation_strip_m3", f"Trench excavation, width exceeding 0.30m; {depth}", "m3"),
        ("pit_excavation_column_bases_m3", f"Pits excavation for column bases; {depth}", "m3"),
        ("working_space_m3", "Working space allowance to excavation; including additional support, disposal and backfilling with selected excavated material", "m3"),
        ("earthwork_support_m2", "Earthwork support; maximum depth not exceeding 2.00m; distance between opposing faces not exceeding 2.00m", "m2"),
        ("strip_footing_concrete_m3", f"Plain in situ concrete, grade {grade:g}; foundations", "m3"),
        (f"fdn_blockwork_{s.block_mm}_m2", f"Blockwork walls in foundation; {block}", "m2"),
    ]
    return [BoqItem(k, d, u, t[k]) for k, d, u in rows if k in t]


def price_boq(items: list[BoqItem], rates: dict) -> dict:
    """Price with user-supplied rates. A missing or zero rate leaves the line unpriced; it is never guessed."""
    unpriced = []
    for i in items:
        r = rates["rates"].get(i.key)
        if r:
            i.rate, i.amount = r, round(i.qty * r, 2)
        else:
            unpriced.append(i.key)
    return {"currency": rates["currency"], "total": round(sum(i.amount or 0 for i in items), 2), "unpriced": unpriced}
