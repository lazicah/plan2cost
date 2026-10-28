"""Tools the agent can call. Each takes the Run and its arguments and returns a JSON-able dict.

The checks live inside the tools, so the agent cannot skip them: a fact's quote must be on the page, the submit gate refuses an
unsettled checklist, and every number in the BoQ comes from deterministic code, never from the model."""
import json
import re
from pathlib import Path

from plan2cost.agent.state import Run

SOURCES = ("drawing", "assumed", "user", "computed")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).translate(str.maketrans({"’": "'", "–": "-", "—": "-", " ": " "}))).strip().lower()


def quote_on_page(quote: str, page_text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 3 and q in _norm(page_text)


# ---- bookkeeping tools ------------------------------------------------------

def set_checklist(run: Run, items: list) -> dict:
    if not 3 <= len(items) <= 12:
        return {"error": "Give 3 to 12 checklist items: each a question about the drawings that must be settled to cost the building."}
    run.checklist = [{"id": f"C{i}", "question": it["question"], "evidence": it.get("evidence", ""), "status": "open"} for i, it in enumerate(items, 1)]
    return {"checklist": run.checklist}


def record_fact(run: Run, item: str, name: str, value, unit: str = "", source: str = "drawing", page: int | None = None,
                quote: str = "", basis: str = "") -> dict:
    """Record one value against a checklist item. A value read from the drawings needs the page and the exact printed text; one
    that is assumed needs the basis; one the user gave is recorded as theirs."""
    entry = next((c for c in run.checklist if c["id"] == item), None)
    if not entry:
        return {"error": f"No checklist item {item}. Items: {[c['id'] for c in run.checklist]}"}
    if source not in SOURCES:
        return {"error": f"source must be one of {SOURCES}"}
    fact = {"item": item, "name": name, "value": value, "unit": unit, "source": source, "page": page, "quote": quote, "basis": basis}
    if source == "drawing":
        if not page or not quote:
            return {"error": "A value from the drawings needs the page number and the exact printed text (quote)."}
        from plan2cost.pdf import page_text

        text = page_text(run.pdf, int(page))
        if text.strip():
            if not quote_on_page(quote, text):
                return {"error": f"Refused: the quote {quote!r} is not on page {page}. Copy the printed text exactly."}
            fact["verified"] = "quote found on the page"
        else:
            fact["verified"] = "page has no text layer; read by the model, not checkable"
    elif source == "computed":
        if not basis:
            return {"error": "A computed value needs the basis: which tool produced it and from what."}
        fact["verified"] = "derived by code from values the model read; approximate until checked"
    elif source == "assumed":
        if not basis:
            return {"error": "An assumed value needs the basis (the standard or default it comes from)."}
        run.assumptions.append({"name": name, "value": value, "basis": basis})
    run.facts.append(fact)
    if entry["status"] == "open":
        entry["status"] = "assumed" if source == "assumed" else "proven"
    return {"recorded": fact, "open_items": [c["id"] for c in run.checklist if c["status"] == "open"]}


def ask_user(run: Run, item: str, question: str) -> dict:
    """Pause the run for a person. Use it when the drawings do not settle an item and no standard default is safe."""
    run.pending = {"item": item, "question": question}
    run.status = "needs_input"
    entry = next((c for c in run.checklist if c["id"] == item), None)
    if entry:
        entry["status"] = "escalated"
    return {"paused": True, "question": question}


def submit_boq(run: Run, summary: str = "") -> dict:
    """The gate. Refused unless every checklist item is settled, a BoQ has been computed, and nothing is waiting on a person."""
    problems = []
    open_items = [c["id"] for c in run.checklist if c["status"] in ("open", "escalated")]
    if not run.checklist:
        problems.append("No checklist has been set.")
    if open_items:
        problems.append(f"Items not settled: {open_items}. Record a fact for each, or ask the user.")
    if run.pending:
        problems.append("A question to the user is still open.")
    if "boq" not in run.data:
        problems.append("No BoQ has been computed yet (compute_boq).")
    if problems:
        return {"refused": problems}
    run.status = "done"
    run.result = {"summary": summary, "boq": run.data["boq"], "assumptions": run.assumptions}
    (run.dir).mkdir(parents=True, exist_ok=True)
    (run.dir / "boq.json").write_text(json.dumps(run.result, indent=2))
    return {"filed": True}


# ---- tools that read the drawings (these call the Meta models) -------------------

def index_document(run: Run) -> dict:
    from plan2cost.document import classify_pages, index_pages

    run.pages = classify_pages(index_pages(run.pdf))
    roles: dict = {}
    for p in run.pages:
        roles.setdefault(p["role"], []).append(p["page"])
    return {"pages": len(run.pages), "roles": roles}


def read_openings(run: Run) -> dict:
    """Door and window types, sizes and quantities from the schedule pages."""
    from plan2cost.document import extract_openings, to_openings

    pages = [p["page"] for p in run.pages if p["role"] == "opening_schedule"]
    if not pages:
        return {"error": "No opening schedule in this set. Use read_plan_openings, or ask the user."}
    data = extract_openings(run.pdf, pages, str(run.dir / "scratch"))
    ops, questions = to_openings(data)
    run.data["openings"] = [o.__dict__ for o in ops]
    return {"openings": [f"{o.label} {o.kind} {int(o.width_m*1000)}x{int(o.height_m*1000)} x{o.count} {'external' if o.external else 'internal'}" for o in ops],
            "pages": pages, "questions": questions}


def read_levels(run: Run) -> dict:
    from plan2cost.document import extract_levels, storey_heights_m

    pages = [p["page"] for p in run.pages if p["role"] == "section"][:2]
    if not pages:
        return {"error": "No section in this set; storey height must come from the user or a default."}
    data = extract_levels(run.pdf, pages, str(run.dir / "scratch"))
    run.data["heights"] = storey_heights_m(data)
    return {"levels": data.get("levels"), "storey_heights_m": run.data["heights"], "questions": data.get("questions", [])}


def read_wall_girth(run: Run, page: int, floor: str) -> dict:
    """Wall girth for one floor from a floor-plan page: the model reads wall runs and how each was dimensioned
    (centre-line, end-to-end, in-to-in); code converts them to centre-line girth. Approximate: record it as source "computed"."""
    from plan2cost.extract import extract_walls_image, to_runs
    from plan2cost.pdf import render_pages
    from plan2cost.tools.takeoff import girth

    img = render_pages(run.pdf, [int(page)], str(run.dir / "scratch"), dpi=200)[0]
    runs, questions = to_runs(extract_walls_image(img, floor))
    g = girth(runs)
    ext = sum(v for k, v in g.items() if k.startswith("ext_girth_"))
    internal = sum(v for k, v in g.items() if k.startswith("int_girth_"))
    return {"floor": floor, "ext_girth_m": round(ext, 2), "int_girth_m": round(internal, 2), "wall_runs": len(runs), "questions": questions}


def compute_boq(run: Run) -> dict:
    """Wall blockwork and priced BoQ lines from recorded facts: girth per floor (facts named ext_girth_<floor>_m and
    int_girth_<floor>_m), storey heights and the openings read from the drawings."""
    from plan2cost.boq import price_boq, superstructure_boq
    from plan2cost.tools.walls import Opening

    ext = {f["name"][len("ext_girth_"):-2]: float(f["value"]) for f in run.facts if f["name"].startswith("ext_girth_") and f["name"].endswith("_m")}
    internal = {f["name"][len("int_girth_"):-2]: float(f["value"]) for f in run.facts if f["name"].startswith("int_girth_") and f["name"].endswith("_m")}
    if not ext or not internal:
        return {"error": "Record the external and internal girth per floor first, as facts named ext_girth_<floor>_m and int_girth_<floor>_m."}
    heights = run.data.get("heights") or {}
    missing = [f for f in ext if f not in heights]
    if missing:
        return {"error": f"No storey height for {missing}. Read the levels, record an assumed height, or ask the user."}
    openings = [Opening(**o) for o in run.data.get("openings", [])]
    items = superstructure_boq(ext, internal, heights, openings)
    rates = json.loads(Path("data/rates.json").read_text())
    priced = price_boq(items, rates)
    run.data["boq"] = {"items": [i.__dict__ for i in items], **priced}
    return {"lines": len(items), "total": priced["total"], "currency": priced["currency"], "unpriced": priced["unpriced"]}


TOOLS = {
    "set_checklist": (set_checklist, 'items: [{"question": str, "evidence": str}], 3 to 12 questions that must be settled to cost the building'),
    "index_document": (index_document, "no args: classify every page of the drawing set"),
    "read_openings": (read_openings, "no args: door and window types from the schedule pages"),
    "read_levels": (read_levels, "no args: storey heights from the sections"),
    "record_fact": (record_fact, 'item: "C1", name: str, value, unit: str, source: "drawing"|"assumed"|"user"|"computed", page: int, quote: exact printed text, basis: str (assumed and computed)'),
    "ask_user": (ask_user, 'item: "C1", question: str: pause for a person'),
    "read_wall_girth": (read_wall_girth, 'page: int (a floor plan page), floor: "ground"|"first"|...: wall girth from the plan; record it as source "computed"'),
    "compute_boq": (compute_boq, "no args: wall areas and priced lines from the recorded facts"),
    "submit_boq": (submit_boq, 'summary: str: the gate; refused unless everything is settled'),
}
