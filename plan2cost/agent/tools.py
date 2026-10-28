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
    if name.startswith(("ext_girth_", "int_girth_")) and name.startswith("ext_girth_") and page and "confirmed" not in basis.lower():
        from plan2cost.dims import bbox_perimeter_m, dimension_tokens

        box = bbox_perimeter_m(dimension_tokens(run.pdf, int(page)))
        if box and abs(float(value) - box) <= 0.01 * box:
            fact["warning"] = (f"{value} m equals the perimeter of a plain rectangle ({box:.2f} m) from the overall dimensions. "
                               "Girth is only that when the plan has no recesses or terraces. Ask the user to confirm, or record the "
                               "centre-line girth with basis containing 'confirmed by user'.")
    fact["confidence"] = ("high" if source == "user" or fact.get("verified", "").startswith("quote found")
                          else "medium" if source == "drawing" else "low")
    run.facts = [f for f in run.facts if f["name"] != name]  # the latest value for a name replaces the earlier one
    run.facts.append(fact)
    if entry["status"] == "open":
        entry["status"] = "assumed" if source == "assumed" else "proven"
    return {"recorded": fact, "warning": fact.get("warning"), "open_items": [c["id"] for c in run.checklist if c["status"] == "open"]}


def sum_lengths(run: Run, values_m: list, label: str = "") -> dict:
    """Add lengths. The model never does arithmetic: use this."""
    return {"label": label, "sum_m": round(sum(float(v) for v in values_m), 3)}


def assume_floor_like_ground(run: Run, floor: str) -> dict:
    """Fallback when an upper floor's walls cannot be read reliably: assume it repeats the ground floor's external and internal girth.
    Recorded as an assumption with the reason, so it is flagged in the BoQ. There is no rule of thumb behind it and no invented dimension."""
    facts = {f["name"]: f for f in run.facts}
    if "ext_girth_ground_m" not in facts or "int_girth_ground_m" not in facts:
        return {"error": "The ground floor girth must be recorded first."}
    item = next((c["id"] for c in run.checklist if floor in c["question"].lower() and "girth" in c["question"].lower()), facts["ext_girth_ground_m"]["item"])
    out = {}
    for kind in ("ext", "int"):
        r = record_fact(run, item=item, name=f"{kind}_girth_{floor}_m", value=facts[f"{kind}_girth_ground_m"]["value"], unit="m", source="assumed",
                        basis=f"{floor} floor walls could not be read from its plan; assumed to repeat the ground floor")
        out[kind] = r.get("error") or "recorded"
    return {"floor": floor, "assumed_like_ground": True, **out}


def sum_lengths(run: Run, values_m: list, label: str = "") -> dict:
    """Add lengths. The model never does arithmetic: use this."""
    return {"label": label, "sum_m": round(sum(float(v) for v in values_m), 3)}


def estimate_girth_from_footprint(run: Run, floor: str, length_m: float, width_m: float, wall_mm: int = 230) -> dict:
    """Fallback when the plan cannot be walked grid by grid: the building's overall length and width (printed on the drawing, or
    the footprint the user knows) give the external centre-line girth of a plain rectangle. Internal walls are estimated from the
    floor area with the default ratio in data/defaults.json. Record both as source "assumed" with this tool as the basis."""
    import json
    from pathlib import Path

    t = wall_mm / 1000
    ext = 2 * ((length_m - t) + (width_m - t))  # centre-line of a rectangle whose overall dimensions are outside to outside
    ratio = json.loads(Path("data/defaults.json").read_text())["estimate"]["internal_wall_m_per_m2_floor"]
    internal = round(length_m * width_m * ratio["value"], 2)
    return {"floor": floor, "ext_girth_m": round(ext, 2), "int_girth_m": internal,
            "basis": f"plain rectangle {length_m} x {width_m} m, {wall_mm}mm walls; internal at {ratio['value']} m per m2 ({ratio['basis']})"}


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
    unresolved = [f["name"] for f in run.facts if f.get("warning")]
    if unresolved:
        problems.append(f"Facts with an unresolved warning: {unresolved}. Ask the user to confirm them.")
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
    """Wall girth for one floor from a floor-plan page, measured: scale and grid from the PDF, walls from the page image, external and
    internal split by what is outdoors. Approximate (record it as source "computed"); if the page has no readable grid it says so and
    you should use estimate_girth_from_footprint."""
    from plan2cost.measure import measure_walls

    m = measure_walls(run.pdf, int(page))
    if m.get("error"):
        return m
    return {"floor": floor, "ext_girth_m": float(m["external_m"]), "int_girth_m": float(m["internal_m"]), "walls": m["walls"],
            "junction_ends": m["junction_ends"], "scale": m["scale"], "note": "approximate: measured from the image; typically within about 10 percent on clean CAD plans"}


def read_notes(run: Run, pages: list | None = None) -> dict:
    """Specification notes (roof sheet, timber, ceiling, floor finish, slab thickness...) from the pages' text, each with its exact
    quote already checked against the page. Default pages: sections, details, roof plans and elevations. Record the ones you need
    with record_fact (source drawing) using the page and the quote."""
    from plan2cost.notes import extract_notes

    pages = [int(p) for p in pages] if pages else [p["page"] for p in run.pages if p["role"] in ("section", "detail", "roof_plan", "elevation")]
    if not pages:
        return {"error": "No pages to read; run index_document first or give page numbers."}
    out = extract_notes(run.pdf, pages)
    run.data["notes"] = out["notes"]
    return out


def compute_foundation(run: Run, block_mm: int = 230) -> dict:
    """Strip foundation from the ground floor walls when no foundation layout is given: trench girth is the ground floor wall girth less
    the overlaps at joints, trench width is three times the block thickness, depths are flagged defaults. Needs the facts
    ext_girth_ground_m and int_girth_ground_m (and, if known, junction_ends_ground). Items are added to the BoQ by compute_boq."""
    from plan2cost.boq import foundation_boq, strip_inputs
    from plan2cost.tools.foundation import GridLine, foundation_takeoff

    facts = {f["name"]: f["value"] for f in run.facts}
    if "ext_girth_ground_m" not in facts or "int_girth_ground_m" not in facts:
        return {"error": "Record ext_girth_ground_m and int_girth_ground_m first (read_wall_girth on the ground floor plan)."}
    total = float(facts["ext_girth_ground_m"]) + float(facts["int_girth_ground_m"])
    overlaps = float(facts.get("junction_ends_ground", 0)) * block_mm / 1000
    section, log, grade = strip_inputs(drawn={"block_mm": block_mm})
    for a in log:
        if a.source == "assumed":
            run.assumptions.append({"name": f"foundation_{a.name}", "value": a.value, "basis": a.basis})
    t = foundation_takeoff([GridLine("ground floor walls", runs=[(total, 1)], deductions=[(overlaps, 1)] if overlaps else [])], [], section)
    items = foundation_boq(t, section, grade)
    run.data["foundation_items"] = [i.__dict__ for i in items]
    return {"trench_girth_m": round(total - overlaps, 2), "trench_width_mm": section.width_mm, "lines": [f"{i.key} {i.qty} {i.unit}" for i in items],
            "assumed": [f"{a.name}={a.value}" for a in log if a.source == "assumed"]}


def compute_boq(run: Run) -> dict:
    """Wall blockwork and priced BoQ lines from recorded facts: girth per floor (facts named ext_girth_<floor>_m and
    int_girth_<floor>_m), storey heights and the openings read from the drawings."""
    from plan2cost.boq import price_boq, superstructure_boq
    from plan2cost.tools.walls import Opening

    ext = {f["name"][len("ext_girth_"):-2]: float(f["value"]) for f in run.facts if f["name"].startswith("ext_girth_") and f["name"].endswith("_m")}
    internal = {f["name"][len("int_girth_"):-2]: float(f["value"]) for f in run.facts if f["name"].startswith("int_girth_") and f["name"].endswith("_m")}
    if not ext or not internal:
        return {"error": "Record the external and internal girth per floor first, as facts named ext_girth_<floor>_m and int_girth_<floor>_m."}
    problems = [f"{f}: internal girth is {g} m, which is not plausible for a floor with rooms" for f, g in internal.items() if g <= 0]
    problems += [f"{f}: external girth is {g} m, which is not plausible" for f, g in ext.items() if g <= 0]
    if len(ext) > 1:
        top, low = max(ext.values()), min(ext.values())
        if low < 0.6 * top:
            problems.append(f"External girth differs too much between floors ({ext}); upper floors are normally close to the ground floor.")
    if problems:
        return {"error": "Implausible girth. Re-read the plan, or use assume_floor_like_ground for an upper floor. Do not ask the user about girth.", "problems": problems}
    heights = run.data.get("heights") or {}
    missing = [f for f in ext if f not in heights]
    if missing:
        return {"error": f"No storey height for {missing}. Read the levels, record an assumed height, or ask the user."}
    openings = [Opening(**o) for o in run.data.get("openings", [])]
    items = superstructure_boq(ext, internal, heights, openings)
    from plan2cost.boq import BoqItem

    items += [BoqItem(**d) for d in run.data.get("foundation_items", [])]
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
    "sum_lengths": (sum_lengths, "values_m: [numbers], label: str: add lengths for you; never add numbers yourself"),
    "assume_floor_like_ground": (assume_floor_like_ground, "floor: str: fallback for an upper floor whose walls cannot be read: assume it repeats the ground floor (flagged as an assumption)"),
    "ask_user": (ask_user, 'item: "C1", question: str: pause for a person'),
    "read_notes": (read_notes, "pages: [int] optional: specification notes (roof, ceiling, floor finish, slab...) with checked quotes"),
    "read_wall_girth": (read_wall_girth, 'page: int (a floor plan page), floor: "ground"|"first"|...: wall girth from the plan; record it as source "computed"'),
    "compute_foundation": (compute_foundation, "block_mm: int (default 230): strip foundation from the ground floor walls; run after the ground girth is recorded, before compute_boq"),
    "compute_boq": (compute_boq, "no args: wall areas and priced lines from the recorded facts"),
    "submit_boq": (submit_boq, 'summary: str: the gate; refused unless everything is settled'),
}
