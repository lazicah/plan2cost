from plan2cost.agent.massing import massing_from
from plan2cost.drawing.model import Element, build_model
from tests.test_drawing_model import box_walls, result_for


def model(floor, shift=0.0):
    m = build_model(result_for(box_walls()), floor, 1)
    for e in m.elements:
        e.x0_mm, e.x1_mm = e.x0_mm + shift, e.x1_mm + shift
    return m


def test_floors_are_lined_up_by_their_top_left_corner_and_openings_stay_with_their_wall():
    ground, first = model("ground"), model("first", shift=50000.0)  # another sheet, another origin
    top = next(e for e in ground.walls() if e.orient == "h" and e.y0_mm == 0)
    ground.elements.append(Element("WN-001", "window", "external", 1, "ground", "h", 2000, 0, 3200, 0, 1.2, 230, parent=top.id, width_mm=1200))
    d = massing_from([ground, first], {"storey_height_m": 3.0, "roof_type": "hip"})
    assert [f["name"] for f in d["floors"]] == ["ground", "first"]
    g, f = d["floors"]
    assert min(w["x0"] for w in g["walls"]) == min(w["x0"] for w in f["walls"]) == 0.0  # the first floor sheet was 50 m to the right
    assert g["openings"] == [{"kind": "window", "parent": top.id, "x0": 2.0, "y0": 0.0, "x1": 3.2, "y1": 0.0}] and f["openings"] == []
    assert d["roof"]["type"] == "hip" and d["roof"]["pitch_deg"] == 32 and d["roof"]["overhang_m"] == 0.45 and any("never a source of quantities" in n for n in d["notes"])


def test_a_pitch_and_overhang_the_user_gave_are_used_and_nothing_measured_gives_nothing():
    d = massing_from([model("ground")], {"storey_height_m": 2.8, "roof_type": "gable", "pitch_deg": 20, "overhang_m": 0.6})
    assert d["roof"]["pitch_deg"] == 20 and d["roof"]["overhang_m"] == 0.6 and d["storey_height_m"] == 2.8
    assert massing_from([], {"storey_height_m": 3, "roof_type": "flat"}) == {}


def test_a_window_on_the_wall_of_a_void_is_glazing_from_the_floor_below():
    ground, first = model("ground"), model("first")
    top = lambda m: next(e for e in m.walls() if e.orient == "h" and e.y0_mm == 0)
    first.elements.append(Element("WN-001", "window", "external", 1, "first", "h", 2000, 0, 3200, 0, 1.2, 230, parent=top(first).id, width_mm=1200))
    first.spaces = [{"name": "Void Over Lounge", "kind": "void", "box_mm": [1000.0, 0.0, 5000.0, 4000.0]}]
    far = Element("WN-002", "window", "external", 1, "first", "h", 6500, 0, 7500, 0, 1.0, 230, parent=top(first).id, width_mm=1000)  # beyond reach of the void
    first.elements.append(far)
    d = massing_from([ground, first], {"storey_height_m": 3.0, "roof_type": "gable"})
    g, f = d["floors"]
    wins = {o["x0"]: o for o in f["openings"]}
    assert wins[2.0].get("tall") is True and not wins[6.5].get("tall")
    assert any(o.get("tall_from_above") and o["x0"] == 2.0 for o in g["openings"])  # the wall below is opened to match
    assert f["voids"] == [[1.0, 0.0, 5.0, 4.0]] and any("void" in n and "assumed" in n for n in d["notes"])
