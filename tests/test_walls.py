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
