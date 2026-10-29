"""Quality checks on a drawing model. Each check looks for one way the interpretation can be wrong and says what a person should look at; none of
them changes a measurement. A result with open warnings is reported as such, never tidied into a clean total."""
from plan2cost.drawing_model import DrawingModel, Element, Issue
from plan2cost.walls_cv import Wall

STANDARD_MM = (100, 150, 200, 225, 230, 300)


def _wall(e: Element) -> Wall:
    return Wall(e.orient, e.y0_mm if e.orient == "h" else e.x0_mm, e.x0_mm if e.orient == "h" else e.y0_mm, e.x1_mm if e.orient == "h" else e.y1_mm, e.thickness_mm)


def _joints(walls: list[Wall], tol_mm: float = 150) -> list[tuple[float, float]]:
    from plan2cost.drawing_model import touching

    pts = []
    for h in (w for w in walls if w.orient == "h"):
        for v in (w for w in walls if w.orient == "v"):
            if touching(h, v, tol_mm):
                pts.append((v.centre_mm, h.centre_mm))
    return pts


def check_double_counting(model: DrawingModel) -> list[Issue]:
    """Two runs on the same line that overlap are counted twice. Parallel runs closer than a wall thickness are the same wall found twice."""
    out = []
    els = model.walls()
    for i, a in enumerate(els):
        for b in els[i + 1:]:
            if a.orient != b.orient:
                continue
            wa, wb = _wall(a), _wall(b)
            if abs(wa.centre_mm - wb.centre_mm) > 0.8 * max(a.thickness_mm, b.thickness_mm):
                continue
            over = min(wa.end_mm, wb.end_mm) - max(wa.start_mm, wb.start_mm)
            short = min(wa.length_mm, wb.length_mm)
            if over > 150 and over >= 0.1 * short:
                out.append(Issue("overlap", "warn", f"{a.id} and {b.id} run along the same line and overlap for {over / 1000:.2f} m, which may be counted twice.", [a.id, b.id],
                                 "Look at where the two runs overlap and delete the duplicate."))
    return out


def check_dangling(model: DrawingModel) -> list[Issue]:
    """A run that extends well beyond the last joint of the building is usually a grid, extension or dimension line merged into a wall."""
    els = model.walls()
    walls = [_wall(e) for e in els]
    pts = _joints(walls)
    if len(pts) < 4:
        return []
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    out = []
    for e, w in zip(els, walls):
        lo, hi = (x0, x1) if w.orient == "h" else (y0, y1)
        beyond = max(lo - w.start_mm, w.end_mm - hi, 0)
        if beyond > 600:
            out.append(Issue("dangling", "warn", f"{e.id} runs {beyond / 1000:.1f} m past the last joint of the building; it may include a grid or dimension line.", [e.id],
                             "Check the end of this run on the plan."))
    return out


def _end_meets_wall(w: Wall, end: float, walls: list[Wall], tol_mm: float = 150) -> bool:
    """Does the end of run `w` (at position `end` along it) land on a perpendicular run?"""
    return any(v.orient != w.orient and abs(v.centre_mm - end) <= v.thickness_mm / 2 + tol_mm and v.start_mm - tol_mm <= w.centre_mm <= v.end_mm + tol_mm for v in walls)


def check_free_ends(model: DrawingModel) -> list[Issue]:
    """In a building most wall ends meet another wall. Many ends meeting nothing means walls were missed or split."""
    walls = [_wall(e) for e in model.walls()]
    free = total = 0
    for w in walls:
        for end in (w.start_mm, w.end_mm):
            total += 1
            free += not _end_meets_wall(w, end, walls)
    if total >= 8 and free / total > 0.45:
        return [Issue("free_ends", "warn", f"{free} of {total} wall ends meet no other wall; walls may have been missed or split by openings.", [],
                      "Compare the plan against the markup for missing walls, especially short partitions.")]
    return []


def check_extents(model: DrawingModel, printed_mm: list) -> list[Issue]:
    """The building the walls make should be as large as the overall dimensions printed on the sheet, on both axes."""
    walls = [_wall(e) for e in model.walls()]
    pts = _joints(walls)
    if len(pts) < 4:
        return [Issue("extents", "warn", "Too few joints to measure the building's size, so it could not be checked against the printed overall dimensions.", [], "Confirm the building size.")]
    vals = [v / 1000 for v in printed_mm if v >= 3000]
    if not vals:
        return [Issue("extents", "info", "No printed overall dimension was available to check the building size against.", [], "")]
    lx, ly = (max(p[0] for p in pts) - min(p[0] for p in pts)) / 1000, (max(p[1] for p in pts) - min(p[1] for p in pts)) / 1000  # metres, like the printed values
    t = (sum(e.thickness_mm for e in model.walls()) / max(len(model.walls()), 1)) / 1000
    for ex, ey in ((lx, ly), (lx + t, ly + t), (lx + 2 * t, ly + 2 * t)):
        for a, b in ((ex, ey), (ey, ex)):
            if any(abs(va - a) <= 0.07 * a for va in vals) and any(abs(vb - b) <= 0.07 * b for vb in vals):
                return []
    return [Issue("extents", "warn", f"The walls make a building of about {lx:.1f} x {ly:.1f} m, which matches no pair of the printed overall dimensions ({', '.join(f'{v:.2f}' for v in sorted(set(vals)))} m).", [],
                  "Part of the building may be missing or something outside it was counted as wall.")]


def check_thickness(model: DrawingModel) -> list[Issue]:
    total = sum(e.length_m for e in model.walls()) or 1
    thin = sum(e.length_m for e in model.walls() if e.thickness_mm <= 100)
    if thin / total > 0.3:
        return [Issue("thin_walls", "info", f"{thin:.0f} m of the walls ({thin / total * 100:.0f}%) are 100 mm thick, which is unusual; some may be fixtures or window frames.", [],
                      "Check the thinnest runs against the plan.")]
    return []


def check_scale(model: DrawingModel) -> list[Issue]:
    out = []
    for c in model.calibrations:
        if c.confidence == "low":
            out.append(Issue("scale", "warn", f"The scale is a weak estimate ({c.method}); every length depends on it.", [c.id], "Confirm one printed dimension against the plan."))
        elif "grid" in c.method:
            out.append(Issue("scale", "info", "The scale came from the grid bubbles, which is accurate to about 2 percent.", [c.id], ""))
    return out


def check_convention(model: DrawingModel) -> list[Issue]:
    """External girth here is the walls with the outdoors on one side. Many surveyors take the building outline instead, which leaves out recesses,
    porches and terraces; when the two differ a person has to say which parts count."""
    walls = [_wall(e) for e in model.walls()]
    pts = _joints(walls)
    if len(pts) < 4:
        return []
    lx, ly = (max(p[0] for p in pts) - min(p[0] for p in pts)) / 1000, (max(p[1] for p in pts) - min(p[1] for p in pts)) / 1000
    outline = 2 * (lx + ly)
    ext = model.totals.get("external_m", 0)
    if outline and ext > 1.15 * outline:
        return [Issue("external_convention", "info", f"External walls total {ext:.0f} m but the building outline is about {outline:.0f} m; recesses, porches or terraces add the difference.", [],
                      "Ask which porches, terraces and recesses count as external wall.")]
    return []


def check_plausibility(model: DrawingModel) -> list[Issue]:
    total = model.totals.get("total_m", 0)
    if total and model.totals.get("internal_m", 0) < 0.1 * total:
        return [Issue("no_internal", "warn", "Almost no internal wall was found; a building with rooms has partitions.", [], "Check that internal walls were not missed.")]
    return []


def run_checks(model: DrawingModel, printed_mm: list) -> list[Issue]:
    issues: list[Issue] = []
    for check in (check_double_counting, check_dangling, check_free_ends, check_thickness, check_scale, check_convention, check_plausibility):
        issues += check(model)
    issues += check_extents(model, printed_mm)
    order = {"error": 0, "warn": 1, "info": 2}
    return sorted(issues, key=lambda i: order[i.severity])
