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
        from plan2cost.pdf import page_text

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
    if run.structural_pdf:
        if not any(f["name"].startswith("fdn_") and f.get("file") == "structural" for f in run.facts):
            problems.append("A structural drawing was given but the foundation section was not read (read_foundation_section).")
        if "pads" not in run.data:
            problems.append("A structural drawing was given but the column bases were not read (read_pad_bases).")
        if "strip_layout" not in run.data:
            problems.append("A structural drawing was given but the strip layout was not read (read_strip_layout).")
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
    for an upper floor use assume_floor_like_ground."""
    from plan2cost.measure import measure_walls

    m = measure_walls(run.pdf, int(page))
    if m.get("error"):
        return m
    return {"floor": floor, "ext_girth_m": float(m["external_m"]), "int_girth_m": float(m["internal_m"]), "walls": m["walls"],
            "junction_ends": m["junction_ends"], "building_length_m": float(m["length_m"]), "building_width_m": float(m["width_m"]),
            "scale": m["scale"], "note": "approximate: measured from the image; typically within about 10 percent on clean CAD plans"}


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


def read_foundation_section(run: Run) -> dict:
    """Layers and dimensions of the strip foundation cross-section on the structural drawing (footing width and thickness, blinding, slab,
    filling, overall depth). Every number is checked to be printed on the page and the layers are checked to add up to the overall depth.
    The verified values are recorded as facts (source drawing, file structural) against the foundation checklist item."""
    import re

    from plan2cost.pdf import page_count, page_text
    from plan2cost.structural import read_foundation_section as read

    if not run.structural_pdf:
        return {"error": "No structural drawing was given for this run."}
    page = next((p for p in range(1, page_count(run.structural_pdf) + 1)
                 if re.search(r"SECTION\s*A\s*-\s*A", page_text(run.structural_pdf, p), re.I) and re.search(r"FOUNDATION|BLINDING", page_text(run.structural_pdf, p), re.I)), None)
    if not page:
        return {"error": "No foundation section found in the structural drawing."}
    out = read(run.structural_pdf, page, str(run.dir / "scratch"))
    item = next((c["id"] for c in run.checklist if "foundation" in c["question"].lower()), run.checklist[0]["id"] if run.checklist else "C1")
    names = {"footing_width_mm": "fdn_footing_width_mm", "footing_thickness_mm": "fdn_footing_thickness_mm", "blinding_mm": "fdn_blinding_mm",
             "slab_mm": "fdn_slab_mm", "fill_depth_mm": "fdn_fill_depth_mm", "overall_depth_mm": "fdn_overall_depth_mm"}
    recorded = []
    for key, v in out["values"].items():
        if key in names:
            r = record_fact(run, item=item, name=names[key], value=v, unit="mm", source="drawing", page=page, quote=str(int(v)), file="structural")
            recorded.append(names[key] if "error" not in r else f"{names[key]} (refused: {r['error']})")
    return {"page": page, "recorded": recorded, "layers_close": out["layers_close"], "questions": out["questions"]}


def read_pad_bases(run: Run) -> dict:
    """Column base (pad) types from the structural drawing: size, thickness, number of each and the bar note. The model reads the base
    detail sheets; each size and count is kept only if it is printed on the page ("4no Thus")."""
    import re

    from plan2cost.extract_foundation import extract_foundation, to_pads
    from plan2cost.pdf import page_count, page_text, render_pages

    if not run.structural_pdf:
        return {"error": "No structural drawing was given for this run."}
    pages = [p for p in range(1, page_count(run.structural_pdf) + 1) if re.search(r"BASE\s*TYPE", page_text(run.structural_pdf, p), re.I)]
    if not pages:
        return {"error": "No column base details found in the structural drawing."}
    text = " ".join(page_text(run.structural_pdf, p) for p in pages)
    printed = set(re.findall(r"\d+", text))
    data = extract_foundation(render_pages(run.structural_pdf, pages, str(run.dir / "scratch"), dpi=130))
    pads, questions = to_pads(data)
    kept = []
    for p in pads:
        ok = str(int(p.length_m * 1000)) in printed and str(int(p.width_m * 1000)) in printed and re.search(rf"{p.count}\s*no", text, re.I)
        if ok:
            kept.append(p)
        else:
            questions.append(f"Base type {p.type}: size or number is not printed on the page, so it was not used.")
    run.data["pads"] = [p.__dict__ for p in kept]
    item = next((c["id"] for c in run.checklist if "foundation" in c["question"].lower()), run.checklist[0]["id"] if run.checklist else "C1")
    for p in kept:
        record_fact(run, item=item, name=f"pad_type_{p.type}", value=f"{p.length_m:g} x {p.width_m:g} m x {p.count}", source="drawing",
                    page=pages[0], quote=f"{p.count}no", file="structural")
    return {"pages": pages, "bases": [f"type {p.type}: {p.length_m:g} x {p.width_m:g} m, {p.thickness_m * 1000:.0f}mm thick, {p.count} no" for p in kept], "questions": questions}


def read_strip_layout(run: Run) -> dict:
    """Strip footing girth from the structural foundation layout (needs read_pad_bases first). The grid, printed bays and dashed footing edges
    give the runs; the column bases are taken out because they are dug as pits. Replaces the ground floor stand-in in compute_foundation."""
    import re

    from plan2cost.pdf import page_count, page_text
    from plan2cost.strip_layout import measure_strips

    if not run.structural_pdf:
        return {"error": "No structural drawing was given for this run."}
    if "pads" not in run.data:
        return {"error": "Read the column bases first (read_pad_bases): their sizes are taken out of the strip runs."}
    pages = [p for p in range(1, page_count(run.structural_pdf) + 1) if re.search(r"FOUNDATION\s*LAYOUT", page_text(run.structural_pdf, p), re.I)]
    if not pages:
        return {"error": "No foundation layout page found in the structural drawing."}
    sizes = {d["type"]: d["length_m"] for d in run.data["pads"]}
    layout = measure_strips(run.structural_pdf, pages[0], sizes)
    if not layout.runs:
        return {"error": f"No strip runs could be measured on page {pages[0]} ({layout.scale_basis or 'the page is not a vector drawing'}). Use the ground floor plan instead (compute_foundation)."}
    run.data["strip_layout"] = {"page": pages[0], "gross_m": layout.gross_m, "net_m": layout.net_m,
                                "floating_base_types": layout.floating_base_types, "scaled_runs": [f"{r.axis}{r.line} {r.start}-{r.end}" for r in layout.runs if r.basis != "printed"]}
    item = next((c["id"] for c in run.checklist if "foundation" in c["question"].lower()), run.checklist[0]["id"] if run.checklist else "C1")
    record_fact(run, item=item, name="strip_girth_m", value=layout.net_m, unit="m", source="computed", page=pages[0],
                basis=f"{len(layout.runs)} runs along grid lines, {layout.gross_m} m centre to centre less {round(layout.gross_m - layout.net_m, 2)} m inside the column bases", file="structural")
    return {"page": pages[0], "runs": [f"{r.axis} {r.line} {r.start}-{r.end}: {r.length_m} m less bases {r.bases_m} = {r.net_m}" for r in layout.runs],
            "gross_m": layout.gross_m, "net_m": layout.net_m, "scale": layout.scale_basis,
            "not_measured": f"{len(layout.floating_base_types)} base(s) off the grid (types {layout.floating_base_types}) and the strips serving them" if layout.floating_base_types else None}


def lookup_besmm(run: Run, query: str) -> dict:
    """Find what the BESMM4 rule book says about something to be measured (unit, what is included or deducted, what the item description must
    state). Returns page numbers and excerpts for you to read; say which page your rule comes from when you record a fact based on it."""
    from plan2cost.besmm import book_path, search

    if not book_path():
        return {"error": "The BESMM4 book is not available here (set P2C_BESMM_PDF). Say in the basis that the rule was not checked."}
    hits = search(query)
    return {"query": query, "pages": hits} if hits else {"query": query, "pages": [], "note": "No page carries all the words; try fewer or different words."}


def compute_foundation(run: Run, block_mm: int = 230) -> dict:
    """Strip foundation from the ground floor walls when no foundation layout is given: trench girth is the ground floor wall girth less
    the overlaps at joints, trench width is three times the block thickness, depths are flagged defaults. Needs the facts
    ext_girth_ground_m and int_girth_ground_m (and, if known, junction_ends_ground, building_length_m, building_width_m; with the lengths it also
    computes the ground bed, topsoil, blinding, formwork, disposal and backfill). Items are added to the BoQ by compute_boq."""
    from plan2cost.boq import foundation_boq, strip_inputs
    from plan2cost.tools.foundation import GridLine, foundation_takeoff

    facts = {f["name"]: f["value"] for f in run.facts}
    layout = run.data.get("strip_layout")
    if layout:  # the drawn strip layout beats the ground floor stand-in: blockwork runs the full length, the trench is net of the bases
        total, overlaps = float(layout["gross_m"]), float(layout["gross_m"]) - float(layout["net_m"])
    elif "ext_girth_ground_m" not in facts or "int_girth_ground_m" not in facts:
        return {"error": "Record ext_girth_ground_m and int_girth_ground_m first (read_wall_girth on the ground floor plan), or read the strip layout (read_strip_layout)."}
    else:
        total = float(facts["ext_girth_ground_m"]) + float(facts["int_girth_ground_m"])
        overlaps = float(facts.get("junction_ends_ground", 0)) * block_mm / 1000
    drawn = {"block_mm": block_mm}
    if "fdn_footing_width_mm" in facts:
        drawn["width_mm"] = float(facts["fdn_footing_width_mm"])
    if "fdn_footing_thickness_mm" in facts:
        drawn["footing_thickness_m"] = float(facts["fdn_footing_thickness_mm"]) / 1000
    if "fdn_overall_depth_mm" in facts:  # the printed overall depth is measured from the stripped level; topsoil is added back for the dig from ground level
        drawn["trench_depth_m"] = float(facts["fdn_overall_depth_mm"]) / 1000 + 0.15
    section, log, grade = strip_inputs(drawn=drawn)
    for a in log:
        if a.source == "assumed":
            run.assumptions.append({"name": f"foundation_{a.name}", "value": a.value, "basis": a.basis})
    from plan2cost.boq import foundation_extras, substructure_extras
    from plan2cost.tools.foundation import PadBase

    pads = [PadBase(**d) for d in run.data.get("pads", [])]
    t = foundation_takeoff([GridLine("ground floor walls", runs=[(total, 1)], deductions=[(overlaps, 1)] if overlaps else [])], pads, section)
    items = foundation_boq(t, section, grade)
    length, width = facts.get("building_length_m"), facts.get("building_width_m")
    if length and width:  # the author's slab area is the overall length x width; fills are that less the wall footprint
        slab = float(length) * float(width)
        items += foundation_extras(pads, grade, slab_area_m2=slab, fill_area_m2=slab - total * block_mm / 1000)
        extras = {i.key: i.qty for i in items}
        items += substructure_extras(t, section, pads, total - overlaps, float(length), float(width), extras)
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
    heights = dict(run.data.get("heights") or {})
    for f in run.facts:
        if f["name"].startswith("storey_height_") and f["name"].endswith("_m"):
            heights.setdefault(f["name"][len("storey_height_"):-2], float(f["value"]))
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
    "read_foundation_section": (read_foundation_section, "no args: foundation cross-section (footing, blinding, slab, filling, overall depth) from the structural drawing, when one is given"),
    "lookup_besmm": (lookup_besmm, "query: what to look up in the BESMM4 book, e.g. 'remove topsoil'; returns pages and excerpts"),
    "read_strip_layout": (read_strip_layout, "no args: strip footing girth from the structural foundation layout; call after read_pad_bases, before compute_foundation"),
    "read_pad_bases": (read_pad_bases, "no args: column base types (size, thickness, number) from the structural drawing, when one is given"),
    "compute_foundation": (compute_foundation, "block_mm: int (default 230): strip foundation from the ground floor walls; run after the ground girth is recorded, before compute_boq"),
    "compute_boq": (compute_boq, "no args: wall areas and priced lines from the recorded facts"),
    "submit_boq": (submit_boq, 'summary: str: the gate; refused unless everything is settled'),
}
