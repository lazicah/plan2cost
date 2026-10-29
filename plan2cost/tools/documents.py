"""Tools that read the set as a whole: what each page is, the opening schedule, storey heights and the specification notes. The model reads
printed text; code checks it."""
from plan2cost.kit.pdf import page_count, render_pages
from plan2cost.kit.progress import Run


def index_document(run: Run) -> dict:
    from plan2cost.facts.document import classify_pages, index_pages

    render_pages(run.pdf, list(range(1, page_count(run.pdf) + 1)), str(run.dir / "pages"), dpi=60)  # thumbnails for the console, shown while the model classifies
    run.pages = classify_pages(index_pages(run.pdf))
    roles: dict = {}
    for p in run.pages:
        roles.setdefault(p["role"], []).append(p["page"])
    return {"pages": len(run.pages), "roles": roles}


def read_openings(run: Run) -> dict:
    """Door and window types, sizes and quantities from the schedule pages."""
    from plan2cost.facts.document import extract_openings, to_openings

    pages = [p["page"] for p in run.pages if p["role"] == "opening_schedule"]
    if not pages:
        return {"error": "No opening schedule in this set. Use read_plan_openings, or ask the user."}
    data = extract_openings(run.pdf, pages, str(run.dir / "scratch"))
    ops, questions = to_openings(data)
    run.data["openings"] = [o.__dict__ for o in ops]
    return {"openings": [f"{o.label} {o.kind} {int(o.width_m*1000)}x{int(o.height_m*1000)} x{o.count} {'external' if o.external else 'internal'}" for o in ops],
            "pages": pages, "questions": questions}


def read_levels(run: Run) -> dict:
    from plan2cost.facts.document import extract_levels, storey_heights_m

    pages = [p["page"] for p in run.pages if p["role"] == "section"][:2]
    if not pages:
        return {"error": "No section in this set; storey height must come from the user or a default."}
    data = extract_levels(run.pdf, pages, str(run.dir / "scratch"))
    run.data["heights"] = storey_heights_m(data)
    return {"levels": data.get("levels"), "storey_heights_m": run.data["heights"], "questions": data.get("questions", [])}


def read_notes(run: Run, pages: list | None = None) -> dict:
    """Specification notes (roof sheet, timber, ceiling, floor finish, slab thickness...) from the pages' text, each with its exact
    quote already checked against the page. Default pages: sections, details, roof plans and elevations. Record the ones you need
    with record_fact (source drawing) using the page and the quote."""
    from plan2cost.facts.notes import extract_notes

    pages = [int(p) for p in pages] if pages else [p["page"] for p in run.pages if p["role"] in ("section", "detail", "roof_plan", "elevation")]
    if not pages:
        return {"error": "No pages to read; run index_document first or give page numbers."}
    out = extract_notes(run.pdf, pages)
    run.data["notes"] = out["notes"]
    return out


TOOLS = {
    "index_document": (index_document, "no args: classify every page of the drawing set"),
    "read_openings": (read_openings, "no args: door and window types from the schedule pages"),
    "read_levels": (read_levels, "no args: storey heights from the sections"),
    "read_notes": (read_notes, "pages: [int] optional: specification notes (roof, ceiling, floor finish, slab...) with checked quotes"),
}
