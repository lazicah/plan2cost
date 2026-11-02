import numpy as np

from plan2cost.drawing.model import build_model
from plan2cost.drawing.walls_cv import Wall, outline_polygon_mm
from plan2cost.facts.rooms import to_rooms
from plan2cost.facts.spaces import apply_space_context, place_spaces
from tests.test_drawing_model import box_walls, result_for


def room(name, box=None):
    return to_rooms({"rooms": [{"name": name, "a_mm": None, "b_mm": None, "box": box}]}, "", "ground")[0]


def test_the_name_of_a_space_says_what_it_is():
    kinds = {n: room(n).kind for n in ("Porch", "Terrace", "Balcony", "Lobby", "Void", "Open to below", "Bath/wc", "Master Bedroom", "Garden")}
    assert kinds == {"Porch": "outdoor", "Terrace": "outdoor", "Balcony": "outdoor", "Lobby": "circulation", "Void": "void", "Open to below": "void", "Bath/wc": "wet", "Master Bedroom": "room", "Garden": "outdoor"}


def test_a_box_must_make_sense_to_be_kept():
    assert room("Porch", [0.1, 0.2, 0.4, 0.6]).box == (0.1, 0.2, 0.4, 0.6)
    assert room("Porch", [0.5, 0.2, 0.4, 0.6]).box is None and room("Porch", [0, 0, 1.5, 1]).box is None and room("Porch", "nonsense").box is None


def test_an_external_wall_across_a_porch_is_removed_but_the_walls_that_bound_it_stay():
    walls = box_walls()[:4] + [Wall("v", 1000.0, 1500.0, 4500.0, 230.0)]  # a wall 3 m long inside the building's west end: a porch there is crossed by it
    m = build_model(result_for(walls, [1, 1, 1, 1, 1]), "ground", 1)
    img = np.zeros((600, 800, 3), np.uint8)
    porch = room("Porch", [0.0, 0.2, 0.25, 0.8])  # fractions of an 800 x 600 picture at 0.1 px per mm: x 0 to 2000 mm, y 1200 to 4800 mm
    log = apply_space_context(m, [porch, room("Lobby", [0.4, 0.2, 0.6, 0.8])], img, 0.1)
    ids = {e.id for e in m.walls()}
    assert any(i.code == "wall_removed_open_space" for i in log) and len(ids) == 4  # the crossing wall went; the four outer walls, one of which borders the porch, stayed
    assert [s["kind"] for s in m.spaces] == ["outdoor", "circulation"]


def test_an_internal_wall_inside_an_open_space_is_only_flagged():
    walls = box_walls()[:4] + [Wall("v", 1000.0, 1500.0, 4500.0, 230.0)]
    m = build_model(result_for(walls, [1, 1, 1, 1, 0]), "ground", 1)
    log = apply_space_context(m, [room("Terrace", [0.0, 0.2, 0.25, 0.8])], np.zeros((600, 800, 3), np.uint8), 0.1)
    assert [i.code for i in log] == ["wall_in_open_space"] and len(m.walls()) == 5


def test_voids_become_spaces_with_millimetre_boxes():
    s = place_spaces([room("Void", [0.25, 0.5, 0.5, 1.0])], (600, 800), 0.1)
    assert s == [{"name": "Void", "kind": "void", "box_mm": [2000.0, 3000.0, 4000.0, 6000.0]}]


def test_the_outline_of_a_closed_building_is_a_polygon_and_walls_that_do_not_close_give_none():
    poly = outline_polygon_mm([Wall(w.orient, w.centre_mm, w.start_mm, w.end_mm, w.thickness_mm) for w in box_walls()])
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    assert abs(min(xs) - 0) < 400 and abs(max(xs) - 8000) < 400 and abs(max(ys) - 6000) < 400 and len(poly) <= 8
    assert outline_polygon_mm([Wall("h", 0, 0, 8000, 230.0)]) is None
