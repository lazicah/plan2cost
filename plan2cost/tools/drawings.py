"""The tool that reads a floor plan: walls, rooms and openings in one call. Walls and openings are measured by code from the lines; the model reads only what is
printed (scale, overall dimensions, room names) and looks at crops to say what a gap in a wall is."""
import tempfile

from plan2cost.drawing.markup import draw_markup, model_for_floor, plan_image
from plan2cost.drawing.openings import locate_openings
from plan2cost.facts.rooms import read_rooms
from plan2cost.kit.pdf import page_text, render_pages
from plan2cost.kit.progress import Run
from plan2cost.takeoff import coefficients as C
from plan2cost.tools.records import add_fact, settle


def _openings(model) -> list[dict]:
    """Doors and windows grouped by kind, width (to 50mm) and the side of the wall they are in, with the standard height where the plan gives none."""
    walls = {w.id: w for w in model.walls()}
    groups: dict = {}
    for o in model.openings():
        if o.category not in ("door", "window") or not o.width_mm:
            continue
        external = bool(o.parent in walls and walls[o.parent].subtype == "external")
        w = int(round(o.width_mm / 50.0) * 50)
        groups[(o.category, w, external)] = groups.get((o.category, w, external), 0) + 1
    h = {"door": C.value("door_height_m"), "window": C.value("window_height_m")}
    return [{"label": f"{'D' if k == 'door' else 'W'}{w}", "width_m": w / 1000, "height_m": h[k], "count": n, "kind": k, "external": ext, "assumed_height": True}
            for (k, w, ext), n in sorted(groups.items())]


def read_floor(run: Run, floor: str) -> dict:
    """Read one floor plan: wall girth (external and internal), the building's size, the doors and windows tied to their walls, and the room names (for wet rooms).
    Returns what was measured, how far to trust it and which checks are open; the open checks are saved with the estimate. Call it once for each floor."""
    spec = next((f for f in run.floors if f["name"] == floor), None)
    if not spec:
        return {"error": f"No floor named {floor}. Floors: {[f['name'] for f in run.floors]}"}
    file, page = spec["file"], int(spec.get("page") or 1)
    is_pdf = file.lower().endswith(".pdf")
    models_dir = run.dir / "models"

    def show(m):  # the measured walls, for the console, while the model review runs
        run.data["preview"] = {"floor": floor, "markup": f"models/{m.markup}", "walls": len(m.walls()), "total_m": m.totals["total_m"], "external_m": m.totals["external_m"],
                               "internal_m": m.totals["internal_m"], "route": m.route}
        run.save()

    try:
        model = model_for_floor(file, page, floor, str(models_dir), review=True, on_measured=show)
    except ValueError as e:
        run.data.pop("preview", None)
        return {"error": f"No walls could be measured on the {floor} floor plan ({e}). Ask the user for a clearer plan, or use assume_floor_like_ground."}
    run.data.pop("preview", None)
    t = model.totals
    ext_walls = [e for e in model.walls() if e.subtype == "external"]
    outer = (max(ext_walls, key=lambda e: e.length_m).thickness_mm / 1000) if ext_walls else 0.23  # joints are on centre lines: add one wall thickness for the outer face
    issues = [i for i in model.issues if i.severity != "info"]
    rooms, room_note = [], ""
    try:
        image = render_pages(file, [page], tempfile.mkdtemp(), dpi=170)[0] if is_pdf else file
        rooms = read_rooms(image, page_text(file, page) if is_pdf else "", floor)
    except Exception as e:  # the room names are a refinement; a failed read never stops the floor
        room_note = f"room names could not be read ({type(e).__name__})"
    ops: list[dict] = []
    try:
        img, scale = plan_image(model, file if is_pdf else None, page if is_pdf else None, None if is_pdf else file, 200)
        before = len(model.issues)
        locate_openings(model, img, scale, file if is_pdf else None, page if is_pdf else None, None)
        draw_markup(model, str(models_dir / model.markup), pdf=file if is_pdf else None, page=page if is_pdf else None, image=None if is_pdf else file)
        issues += [i for i in model.issues[before:] if i.severity != "info"]
        ops = _openings(model)
    except Exception as e:
        room_note += f" openings could not be located ({type(e).__name__})"
    model.save(models_dir / f"drawing_model_{floor}_p{page}.json")
    for i in issues:  # open checks travel with the estimate so they cannot be lost at submit
        run.assumptions.append({"name": "_".join(["drawing_check", floor, i.code, *i.elements[:2]]), "value": "open", "basis": f"{i.message} {i.check}".strip()})
    data = {"name": floor, "ext_m": float(t["external_m"]), "int_m": float(t["internal_m"]), "junctions": sum(len(e.connected) for e in model.walls()) // 2,
            "length_m": round(float(t["length_m"]) + outer, 2), "width_m": round(float(t["width_m"]) + outer, 2),
            "wall_plan_area_m2": round(sum(e.length_m * e.thickness_mm / 1000 for e in model.walls()), 2), "openings": ops, "rooms": [r.name for r in rooms],
            "route": model.route, "confidence": model.confidence, "markup": f"models/{model.markup}", "page": page}
    run.data.setdefault("floors", {})[floor] = data
    run.data.setdefault("models", {})[floor] = {"file": f"models/drawing_model_{floor}_p{page}.json", "markup": f"models/{model.markup}", **model.summary()}
    item = next((c["id"] for c in run.checklist if f"the {floor} floor" in c["question"]), "")
    for name, v, u in (("ext_girth", data["ext_m"], "m"), ("int_girth", data["int_m"], "m"), ("building_length", data["length_m"], "m"), ("building_width", data["width_m"], "m")):
        add_fact(run, f"{name}_{floor}", v, u, "computed", f"measured from the {floor} floor plan ({model.route} route, {model.confidence} confidence)", item)
    settle(run, item)
    n_doors, n_windows = sum(o["count"] for o in ops if o["kind"] == "door"), sum(o["count"] for o in ops if o["kind"] == "window")
    return {"floor": floor, "ext_girth_m": data["ext_m"], "int_girth_m": data["int_m"], "building_m": [data["length_m"], data["width_m"]], "walls": len(model.walls()),
            "doors": n_doors, "windows": n_windows, "rooms": [r.name for r in rooms], "route": model.route, "confidence": model.confidence, "scale": model.calibrations[0].basis,
            "open_checks": [f"{i.code}: {i.message}" for i in issues][:8], "note": ("; ".join(x for x in (room_note.strip(),) if x) or "approximate: the external and internal split depends on what counts as outdoors")}


TOOLS = {
    "read_floor": (read_floor, 'floor: str ("ground", "first", ...): read that floor plan: wall girth, building size, doors and windows, room names. One call per floor.'),
}
