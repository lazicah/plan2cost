"""Bookkeeping tools: the checklist, facts with their evidence, assumptions and questions to the user. Every fact is checked on the way in:
a value read from the drawings must carry a quote that is really on the page."""
import re

from plan2cost.kit.progress import Run

SOURCES = ("drawing", "assumed", "user", "computed")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).translate(str.maketrans({"’": "'", "–": "-", "—": "-", " ": " "}))).strip().lower()


def quote_on_page(quote: str, page_text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 3 and q in _norm(page_text)


def set_checklist(run: Run, items: list) -> dict:
    if not 3 <= len(items) <= 12:
        return {"error": "Give 3 to 12 checklist items: each a question about the drawings that must be settled to cost the building."}
    run.checklist = [{"id": f"C{i}", "question": it["question"], "evidence": it.get("evidence", ""), "status": "open"} for i, it in enumerate(items, 1)]
    from plan2cost.takeoff.checklist import trades_missing

    missing = trades_missing([f"{it['question']} {it.get('evidence', '')}" for it in items])
    return {"checklist": run.checklist, **({"trades_not_in_your_checklist": missing,
                                            "note": "These trades are part of a house estimate. Add an item for each you can settle, or leave it out on purpose: the estimate will then say it does not cover it."} if missing else {})}


def record_fact(run: Run, item: str, name: str, value, unit: str = "", source: str = "drawing", page: int | None = None,
                quote: str = "", basis: str = "", file: str = "main") -> dict:
    """Record one value against a checklist item. A value read from the drawings needs the page and the exact printed text; one
    that is assumed needs the basis; one the user gave is recorded as theirs."""
    entry = next((c for c in run.checklist if c["id"] == item), None)
    if not entry:
        return {"error": f"No checklist item {item}. Items: {[c['id'] for c in run.checklist]}"}
    if source not in SOURCES:
        return {"error": f"source must be one of {SOURCES}"}
    fact = {"item": item, "name": name, "value": value, "unit": unit, "source": source, "page": page, "quote": quote, "basis": basis, "file": file}
    if source == "drawing":
        if not page or not quote:
            return {"error": "A value from the drawings needs the page number and the exact printed text (quote)."}
        from plan2cost.kit.pdf import page_text

        text = page_text(run.structural_pdf if file == "structural" and run.structural_pdf else run.pdf, int(page))
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
        from plan2cost.drawing.dims import bbox_perimeter_m, dimension_tokens

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


def ask_user(run: Run, item: str, question: str) -> dict:
    """Pause the run for a person. Use it when the drawings do not settle an item and no standard default is safe."""
    run.pending = {"item": item, "question": question}
    run.status = "needs_input"
    entry = next((c for c in run.checklist if c["id"] == item), None)
    if entry:
        entry["status"] = "escalated"
    return {"paused": True, "question": question}


def foundation_item(run: Run) -> str:
    """The checklist item that foundation facts are recorded against."""
    return next((c["id"] for c in run.checklist if "foundation" in c["question"].lower()), run.checklist[0]["id"] if run.checklist else "C1")


TOOLS = {
    "set_checklist": (set_checklist, 'items: [{"question": str, "evidence": str}], 3 to 12 questions that must be settled to cost the building'),
    "record_fact": (record_fact, 'item: "C1", name: str, value, unit: str, source: "drawing"|"assumed"|"user"|"computed", page: int, quote: exact printed text, basis: str (assumed and computed)'),
    "sum_lengths": (sum_lengths, "values_m: [numbers], label: str: add lengths for you; never add numbers yourself"),
    "assume_floor_like_ground": (assume_floor_like_ground, "floor: str: fallback for an upper floor whose walls cannot be read: assume it repeats the ground floor (flagged as an assumption)"),
    "ask_user": (ask_user, 'item: "C1", question: str: pause for a person'),
}
