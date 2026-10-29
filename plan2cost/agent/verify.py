"""The submit gate. It runs inside submit_boq, so the agent cannot skip it or choose not to call it: a BoQ is filed only if every check passes,
and each refusal says what to do next. The checks are deterministic; the quotes behind the facts were already checked when they were recorded."""
from plan2cost.kit.progress import Run


def verify_boq(run: Run) -> list[str]:
    """Reasons the estimate cannot be filed yet; empty when it can."""
    problems = []
    unread = [f["name"] for f in run.floors if f["name"] not in (run.data.get("floors") or {})]
    open_items = [c["id"] for c in run.checklist if c["status"] in ("open", "escalated")]
    if not run.floors:
        problems.append("No floor plan was given.")
    if unread:
        problems.append(f"Floors not read yet: {unread} (read_floor, or assume_floor_like_ground).")
    if open_items and not unread:
        problems.append(f"Items not settled: {open_items}.")
    if run.pending:
        problems.append("A question to the user is still open.")
    if "boq" not in run.data:
        problems.append("The estimate has not been computed yet (compute_boq).")
    if run.quote and "audit" not in run.data:
        problems.append("A contractor quote was given but it has not been audited (audit_quote).")
    return problems
