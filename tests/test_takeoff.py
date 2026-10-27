from plan2cost.tools.takeoff import DimKind, Plan, Room, WallRun, centre_line_m, girth, missing_inputs, takeoff


def test_takeoff_basic():
    p = Plan(rooms=[Room("a", 4, 3)], wall_height_m=3, openings_area_m2=4)
    assert takeoff(p) == {"floor_area_m2": 12.0, "wall_area_m2": 38.0}


def test_missing_inputs_flags_openings():
    assert "door/window schedule missing" in missing_inputs(Plan(rooms=[Room("a", 4, 3)]))


def test_centre_line_from_each_dimension_kind():
    cl = WallRun("a", 9.6, DimKind.CENTRE_LINE, 230)
    ee = WallRun("b", 9.83, DimKind.END_TO_END, 230)  # 9.6 + 0.23 overall
    ii = WallRun("c", 9.37, DimKind.IN_TO_IN, 230)  # 9.6 - 0.23 clear
    assert centre_line_m(cl) == centre_line_m(ee) == centre_line_m(ii) == 9.6


def test_girth_groups_by_drawn_thickness():
    runs = [
        WallRun("x", 5.0, DimKind.CENTRE_LINE, 230, count=2, external=True),
        WallRun("y", 3.0, DimKind.CENTRE_LINE, 150),
    ]
    assert girth(runs) == {
        "ext_girth_230_m": 10.0,
        "int_girth_150_m": 3.0,
        "total_girth_150_m": 3.0,
        "total_girth_230_m": 10.0,
    }


def test_extraction_parsing_asks_instead_of_guessing():
    from plan2cost.extract import parse_json, to_runs

    reply = 'Here you go:\n```json\n{"wall_runs": [' \
        '{"label": "A", "length_mm": 9830, "kind": "end_to_end", "thickness_mm": 230, "external": true},' \
        '{"label": "B", "length_mm": 3000, "kind": "unknown", "thickness_mm": 230}], "questions": []}\n```'
    runs, questions = to_runs(parse_json(reply))
    assert [centre_line_m(r) for r in runs] == [9.6]
    assert len(questions) == 1 and questions[0].startswith("B:")
