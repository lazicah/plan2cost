from plan2cost.facts.rooms import Room, to_rooms
from plan2cost.takeoff.finishes import deductible, external_finish_area, finishes_boq, floor_finishes, lintel_items
from plan2cost.takeoff.walls import Opening

TEXT = "KITCHEN 4500 4038 BEDROOM 3850 3600 PORCH 900 2750 STORE 1275"


def rooms():
    data = {"rooms": [{"name": "Kitchen", "a_mm": 4500, "b_mm": 4038}, {"name": "Bedroom 1", "a_mm": 3850, "b_mm": 3600}, {"name": "Porch", "a_mm": 900, "b_mm": 2750},
                      {"name": "Store", "a_mm": 1275, "b_mm": 3000}, {"name": "Bath/wc", "a_mm": 9999, "b_mm": 2425}]}
    return to_rooms(data, TEXT, "ground")


def test_a_dimension_not_printed_on_the_page_is_dropped_not_used():
    r = {x.name: x for x in rooms()}
    assert r["Kitchen"].area_m2 == 18.17 and r["Kitchen"].verified
    assert r["Store"].area_m2 is None and "3000" in " ".join(r["Store"].issues)  # 3000 is not on this page's text
    assert r["Bath/wc"].a_mm is None and r["Bath/wc"].wet and r["Porch"].open_space


def test_only_a_void_over_one_square_metre_comes_off_a_finish():
    ops = [Opening("W1", 0.6, 0.6, 7), Opening("W2", 1.2, 1.5, 2), Opening("D2", 0.9, 2.1, 3, "door", False)]
    assert {o.label for o in deductible(ops)} == {"W2", "D2"}
    # facade 100 m2, W2 two windows of 1.8 m2 come off, the seven small windows and the internal doors do not
    assert external_finish_area(100, ops) == 97


def test_wall_area_is_perimeter_times_height_less_deductible_voids_internal_doors_twice():
    rs = [r for r in rooms() if r.area_m2]
    ops = [Opening("D2", 0.9, 2.1, 1, "door", False), Opening("W2", 1.2, 1.5, 1)]
    f = floor_finishes("ground", rs, 3.0, ops)
    assert f.rooms == 2 and f.floor_area_m2 == 32.03 and f.open_spaces == ["Porch"]
    per = 2 * (4.5 + 4.038) + 2 * (3.85 + 3.6)
    assert abs(f.wall_area_m2 - (per * 3.0 - 1.8 - 2 * 0.9 * 2.1)) < 0.05


def test_finishes_lines_ask_for_what_the_drawings_do_not_say():
    f = floor_finishes("ground", [r for r in rooms() if r.area_m2], 3.0, [])
    items, ask = finishes_boq({"ground": f}, {})
    assert {i.key for i in items} == {"floor_finish_m2", "internal_wall_finish_m2", "internal_wall_paint_m2", "ceiling_finish_m2", "skirting_m"} and len(ask) == 3
    items, ask = finishes_boq({"ground": f}, {"floor_finish_spec": "ceramic tiles 400x400", "wall_finish_spec": "cement-sand plaster 15mm", "skirting_height_mm": 100})
    assert not ask and "ceramic tiles" in items[0].description


def test_lintels_wait_for_the_bearing_and_never_assume_it():
    ops = [Opening("W2", 1.2, 1.5, 2), Opening("W2", 1.2, 1.5, 1, "window", False)]
    assert lintel_items(ops, None)[1]
    items, ask = lintel_items(ops, 225)
    assert not ask and items[0].qty == 3 and "1650mm long" in items[0].description
