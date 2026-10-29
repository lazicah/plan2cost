"""The submit gate. It runs inside submit_boq, so the agent cannot skip it or choose not to call it: a BoQ is filed only if every check passes,
and each refusal says what to do next. The checks are deterministic; the quotes behind the facts were already checked when they were recorded."""
from plan2cost.kit.progress import Run


def verify_boq(run: Run) -> list[str]:
    """Reasons the BoQ cannot be filed yet; empty when it can."""
    problems = []
    open_items = [c["id"] for c in run.checklist if c["status"] in ("open", "escalated")]
    if not run.checklist:
        problems.append("No checklist has been set.")
    if open_items:
        problems.append(f"Items not settled: {open_items}. Record a fact for each, or ask the user.")
    if run.pending:
        problems.append("A question to the user is still open.")
    unresolved = [f["name"] for f in run.facts if f.get("warning")]
    if unresolved:
        problems.append(f"Facts with an unresolved warning: {unresolved}. Ask the user to confirm them.")
    if "boq" not in run.data:
        problems.append("No BoQ has been computed yet (compute_boq).")
    if run.structural_pdf:
        if not any(f["name"].startswith("fdn_") and f.get("file") == "structural" for f in run.facts):
            problems.append("A structural drawing was given but the foundation section was not read (read_foundation_section).")
        if "pads" not in run.data:
            problems.append("A structural drawing was given but the column bases were not read (read_pad_bases).")
        if "strip_layout" not in run.data:
            problems.append("A structural drawing was given but the strip layout was not read (read_strip_layout).")
    return problems
