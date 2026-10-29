"""Tool that measures the roof: the plan by code from the vector roof plan, the pitch and specification from the section's printed levels and notes."""
import re
from dataclasses import asdict

from plan2cost.drawing.roof import draw_roof, measure_roof
from plan2cost.facts.roof_spec import read_roof_spec
from plan2cost.kit.progress import Run


def read_roof(run: Run) -> dict:
    """The roof: plan area under it, eaves, ridges, hips and valleys measured from the vector roof plan (scale fixed from its printed overall dimensions), and
    the pitch from the printed apex and eaves levels on a section over the plan's half-span. The covering and the timber sizes and spacings are read from the
    section's specification note. Roof quantities are made in compute_boq. A raster roof plan cannot be measured this way: ask the user."""
    pages = [p["page"] for p in run.pages if p["role"] == "roof_plan"]
    if not pages:
        return {"error": "No roof plan in this set. Ask the user for the roof pitch and size, or leave the roof out (the estimate will say so)."}
    roof = measure_roof(run.pdf, pages[0])
    if roof is None or not roof.plan_area_m2:
        return {"error": "The roof plan is not a vector drawing or its scale could not be fixed. Ask the user for the roof pitch and plan size.", "detail": (roof.scale_basis if roof else "")}
    spec = read_roof_spec(run.pdf, [p["page"] for p in run.pages if p["role"] in ("section", "elevation")] or None)
    models = run.dir / "models"
    models.mkdir(parents=True, exist_ok=True)
    markup = f"models/roof_p{pages[0]}.jpg"
    draw_roof(run.pdf, pages[0], roof, str(run.dir / markup))
    for w in roof.warnings:
        run.assumptions.append({"name": f"roof_check_{re.sub(r'[^a-z]+', '_', w.lower())[:30]}", "value": "open", "basis": w})
    run.data["roof"] = {"page": pages[0], "roof": asdict(roof), "spec": asdict(spec) if spec else None, "markup": markup}
    return {"page": pages[0], "scale": roof.scale_basis, "plan_area_m2": roof.plan_area_m2, "eaves_m": roof.eaves_m, "ridges_m": roof.ridges_m, "hips_m": roof.hips_m,
            "valleys_m": roof.valleys_m, "not_told_apart_m": roof.unsorted_m, "half_span_mm": roof.half_span_mm, "levels": spec.levels if spec else None,
            "covering": spec.covering if spec else None, "members": {k: v["quote"] for k, v in (spec.members if spec else {}).items()}, "checks": roof.warnings,
            "markup": markup, "confidence": roof.confidence}


TOOLS = {
    "read_roof": (read_roof, "no args: roof plan area, eaves, ridges, hips and valleys from the roof plan, pitch and timber specification from the section (after index_document)"),
}
