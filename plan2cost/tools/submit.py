"""File the BoQ. The verification gate is part of this tool, not a separate tool the agent could skip."""
import json

from plan2cost.agent.verify import verify_boq
from plan2cost.kit.progress import Run
from plan2cost.takeoff.bill import numbered, ranged, write_pdf, write_xlsx


def submit_boq(run: Run, summary: str = "") -> dict:
    """The gate. Refused unless every checklist item is settled, a BoQ has been computed, and nothing is waiting on a person."""
    problems = verify_boq(run)
    if problems:
        return {"refused": problems}
    run.status = "done"
    cov = (run.data["boq"].get("coverage") or {}).get("statement", "")
    run.result = {"summary": (summary if cov and cov in summary else (summary + " " + cov)).strip(), "boq": run.data["boq"], "assumptions": run.assumptions}
    run.dir.mkdir(parents=True, exist_ok=True)
    (run.dir / "boq.json").write_text(json.dumps(run.result, indent=2))
    rows = numbered(run.data["boq"].get("items", []))
    (run.dir / "bill.json").write_text(json.dumps(rows, indent=2))  # the issued item numbers, so returned bids can be matched
    cur = run.data["boq"].get("currency", "NGN")
    files = ["bill_priced.xlsx", "bill_priced.pdf"]
    write_xlsx(run.dir / "bill_priced.xlsx", rows, True, cur, "Bill of quantities", run.id)
    write_pdf(run.dir / "bill_priced.pdf", rows, True, cur, "Bill of quantities", run.id)
    if not ranged(rows):  # an unpriced bill for tender only when every quantity was measured
        write_xlsx(run.dir / "bill_unpriced.xlsx", rows, False, cur, "Bill of quantities", run.id)
        write_pdf(run.dir / "bill_unpriced.pdf", rows, False, cur, "Bill of quantities", run.id)
        files += ["bill_unpriced.xlsx", "bill_unpriced.pdf"]
    return {"filed": True, "bills": files}


TOOLS = {
    "submit_boq": (submit_boq, "summary: str: the gate; refused unless everything is settled"),
}
