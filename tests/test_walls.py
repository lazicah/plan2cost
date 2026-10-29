from plan2cost.takeoff.walls import Opening, blockwork_area_m2, facade_area_m2

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
    from plan2cost.takeoff.boq import superstructure_boq

    ops = [Opening("W", 1.0, 1.0, 10), Opening("D", 1.0, 2.0, 5, "door", False)]
    items = {i.key: i for i in superstructure_boq({"g": 100}, {"g": 50}, {"g": 3.0}, ops)}
    assert items["ext_blockwork_230_m2"].qty == 290 and items["int_blockwork_230_m2"].qty == 140
    assert items["opening_w_nr"].qty == 10