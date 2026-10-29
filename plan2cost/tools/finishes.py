"""Tools that measure the finishes: the rooms of each floor as printed. The quantities themselves are made in compute_boq."""
from plan2cost.facts.rooms import read_rooms as read
from plan2cost.kit.pdf import page_text, render_pages
from plan2cost.kit.progress import Run


def read_rooms(run: Run, page: int, floor: str) -> dict:
    """The rooms of one floor with their printed internal dimensions, for floor, ceiling, wall finishes and skirting. Each number is checked to be
    printed on the page. Rooms are taken as rectangles of the two printed dimensions. Porches, terraces and balconies are listed but left out of the
    finishes until the user says they count. Call it for each floor plan page, after read_wall_girth."""
    text = page_text(run.pdf, int(page))
    image = render_pages(run.pdf, [int(page)], str(run.dir / "scratch"), dpi=170)[0]
    rooms = read(image, text, floor)
    if not rooms:
        return {"error": "No rooms could be read from this page."}
    run.data.setdefault("rooms", {})[floor] = [{**r.__dict__, "area_m2": r.area_m2, "perimeter_m": r.perimeter_m} for r in rooms]
    measured = [r for r in rooms if r.area_m2 and not r.open_space]
    open_spaces = [r.name for r in rooms if r.open_space]
    return {"floor": floor, "rooms": [f"{r.name}: {r.a_mm:g} x {r.b_mm:g} = {r.area_m2} m2" if r.area_m2 else f"{r.name}: size not printed" for r in rooms],
            "net_floor_area_m2": round(sum(r.area_m2 for r in measured), 2), "not_measured": [r.name for r in rooms if not r.area_m2],
            "open_spaces_left_out": open_spaces, "dropped_numbers": [i for r in rooms for i in r.issues if "not printed on the page" in i],
            "to_confirm_with_user": ([f"Do the {', '.join(open_spaces)} count for floor finishes, and what is their finish?"] if open_spaces else [])
                                    + ([f"The size of {', '.join(r.name for r in rooms if not r.area_m2 and not r.open_space)} is not printed: can you give it?"]
                                       if any(not r.area_m2 and not r.open_space for r in rooms) else [])}


TOOLS = {
    "read_rooms": (read_rooms, 'page: int (a floor plan page), floor: "ground"|"first"|...: rooms with printed internal sizes, for floor, ceiling and wall finishes and skirting'),
}
