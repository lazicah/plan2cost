"""What the console shows: a run's turns, derived from its saved messages."""
import json
import re
from pathlib import Path

from plan2cost.kit.progress import RUNS_DIR, Run

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


# The stages of an estimate, in the order the agent normally does them: (label, the tools that complete it, when it applies)
STAGES = [("Index the pages", {"index_document"}, "always"), ("Set the checklist", {"set_checklist"}, "always"),
          ("Schedules, levels, notes", {"read_openings", "read_levels", "read_notes"}, "always"), ("Walls, floor by floor", {"read_wall_girth"}, "always"),
          ("Doors and windows on the plan", {"locate_openings"}, "always"), ("Structural drawing", {"read_foundation_section", "read_pad_bases", "read_strip_layout"}, "structural"),
          ("Foundation", {"compute_foundation"}, "always"), ("Priced bill", {"compute_boq"}, "always"), ("Quote audit", {"audit_quote"}, "quote"), ("Filed", {"submit_boq"}, "always")]


def stages(run: Run, done_turns: list[dict], now: dict | None) -> list[dict]:
    """Progress for the console: each stage is done (a tool of it returned without error), active (the agent is in it) or waiting."""
    ok = [t["tool"] for t in done_turns if not ({"error", "refused"} & set((t.get("result") or {})) )]
    out = []
    for label, tools, when in STAGES:
        if (when == "structural" and not run.structural_pdf) or (when == "quote" and not run.quote):
            continue
        n = sum(1 for x in ok if x in tools)
        out.append({"label": label, "done": n >= len(tools) if label == "Structural drawing" else n > 0, "count": n, "active": bool(now and now["tool"] in tools)})
    first_open = next((s for s in out if not s["done"]), None)
    if first_open and not any(s["active"] for s in out) and run.status == "running":
        first_open["active"] = True
    return out


def built(run: Run) -> dict:
    """The components of the estimate that exist so far, for the console's live panel."""
    d = run.data
    opened = {f: sum(c["external"] + c["internal"] for c in counts.values()) for f, counts in (d.get("located_openings") or {}).items()}
    boq = d.get("boq")
    return {"walls": {f: {k: m.get(k) for k in ("walls", "total_m", "external_m", "internal_m", "route", "confidence", "markup")} for f, m in (d.get("models") or {}).items()},
            "openings_found": opened, "openings_scheduled": sum(o["count"] for o in d.get("openings", [])), "pads": len(d.get("pads", [])),
            "strip": ({k: d["strip_layout"][k] for k in ("gross_m", "net_m")} if d.get("strip_layout") else None), "foundation_lines": len(d.get("foundation_items", [])),
            "boq": ({"lines": len(boq["items"]), "total": boq["total"], "currency": boq["currency"]} if boq else None)}


def ensure_thumbs(run: Run) -> None:
    """Runs made before thumbnails existed get them the first time the console opens them."""
    if not (run.dir / "pages").is_dir() and run.pdf and Path(run.pdf).is_file():
        from plan2cost.kit.pdf import page_count, render_pages

        render_pages(run.pdf, list(range(1, page_count(run.pdf) + 1)), str(run.dir / "pages"), dpi=60)


def summary(run: Run) -> dict:
    ensure_thumbs(run)
    done_turns, now = turns(run), in_flight(run)
    d = run.dir
    tender = json.loads((d / "tender_audit.json").read_text()) if (d / "tender_audit.json").exists() else None
    files = [f for f in ("bill_priced.xlsx", "bill_priced.pdf", "bill_unpriced.xlsx", "bill_unpriced.pdf", "boq.json", "tender_audit.json") if (d / f).exists()]
    return {"id": run.id, "status": run.status, "stages": stages(run, done_turns, now), "now": now, "pages": run.pages, "thumbs": sorted(f.name for f in (d / "pages").glob("p*.jpg")) if (d / "pages").is_dir() else [], "built": built(run), "preview": run.data.get("preview"), "error": run.data.get("error"), "files": files, "tender": tender,
            "structural": run.structural_pdf, "quote": run.quote, "turn": run.turn, "objective": run.objective, "pdf": run.pdf, "checklist": run.checklist,
            "facts": run.facts, "assumptions": run.assumptions, "pending": run.pending, "result": run.result,
            "boq": run.data.get("boq"), "models": run.data.get("models", {}), "audit": run.data.get("audit"), "turns": done_turns}


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
