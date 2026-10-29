"""Tools that read the structural drawing set: the foundation section, the column bases and the strip footing layout."""
import re

from plan2cost.drawing.strips import measure_strips
from plan2cost.facts.foundation_section import read_foundation_section as read
from plan2cost.facts.pad_bases import extract_foundation, to_pads
from plan2cost.kit.pdf import page_count, page_text, render_pages
from plan2cost.kit.progress import Run
from plan2cost.tools.records import foundation_item, record_fact


def read_foundation_section(run: Run) -> dict:
    """Layers and dimensions of the strip foundation cross-section on the structural drawing (footing width and thickness, blinding, slab,
    filling, overall depth). Every number is checked to be printed on the page and the layers are checked to add up to the overall depth.
    The verified values are recorded as facts (source drawing, file structural) against the foundation checklist item."""
    if not run.structural_pdf:
        return {"error": "No structural drawing was given for this run."}
    page = next((p for p in range(1, page_count(run.structural_pdf) + 1)
                 if re.search(r"SECTION\s*A\s*-\s*A", page_text(run.structural_pdf, p), re.I) and re.search(r"FOUNDATION|BLINDING", page_text(run.structural_pdf, p), re.I)), None)
    if not page:
        return {"error": "No foundation section found in the structural drawing."}
    out = read(run.structural_pdf, page, str(run.dir / "scratch"))
    item = foundation_item(run)
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
    item = foundation_item(run)
    for p in kept:
        record_fact(run, item=item, name=f"pad_type_{p.type}", value=f"{p.length_m:g} x {p.width_m:g} m x {p.count}", source="drawing",
                    page=pages[0], quote=f"{p.count}no", file="structural")
    return {"pages": pages, "bases": [f"type {p.type}: {p.length_m:g} x {p.width_m:g} m, {p.thickness_m * 1000:.0f}mm thick, {p.count} no" for p in kept], "questions": questions}


def read_strip_layout(run: Run) -> dict:
    """Strip footing girth from the structural foundation layout (needs read_pad_bases first). The grid, printed bays and dashed footing edges
    give the runs; the column bases are taken out because they are dug as pits. Replaces the ground floor stand-in in compute_foundation."""


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
    item = foundation_item(run)
    record_fact(run, item=item, name="strip_girth_m", value=layout.net_m, unit="m", source="computed", page=pages[0],
                basis=f"{len(layout.runs)} runs along grid lines, {layout.gross_m} m centre to centre less {round(layout.gross_m - layout.net_m, 2)} m inside the column bases", file="structural")
    return {"page": pages[0], "runs": [f"{r.axis} {r.line} {r.start}-{r.end}: {r.length_m} m less bases {r.bases_m} = {r.net_m}" for r in layout.runs],
            "gross_m": layout.gross_m, "net_m": layout.net_m, "scale": layout.scale_basis,
            "not_measured": f"{len(layout.floating_base_types)} base(s) off the grid (types {layout.floating_base_types}) and the strips serving them" if layout.floating_base_types else None}


TOOLS = {
    "read_foundation_section": (read_foundation_section, "no args: foundation cross-section (footing, blinding, slab, filling, overall depth) from the structural drawing, when one is given"),
    "read_pad_bases": (read_pad_bases, "no args: column base types (size, thickness, number) from the structural drawing, when one is given"),
    "read_strip_layout": (read_strip_layout, "no args: strip footing girth from the structural foundation layout; call after read_pad_bases, before compute_foundation"),
}
