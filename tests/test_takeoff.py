from plan2cost.tools.takeoff import Plan, Room, takeoff, missing_inputs


def test_takeoff_basic():
    p = Plan(rooms=[Room("a", 4, 3)], wall_height_m=3, openings_area_m2=4)
    assert takeoff(p) == {"floor_area_m2": 12.0, "wall_area_m2": 38.0}


def test_missing_inputs_flags_openings():
    assert "door/window schedule missing" in missing_inputs(Plan(rooms=[Room("a", 4, 3)]))
