"""Data for the 3D massing view: the walls and openings of the drawing models, lined up floor on floor, with the storey height, roof type, pitch and overhang. The view is
illustrative, built from the same models the bill is measured from so the two cannot disagree. It is never a source of quantities: door and window heights are standard
sizes, the sill height is assumed, and the roof is a plain shape of the chosen type over the walls' outline."""
from plan2cost.drawing.model import DrawingModel
from plan2cost.kit.progress import Run
from plan2cost.takeoff import coefficients as C
from plan2cost.drawing.qc import _wall
from plan2cost.drawing.walls_cv import outline_polygon_mm
from plan2cost.takeoff.rough import pitch_range

SILL_M = 0.9  # not on a floor plan: assumed, for the picture only


def _bounds(model: DrawingModel) -> tuple[float, float, float, float]:
    xs = [v for e in model.walls() for v in (e.x0_mm, e.x1_mm)]
    ys = [v for e in model.walls() for v in (e.y0_mm, e.y1_mm)]
    return min(xs), min(ys), max(xs), max(ys)


def massing_from(models: list[DrawingModel], inputs: dict) -> dict:
    """Floors lowest first. Every floor is shifted so its walls' top-left corner sits on the ground floor's: the plans are separate sheets with their own origins."""
    if not models or not any(m.walls() for m in models):
        return {}
    gx, gy, gx1, gy1 = _bounds(models[0])
    floors = []
    for i, m in enumerate(models):
        if not m.walls():
            continue
        x0, y0, _, _ = _bounds(m)
        dx, dy = (gx - x0) / 1000, (gy - y0) / 1000
        f = lambda e: {"x0": e.x0_mm / 1000 + dx, "y0": e.y0_mm / 1000 + dy, "x1": e.x1_mm / 1000 + dx, "y1": e.y1_mm / 1000 + dy}
        poly = outline_polygon_mm([_wall(e) for e in m.walls()])
        if not poly:  # the walls do not close a building: a slab over the rectangle that holds them
            x0_, y0_, x1_, y1_ = _bounds(m)
            poly = [(x0_, y0_), (x1_, y0_), (x1_, y1_), (x0_, y1_)]
        voids = [[b[0] / 1000 + dx, b[1] / 1000 + dy, b[2] / 1000 + dx, b[3] / 1000 + dy] for b in (sp["box_mm"] for sp in m.spaces if sp["kind"] == "void")]
        floors.append({"name": m.floor, "index": len(floors), "outline": [[x / 1000 + dx, y / 1000 + dy] for x, y in poly], "voids": voids,
                       "walls": [{"id": e.id, **f(e), "t": e.thickness_mm / 1000, "external": e.subtype == "external"} for e in m.walls()],
                       "openings": [{"kind": o.category, "parent": o.parent, **f(o)} for o in m.openings()]})
    t = max(e.thickness_mm for e in models[0].walls()) / 1000
    pitch = pitch_range(inputs, len(floors))[1]
    overhang = float(inputs["overhang_m"]) if inputs.get("overhang_m") else C.value("roof_eaves_overhang_m")
    return {"storey_height_m": float(inputs["storey_height_m"]), "door_height_m": C.value("door_height_m"), "window_height_m": C.value("window_height_m"), "sill_m": SILL_M,
            "floors": floors, "roof": {"type": inputs["roof_type"], "pitch_deg": round(pitch, 1), "overhang_m": round(overhang, 2),
                                       "bounds": [gx / 1000 - t / 2, gy / 1000 - t / 2, gx1 / 1000 + t / 2, gy1 / 1000 + t / 2]},
            "notes": ["Illustrative: built from the same walls and openings as the bill, never a source of quantities.",
                      f"Door and window heights are standard sizes ({C.value('door_height_m')} m and {C.value('window_height_m')} m); the sill height is assumed ({SILL_M} m).",
                      "Floor slabs follow the outline the walls enclose, with a hole for each space named Void. The roof is a plain shape of the chosen type over the rectangle that holds the walls, so an L-shaped plan gets a roof over its missing corner.", "Floors are lined up by the top-left corner of their walls."]}


def massing(run: Run) -> dict:
    models = []
    for f in run.floors:
        info = (run.data.get("models") or {}).get(f["name"])
        if info and (run.dir / info["file"]).exists():
            models.append(DrawingModel.load(run.dir / info["file"]))
    return massing_from(models, run.inputs)
