"""Data for the 3D massing view: the walls and openings of the drawing models, lined up floor on floor, with the storey height, roof type, pitch and overhang. The view is
illustrative, built from the same models the bill is measured from so the two cannot disagree. It is never a source of quantities: door and window heights are standard
sizes, the sill height is assumed, and the roof is a plain shape of the chosen type over the walls' outline."""
from plan2cost.drawing.model import DrawingModel, wall_of
from plan2cost.drawing.walls_cv import outline_polygon_mm
from plan2cost.kit.progress import Run
from plan2cost.takeoff import coefficients as C
from plan2cost.takeoff.rough import pitch_range

SILL_M = 0.9  # not on a floor plan: assumed, for the picture only
VOID_REACH_M = 1.5  # a window within this distance of a void is taken to be glazing to it


def _bounds(model: DrawingModel) -> tuple[float, float, float, float]:
    """The box that holds a floor's walls, in sheet millimetres: x0, y0, x1, y1."""
    xs = [v for e in model.walls() for v in (e.x0_mm, e.x1_mm)]
    ys = [v for e in model.walls() for v in (e.y0_mm, e.y1_mm)]
    return min(xs), min(ys), max(xs), max(ys)


def _is_horizontal(w: dict) -> bool:
    return abs(w["x1"] - w["x0"]) >= abs(w["y1"] - w["y0"])


def _floor_entry(m: DrawingModel, index: int, gx: float, gy: float) -> dict:
    """One floor as the view needs it, in metres, shifted so its walls' top-left corner sits on the ground floor's (gx, gy): the plans are separate sheets with their own origins.
    It holds the walls, the openings, the outline the walls enclose (a rectangle when they do not close a building) and the voids."""
    x0, y0, x1, y1 = _bounds(m)
    dx, dy = (gx - x0) / 1000, (gy - y0) / 1000
    at = lambda e: {"x0": e.x0_mm / 1000 + dx, "y0": e.y0_mm / 1000 + dy, "x1": e.x1_mm / 1000 + dx, "y1": e.y1_mm / 1000 + dy}
    poly = outline_polygon_mm([wall_of(e) for e in m.walls()]) or [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    voids = [[b[0] / 1000 + dx, b[1] / 1000 + dy, b[2] / 1000 + dx, b[3] / 1000 + dy] for b in (sp["box_mm"] for sp in m.spaces if sp["kind"] == "void")]
    return {"name": m.floor, "index": index, "outline": [[x / 1000 + dx, y / 1000 + dy] for x, y in poly], "voids": voids,
            "walls": [{"id": e.id, **at(e), "t": e.thickness_mm / 1000, "external": e.subtype == "external"} for e in m.walls()],
            "openings": [{"kind": o.category, "parent": o.parent, **at(o)} for o in m.openings()]}


def _wall_below(below: dict, wall: dict, mx: float, my: float) -> dict | None:
    """The wall on the floor below that lies along `wall` and under the point (mx, my), within 0.4 m across and 0.3 m along."""
    horiz = _is_horizontal(wall)
    across = lambda w: w["y0"] if horiz else w["x0"]
    for w in below["walls"]:
        if _is_horizontal(w) != horiz or abs(across(w) - across(wall)) >= 0.4:
            continue
        lo, hi = (min(w["x0"], w["x1"]), max(w["x0"], w["x1"])) if horiz else (min(w["y0"], w["y1"]), max(w["y0"], w["y1"]))
        if lo - 0.3 <= (mx if horiz else my) <= hi + 0.3:
            return w
    return None


def _link_void_glazing(floors: list[dict]) -> None:
    """Glazing to a void: a window on an external wall of a void runs from the floor below to this floor (no elevation says so, so it is assumed and flagged in the notes). The
    window is marked `tall`, and the wall below gets a matching opening marked `tall_from_above` (an existing window at that place is marked instead of doubled)."""
    for up, below in zip(floors[1:], floors):
        for o in up["openings"]:
            if o["kind"] != "window":
                continue
            mx, my = (o["x0"] + o["x1"]) / 2, (o["y0"] + o["y1"]) / 2
            wall = next((w for w in up["walls"] if w["id"] == o["parent"]), None)
            near_void = any(v[0] - VOID_REACH_M <= mx <= v[2] + VOID_REACH_M and v[1] - VOID_REACH_M <= my <= v[3] + VOID_REACH_M for v in up["voids"])
            if not wall or not wall["external"] or not near_void:
                continue
            o["tall"] = True
            low = _wall_below(below, wall, mx, my)
            if not low:
                continue
            twin = next((b for b in below["openings"] if b["kind"] == "window" and b["parent"] == low["id"] and abs((b["x0"] + b["x1"]) / 2 - mx) < 0.6 and abs((b["y0"] + b["y1"]) / 2 - my) < 0.6), None)
            if twin is None:
                twin = {"kind": "window", "parent": low["id"], "x0": o["x0"], "y0": o["y0"], "x1": o["x1"], "y1": o["y1"]}
                below["openings"].append(twin)
            twin["tall_from_above"] = True


def massing_from(models: list[DrawingModel], inputs: dict) -> dict:
    """The data for the view from the floors' drawing models, lowest first (empty when no walls were measured): the floors, the roof and the notes the view shows."""
    if not models or not any(m.walls() for m in models):
        return {}
    gx, gy, gx1, gy1 = _bounds(models[0])
    floors = []
    for m in models:
        if m.walls():
            floors.append(_floor_entry(m, len(floors), gx, gy))
    _link_void_glazing(floors)
    t = max(e.thickness_mm for e in models[0].walls()) / 1000
    pitch = pitch_range(inputs, len(floors))[1]
    overhang = float(inputs["overhang_m"]) if inputs.get("overhang_m") else C.value("roof_eaves_overhang_m")
    return {"storey_height_m": float(inputs["storey_height_m"]), "door_height_m": C.value("door_height_m"), "window_height_m": C.value("window_height_m"), "sill_m": SILL_M,
            "floors": floors, "roof": {"type": inputs["roof_type"], "pitch_deg": round(pitch, 1), "overhang_m": round(overhang, 2),
                                       "bounds": [gx / 1000 - t / 2, gy / 1000 - t / 2, gx1 / 1000 + t / 2, gy1 / 1000 + t / 2]},
            "notes": ["Illustrative: built from the same walls and openings as the bill, never a source of quantities.",
                      f"Door and window heights are standard sizes ({C.value('door_height_m')} m and {C.value('window_height_m')} m); the sill height is assumed ({SILL_M} m).",
                      "A window on a wall of a void is drawn as glazing from the floor below to this floor (no elevation says so: assumed). Floor slabs follow the outline the walls enclose, with a hole for each space named Void. The roof is a plain shape of the chosen type over the rectangle that holds the walls, so an L-shaped plan gets a roof over its missing corner.", "Floors are lined up by the top-left corner of their walls."]}


def massing(run: Run) -> dict:
    """The 3D view's data for a run: the saved drawing model of each floor, lowest first, with the run's inputs."""
    models = []
    for f in run.floors:
        info = (run.data.get("models") or {}).get(f["name"])
        if info and (run.dir / info["file"]).exists():
            models.append(DrawingModel.load(run.dir / info["file"]))
    return massing_from(models, run.inputs)
