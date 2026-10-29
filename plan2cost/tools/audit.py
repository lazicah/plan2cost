"""Audit a contractor's quote against the BoQ the agent filed. The comparison is deterministic; see takeoff/audit.py."""
import json
from dataclasses import asdict
from pathlib import Path

from plan2cost.facts.quote import match_lines, read_quote
from plan2cost.kit.progress import Run
from plan2cost.takeoff.audit import audit
from plan2cost.takeoff.boq import load_rates
from plan2cost.takeoff.tender import audit_bid, compare_bids


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
    rates = dict(load_rates(run.inputs.get("finish_level"))["rates"])
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


def _rates(run: Run) -> dict:
    rates = dict(load_rates(run.inputs.get("finish_level"))["rates"])
    rates.update({i["key"]: i["rate"] for i in run.data["boq"]["items"] if i.get("rate")})
    return rates


def audit_bids(run: Run, paths: list[str]) -> dict:
    """Bids returned on the unpriced bill this run issued (bill.json). A bill returned as Excel is read directly; a PDF or image is read by the model
    and matched by item number. Each bid is audited alone and all are compared side by side. Saved as tender_audit.json."""
    from plan2cost.takeoff.bill import read_xlsx_bid

    issued = json.loads((run.dir / "bill.json").read_text())
    rates = _rates(run) if "boq" in run.data else {}
    bids, audits = {}, {}
    for path in paths:
        name, total, unverified = Path(path).stem, None, []
        if path.lower().endswith(".xlsx"):
            bid = read_xlsx_bid(path)
        else:
            q = read_quote(path, str(run.dir / "scratch" / name))
            bid = {l.no: {"description": l.description, "unit": l.unit, "qty": l.qty, "rate": l.rate, "amount": l.amount} for l in q["lines"]}
            total, unverified = q["total"], q["unverified"]
        bids[name] = bid
        audits[name] = audit_bid(issued, bid, total, rates) | {"unverified_readings": unverified}
    compared = compare_bids(issued, bids)
    for name, flags in compared["peer_flags"].items():
        audits[name]["flags"] += flags
        audits[name]["counts"] = {c: sum(f["code"] == c for f in audits[name]["flags"]) for c in sorted({f["code"] for f in audits[name]["flags"]})}
    out = {"bids": audits, "comparison": compared["items"], "note": "Totals are the bid's rates at our issued quantities. A bid with unpriced items is not comparable on total."}
    (run.dir / "tender_audit.json").write_text(json.dumps(out, indent=2))
    return out


TOOLS = {
    "audit_quote": (audit_quote, "no args: when a contractor quote was given, check it line by line against the BoQ (after compute_boq, before submit_boq)"),
}
