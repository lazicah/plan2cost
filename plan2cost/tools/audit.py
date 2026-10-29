"""Audit a contractor's quote against the BoQ the agent filed. The comparison is deterministic; see takeoff/audit.py."""
import json
from dataclasses import asdict
from pathlib import Path

from plan2cost.facts.quote import match_lines, read_quote
from plan2cost.kit.progress import Run
from plan2cost.takeoff.audit import audit


def audit_quote(run: Run) -> dict:
    """Check the contractor's quote line by line against our BoQ: arithmetic, quantities, rates against the user's rates, units, duplicates and work
    the quote leaves out. Needs compute_boq first. Each flag says what to ask the contractor. Report the flags in plain words; never call a contractor dishonest."""
    if not run.quote:
        return {"error": "No contractor quote was given for this run."}
    if "boq" not in run.data:
        return {"error": "Compute the BoQ first (compute_boq): the quote is checked against it."}
    items: dict = {}
    for i in run.data["boq"]["items"]:  # one BoQ key can carry several lines (an opening type on both sides of the wall): the quote prices the total
        it = items.setdefault(i["key"], {"description": i["description"], "unit": i["unit"], "qty": 0})
        it["qty"] = round(it["qty"] + i["qty"], 3)
    rates = json.loads(Path("data/rates.json").read_text())["rates"]
    rates.update({i["key"]: i["rate"] for i in run.data["boq"]["items"] if i.get("rate")})
    q = read_quote(run.quote, str(run.dir / "scratch"))
    if not q["lines"]:
        return {"error": "No priced lines could be read from the quote.", "unverified": q["unverified"]}
    match_lines(q["lines"], items)
    result = audit(q["lines"], q["total"], items, rates) | {"unverified_readings": q["unverified"], "currency": q["currency"]}
    run.data["audit"] = result | {"quote_lines": [asdict(l) for l in q["lines"]]}
    run.dir.mkdir(parents=True, exist_ok=True)
    (run.dir / "audit.json").write_text(json.dumps(run.data["audit"], indent=2))
    return result


TOOLS = {
    "audit_quote": (audit_quote, "no args: when a contractor quote was given, check it line by line against the BoQ (after compute_boq, before submit_boq)"),
}
