"""Tools that interpret a floor plan: wall girth by code, and the doors, windows and openings tied to the walls they sit in."""
from plan2cost.kit.progress import Run


def read_wall_girth(run: Run, page: int, floor: str) -> dict:
    """Wall girth for one floor from a floor-plan page, measured by code: vector line work is read exactly, a raster page is read through the
    image route (the model reads the printed overall dimensions to fix the scale). Builds the drawing model for the floor (every wall with an id,
    the scale evidence, quality checks) and an annotated plan the user can check. The result says which route was used, how far to trust it
    (confidence high, medium or low) and which checks are open. External is the walls with outdoors on one side, which can differ from an
    outline-only convention. Record it as source "computed". For an upper floor use assume_floor_like_ground when the plan cannot be read."""
    from plan2cost.drawing.interpret import interpret_page
    from plan2cost.drawing.markup import model_for_page

    models_dir = run.dir / "models"
    try:
        def show(m):  # the measured walls, for the console, while the model review runs
            run.data["preview"] = {"floor": floor, "page": int(page), "markup": f"models/{m.markup}", "walls": len(m.walls()), "total_m": m.totals["total_m"],
                                   "external_m": m.totals["external_m"], "internal_m": m.totals["internal_m"], "route": m.route}
            run.save()

        model = model_for_page(run.pdf, int(page), floor, str(models_dir), review=True, on_measured=show)
    except ValueError as e:  # no route kept its walls: fall back to the plain measurement, without a drawing model
        m = interpret_page(run.pdf, int(page), str(run.dir / "scratch"))
        if m.get("error"):
            return {"error": m["error"], "detail": str(e)}
        return {"floor": floor, "ext_girth_m": float(m["external_m"]), "int_girth_m": float(m["internal_m"]), "walls": m["walls"], "junction_ends": m["junction_ends"],
                "building_length_m": float(m["length_m"]), "building_width_m": float(m["width_m"]), "route": m["route"], "confidence": "low",
                "note": "no drawing model could be built for this page; treat the girth as a rough estimate"}
    run.data.pop("preview", None)
    run.data.setdefault("models", {})[floor] = {"file": f"models/drawing_model_{floor}_p{int(page)}.json", "markup": f"models/{model.markup}", **model.summary()}
    open_checks = [i for i in model.issues if i.severity != "info"]
    for i in open_checks:  # open checks travel with the estimate so they cannot be lost at submit
        run.assumptions.append({"name": "_".join(["drawing_check", floor, i.code, *i.elements[:2]]), "value": "open", "basis": f"{i.message} {i.check}".strip()})
    t = model.totals
    ext = [e for e in model.walls() if e.subtype == "external"]
    outer = (max(ext, key=lambda e: e.length_m).thickness_mm / 1000) if ext else 0.0  # joints are on centre lines: add one wall thickness for the outer-face overall size
    return {"floor": floor, "ext_girth_m": float(t["external_m"]), "int_girth_m": float(t["internal_m"]), "walls": len(model.walls()),
            "junction_ends": sum(len(e.connected) for e in model.walls()) // 2, "building_length_m": round(float(t["length_m"]) + outer, 2), "building_width_m": round(float(t["width_m"]) + outer, 2),
            "route": model.route, "confidence": model.confidence, "scale": model.calibrations[0].basis, "markup": f"models/{model.markup}",
            "open_checks": [f"{i.code}: {i.message}" for i in open_checks],
            "to_confirm_with_user": [i.check for i in model.issues if i.code == "external_convention"],
            "note": "approximate; the external and internal split depends on what counts as outdoors, so treat it as medium confidence"}


def locate_openings_tool(run: Run, floor: str) -> dict:
    """Find the doors, windows and openings on a floor's plan and tie each to the wall it is in (so external or internal comes from the wall, not
    a guess) and to a schedule type. Needs read_wall_girth for that floor and read_openings (the schedule). Candidates are gaps in the walls and
    printed dimensions equal to a schedule width; the model checks each one by looking at a crop and reads its tag. Counts per schedule type go to
    the BoQ; anything that cannot be matched stays on the schedule and is flagged."""
    from plan2cost.drawing.model import DrawingModel
    from plan2cost.drawing.markup import draw_markup, plan_image
    from plan2cost.drawing.openings import counts_by_mark, locate_openings

    entry = (run.data.get("models") or {}).get(floor)
    if not entry:
        return {"error": f"Read the wall girth for the {floor} floor first (read_wall_girth), so there is a drawing model to put the openings in."}
    if not run.data.get("openings"):
        return {"error": "Read the schedule first (read_openings): the openings are matched to its types."}
    model = DrawingModel.load(run.dir / entry["file"])
    if model.openings():
        return {"error": f"The openings of the {floor} floor are already located."}
    img, scale = plan_image(model, run.pdf, model.page, None, 200)
    schedule = [{"label": o["label"], "width_m": o["width_m"], "height_m": o["height_m"], "count": o["count"], "kind": o["kind"]} for o in run.data["openings"]]
    before = len(model.issues)
    locate_openings(model, img, scale, run.pdf, model.page, schedule)
    model.save(run.dir / entry["file"])
    draw_markup(model, str(run.dir / entry["markup"]), pdf=run.pdf, page=model.page)
    counts = counts_by_mark(model)
    run.data.setdefault("located_openings", {})[floor] = counts
    run.data["models"][floor] = {**entry, **model.summary()}
    new = model.issues[before:]
    for i in new:
        if i.severity != "info":
            run.assumptions.append({"name": "_".join(["drawing_check", floor, i.code, *i.elements[:2]]), "value": "open", "basis": f"{i.message} {i.check}".strip()})
    kinds: dict = {}
    for o in model.openings():
        kinds[o.category] = kinds.get(o.category, 0) + 1
    total: dict = {}
    for fc in run.data["located_openings"].values():
        for mark, c in fc.items():
            total[mark] = total.get(mark, 0) + c["external"] + c["internal"]
    versus = {o["label"]: {"schedule": o["count"], "found_so_far": total.get(o["label"].upper(), 0)} for o in run.data["openings"]}
    return {"floor": floor, "found": kinds, "by_schedule_type": counts, "schedule_vs_found": versus, "unmatched": sum(1 for o in model.openings() if not o.mark),
            "checks": [f"{i.code}: {i.message}" for i in new if i.severity != "info"], "markup": entry["markup"]}


TOOLS = {
    "read_wall_girth": (read_wall_girth, 'page: int (a floor plan page), floor: "ground"|"first"|...: wall girth from the plan; record it as source "computed"'),
    "locate_openings": (locate_openings_tool, "floor: str: find the doors, windows and openings on that floor's plan and tie them to walls and schedule types (after read_wall_girth and read_openings)"),
}
