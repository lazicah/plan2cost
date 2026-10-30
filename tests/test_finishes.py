from plan2cost.facts.rooms import to_rooms
from plan2cost.takeoff.finishes import deductible, external_finish_area, lintel_items, lintel_length_m
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
    assert external_finish_area(100, ops) == 97  # the two 1.8 m2 windows come off, the seven small ones and the internal doors do not


def test_lintels_are_concrete_formwork_and_steel_over_each_opening_plus_its_bearing():
    ops = [Opening("W2", 1.2, 1.5, 2), Opening("D2", 0.9, 2.1, 1, "door", False)]
    length = lintel_length_m(ops, 225)
    assert abs(length - (2 * (1.2 + 0.45) + (0.9 + 0.45))) < 1e-9  # 4.65 m
    items = {i.key: i for i in lintel_items((length,) * 3, length, 0.23, 225, (120, 157, 195), 225)}
    assert items["lintel_concrete_m3"].qty == 1 and items["lintel_concrete_m3"].basis == "measured"  # 4.65 x 0.23 x 0.225 = 0.24 m3, whole units
    assert items["lintel_formwork_m2"].qty == 4 and items["lintel_steel_kg"].basis == "estimated" and items["lintel_steel_kg"].qty_low <= items["lintel_steel_kg"].qty <= items["lintel_steel_kg"].qty_high
    assert lintel_items((0, 0, 0), 0, 0.23, 225, (120, 157, 195), 225) == []
