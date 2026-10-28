from plan2cost.tools.walls import Opening, blockwork_area_m2, facade_area_m2

HEIGHTS = {"ground": 3.3, "first": 3.3}


def test_plan6_external_blockwork_507():
    ext = {"ground": 98.62, "first": 82.34}
    openings = [Opening("D1", 0.9, 2.1, 4, "door"), Opening("D2", 1.2, 2.1, 4, "door"), Opening("W1", 0.6, 1.8, 22),
                Opening("W2", 0.9, 1.8, 20), Opening("W3", 1.8, 1.2, 2), Opening("W4", 3.6, 1.8, 2)]
    assert round(facade_area_m2(ext, HEIGHTS), 2) == 597.17
    assert blockwork_area_m2(ext, HEIGHTS, openings) == 507


def test_plan6_internal_blockwork_513():
    internal = {"ground": 84.32, "first": 89.05}
    doors = [Opening("D1", 0.95, 2.1, 12, "door", False), Opening("D2", 0.9, 2.1, 10, "door", False),
             Opening("D3", 0.9, 2.1, 2, "door", False), Opening("D4", 3.0, 2.1, 2, "door", False)]
    assert blockwork_area_m2(internal, HEIGHTS, doors) == 513


def test_default_height_when_elevation_missing():
    assert facade_area_m2({"ground": 10}) == 30.0


def test_schedule_to_openings_marks_timber_doors_internal():
    from plan2cost.document import to_openings

    data = {"openings": [
        {"mark": "TD2", "kind": "door", "material": "timber", "width_mm": 900, "height_mm": 2100, "quantity": 10},
        {"mark": "SD1", "kind": "door", "material": "steel", "width_mm": 900, "height_mm": 2100, "quantity": 4},
        {"mark": "AW1", "kind": "window", "material": "aluminium", "width_mm": 600, "height_mm": 1800, "quantity": 22},
        {"mark": "X", "kind": "door", "material": "timber", "width_mm": None, "height_mm": 2100, "quantity": 1}]}
    ops, q = to_openings(data)
    assert [(o.label, o.external) for o in ops] == [("TD2", False), ("SD1", True), ("AW1", True)]
    assert len(q) == 1


def test_plan6_corrected_with_drawing_height_and_schedule_sizes():
    """Author-confirmed corrections: storey height 3.0m (drawing), TD1 0.75m (schedule). ASD1 is treated as internal as in the sheet."""
    ext = {"ground": 98.62, "first": 82.34}
    internal = {"ground": 84.32, "first": 89.05}
    h = {"ground": 3.0, "first": 3.0}
    ext_open = [Opening("SD1", 0.9, 2.15, 4, "door"), Opening("GD1", 1.2, 2.1, 4, "door"), Opening("AW1", 0.6, 1.8, 22),
                Opening("AW2", 0.9, 1.8, 20), Opening("AW3", 1.8, 1.2, 2), Opening("AW4", 3.6, 1.8, 2)]
    int_open = [Opening("TD1", 0.75, 2.1, 12, "door", False), Opening("TD2", 0.9, 2.1, 10, "door", False),
                Opening("TD3", 0.9, 2.1, 2, "door", False), Opening("ASD1", 3.0, 2.1, 2, "door", False)]
    assert blockwork_area_m2(ext, h, ext_open) == 452
    assert blockwork_area_m2(internal, h, int_open) == 466


def test_superstructure_boq_deducts_openings_from_their_own_wall():
    from plan2cost.boq import superstructure_boq

    ops = [Opening("W", 1.0, 1.0, 10), Opening("D", 1.0, 2.0, 5, "door", False)]
    items = {i.key: i for i in superstructure_boq({"g": 100}, {"g": 50}, {"g": 3.0}, ops)}
    assert items["ext_blockwork_230_m2"].qty == 290 and items["int_blockwork_230_m2"].qty == 140
    assert items["opening_w_nr"].qty == 10


def test_storey_heights_from_levels():
    from plan2cost.document import storey_heights_m

    lv = {"storey_heights_mm": [{"from": "NGL", "to": "GROUND FLR. LEVL", "value_mm": 600},
                                {"from": "GROUND FLR. LEVL", "to": "FIRST FLR. LEVEL", "value_mm": 3000},
                                {"from": "FIRST FLR. LEVEL", "to": "ROOF BASE LEVEL", "value_mm": 3000}]}
    assert storey_heights_m(lv) == {"ground": 3.0, "first": 3.0}
