"""What the console shows: a run's turns, derived from its saved messages."""
import json
import re

from plan2cost.agent.state import RUNS_DIR, Run

RESULT = "Tool result: "
RUN_ID = re.compile(r"^\d{8}-\d{6}$")


def turns(run: Run) -> list[dict]:
    """One entry per model turn: the tool it called, why, and what came back. User answers appear as their own entries."""
    out, pending = [], None
    for m in run.messages[2:]:  # skip the system prompt and the objective
        if m["role"] == "assistant":
            try:
                a = json.loads(re.search(r"\{.*\}", m["content"], re.S).group(0))
            except (AttributeError, ValueError):
                a = {}
            pending = {"tool": a.get("tool", "(invalid reply)"), "args": a.get("args") or {}, "reason": a.get("reason", "")}
        elif m["content"].startswith(RESULT) and pending:
            try:
                pending["result"] = json.loads(m["content"][len(RESULT):])
            except ValueError:
                pending["result"] = {"raw": m["content"][len(RESULT):][:500]}
            out.append(pending)
            pending = None
        elif m["content"].startswith("The user answered:"):
            out.append({"tool": "user_answer", "args": {}, "reason": "", "result": {"answer": m["content"].split("\n")[0][len("The user answered: "):]}})
    return out


def summary(run: Run) -> dict:
    return {"id": run.id, "status": run.status, "turn": run.turn, "objective": run.objective, "pdf": run.pdf, "checklist": run.checklist,
            "facts": run.facts, "assumptions": run.assumptions, "pending": run.pending, "result": run.result,
            "boq": run.data.get("boq"), "models": run.data.get("models", {}), "turns": turns(run)}


def list_runs() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    rows = []
    for d in sorted((p for p in RUNS_DIR.iterdir() if p.is_dir() and RUN_ID.match(p.name)), reverse=True):
        try:
            r = Run.load(d.name)
            rows.append({"id": r.id, "status": r.status, "turn": r.turn, "pdf": r.pdf})
        except (OSError, ValueError, TypeError):
            continue
    return rows
