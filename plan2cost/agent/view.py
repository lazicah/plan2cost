"""What the console shows: a run's turns, derived from its saved messages."""
import json
import re

from plan2cost.kit import progress
from plan2cost.kit.progress import Run

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


def in_flight(run: Run) -> dict | None:
    """The tool the agent has asked for and has not heard back from yet: what it is doing right now (a plan read takes a minute or more)."""
    if run.status != "running" or not run.messages or run.messages[-1]["role"] != "assistant":
        return None
    try:
        a = json.loads(re.search(r"\{.*\}", run.messages[-1]["content"], re.S).group(0))
    except (AttributeError, ValueError):
        return None
    return {"tool": a.get("tool", ""), "args": a.get("args") or {}, "reason": a.get("reason", "")}


# The stages of an estimate: (label, the tools that complete it, when it applies)
STAGES = [("Read the floor plans", {"read_floor"}, "always"), ("Estimate", {"compute_boq"}, "always"), ("Quote audit", {"audit_quote"}, "quote"), ("Filed", {"submit_boq"}, "always")]


def stages(run: Run, done_turns: list[dict], now: dict | None) -> list[dict]:
    """Progress for the console: each stage is done (all it needs returned without error), active (the agent is in it) or waiting."""
    ok = [t["tool"] for t in done_turns if not ({"error", "refused"} & set((t.get("result") or {})))]
    out = []
    for label, tools, when in STAGES:
        if when == "quote" and not run.quote:
            continue
        n = sum(1 for x in ok if x in tools)
        need = len(run.floors) if label == "Read the floor plans" else 1
        out.append({"label": label, "done": n >= need, "count": n, "of": need if need > 1 else None, "active": bool(now and now["tool"] in tools)})
    first_open = next((s for s in out if not s["done"]), None)
    if first_open and not any(s["active"] for s in out) and run.status == "running":
        first_open["active"] = True
    return out


def built(run: Run) -> dict:
    """The components of the estimate that exist so far, for the console's live panel."""
    d = run.data
    boq = d.get("boq")
    return {"floors": {f: {"walls": m.get("walls"), "total_m": m.get("total_m"), "external_m": m.get("external_m"), "internal_m": m.get("internal_m"), "route": m.get("route"),
                           "confidence": m.get("confidence"), "markup": m.get("markup"), "doors": sum(o["count"] for o in (d.get("floors", {}).get(f, {}).get("openings") or []) if o["kind"] == "door"),
                           "windows": sum(o["count"] for o in (d.get("floors", {}).get(f, {}).get("openings") or []) if o["kind"] == "window")} for f, m in (d.get("models") or {}).items()},
            "working": (boq or {}).get("working"),
            "boq": ({"lines": len(boq["items"]), "total": boq["total"], "low": boq["total_low"], "high": boq["total_high"], "currency": boq["currency"], "estimated_share": boq["estimated_share"]} if boq else None)}


def summary(run: Run) -> dict:
    done_turns, now = turns(run), in_flight(run)
    d = run.dir
    tender = json.loads((d / "tender_audit.json").read_text()) if (d / "tender_audit.json").exists() else None
    files = [f for f in ("bill_priced.xlsx", "bill_priced.pdf", "bill_unpriced.xlsx", "bill_unpriced.pdf", "boq.json", "tender_audit.json") if (d / f).exists()]
    return {"id": run.id, "status": run.status, "stages": stages(run, done_turns, now), "now": now, "floors": run.floors, "inputs": run.inputs,
            "thumbs": sorted(f.name for f in (d / "pages").glob("p*.jpg")) if (d / "pages").is_dir() else [], "built": built(run), "preview": run.data.get("preview"),
            "error": run.data.get("error"), "files": files, "tender": tender, "quote": run.quote, "turn": run.turn, "objective": run.objective, "checklist": run.checklist,
            "facts": run.facts, "assumptions": run.assumptions, "pending": run.pending, "result": run.result, "boq": run.data.get("boq"), "models": run.data.get("models", {}),
            "audit": run.data.get("audit"), "turns": done_turns}


def list_runs() -> list[dict]:
    if not progress.RUNS_DIR.exists():
        return []
    rows = []
    for d in sorted((p for p in progress.RUNS_DIR.iterdir() if p.is_dir() and RUN_ID.match(p.name)), reverse=True):
        try:
            r = Run.load(d.name)
            rows.append({"id": r.id, "status": r.status, "turn": r.turn, "floors": [f["name"] for f in r.floors]})
        except (OSError, ValueError, TypeError):
            continue
    return rows
