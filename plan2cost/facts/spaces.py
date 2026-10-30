"""What the names of spaces say about the walls. A space named Porch, Terrace or Balcony is open air, so no external wall crosses it; a wall drawn across one is a drawing edge,
a kerb or a rail and not a wall. A Lobby is a long way through that connects rooms and is enclosed. A Void is open between floors, so it has no slab. The model reads the names and
roughly where each space is; code decides, with margins, so a rough box never removes a wall that bounds the space."""
from plan2cost.drawing.model import DrawingModel, Issue, refresh

EDGE_MARGIN_M = 0.7  # a wall must lie well inside an open space, not on its boundary, to be said to cross it


def place_spaces(rooms: list, shape: tuple, scale: float) -> list[dict]:
    """Rooms with a box as spaces in sheet millimetres. `shape` is (height, width) in pixels of the picture the fractions refer to, `scale` its pixels to a millimetre."""
    h, w = shape
    out = []
    for r in rooms:
        if r.box:
            x0, y0, x1, y1 = r.box
            out.append({"name": r.name, "kind": r.kind, "box_mm": [round(x0 * w / scale, 1), round(y0 * h / scale, 1), round(x1 * w / scale, 1), round(y1 * h / scale, 1)]})
    return out


def _inside(e, box_mm: list, margin_mm: float) -> float:
    """Length (mm) of a wall inside a box shrunk by a margin."""
    x0, y0, x1, y1 = box_mm[0] + margin_mm, box_mm[1] + margin_mm, box_mm[2] - margin_mm, box_mm[3] - margin_mm
    if x1 <= x0 or y1 <= y0:
        return 0.0
    if e.orient == "h":
        return max(min(max(e.x0_mm, e.x1_mm), x1) - max(min(e.x0_mm, e.x1_mm), x0), 0.0) if y0 <= e.y0_mm <= y1 else 0.0
    return max(min(max(e.y0_mm, e.y1_mm), y1) - max(min(e.y0_mm, e.y1_mm), y0), 0.0) if x0 <= e.x0_mm <= x1 else 0.0


def walls_in_open_air(model: DrawingModel) -> list[tuple]:
    """(wall, space) for each wall that mostly lies inside an open-air space (60% of its length, at least a metre, inside the space shrunk by a margin)."""
    out = []
    for s in model.spaces:
        if s["kind"] != "outdoor":
            continue
        for e in model.walls():
            inside = _inside(e, s["box_mm"], EDGE_MARGIN_M * 1000)
            if inside >= 1000 and inside >= 0.6 * e.length_m * 1000:
                out.append((e, s))
    return out


def apply_space_context(model: DrawingModel, rooms: list, img, scale: float) -> list[Issue]:
    """Record the spaces on the model and remove the external walls that cross open-air spaces (an internal one is only flagged). When a wall is removed, which walls have the
    outdoors on one side is worked out again, since a wall across a porch had closed it off."""
    model.spaces = place_spaces(rooms, img.shape[:2], scale)
    log: list[Issue] = []
    crossing = walls_in_open_air(model)
    drop = {e.id: s for e, s in crossing if e.subtype == "external" or e.external_share >= 0.5}
    for e, s in crossing:
        if e.id not in drop:
            log.append(Issue("wall_in_open_space", "warn", f"{e.id} lies inside the {s['name']}, which is open air; it may be a rail, a kerb or a drawing edge.", [e.id], "Check this wall on the plan.", "space names"))
    if drop:
        model.elements = [e for e in model.elements if e.id not in drop]
        for i, s in drop.items():
            log.append(Issue("wall_removed_open_space", "info", f"{i} removed: an external wall cannot cross the {s['name']}, which is open air.", [i], "", "space names"))
        refresh(model)
        recompute_external(model, img.shape[:2], scale)
    return log


def recompute_external(model: DrawingModel, shape: tuple, scale: float) -> None:
    """Work out again which walls have the outdoors on one side (after a wall was removed or added) and refresh the totals."""
    from plan2cost.drawing.model import compute_totals, wall_of
    from plan2cost.drawing.walls_cv import building_size_m, external_fractions

    els = model.walls()
    walls = [wall_of(e) for e in els]
    for e, f in zip(els, external_fractions(walls, shape, 1 / scale)):
        e.external_share, e.subtype = round(float(f), 2), "external" if f >= 0.5 else "internal"
    model.totals = compute_totals(els, building_size_m(walls))
