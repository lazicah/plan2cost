"""File the BoQ. The verification gate is part of this tool, not a separate tool the agent could skip."""
import json

from plan2cost.agent.verify import verify_boq
from plan2cost.kit.progress import Run


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
    return {"filed": True}


TOOLS = {
    "submit_boq": (submit_boq, "summary: str: the gate; refused unless everything is settled"),
}
