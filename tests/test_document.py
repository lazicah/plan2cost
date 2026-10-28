from plan2cost.document import plan_openings_to_openings, score_plan_openings

TRUTH = {"AW1": {"width_mm": 600, "height_mm": 1800, "quantity": 2}, "TD2": {"width_mm": 900, "height_mm": 2100, "quantity": 3}}


def test_score_plan_openings_matches_each_schedule_opening_once():
    found = [{"kind": "window", "width_mm": 600, "count": 3}, {"kind": "door", "width_mm": 900, "count": 2}]
    s = score_plan_openings(found, TRUTH)
    assert s["schedule_openings"] == 5 and s["matched"] == 4 and s["found"] == 5


def test_missing_height_falls_back_and_asks():
    ops, q = plan_openings_to_openings({"openings": [{"floor": "ground", "kind": "window", "width_mm": 900, "height_mm": None, "wall": "external", "count": 2}]})
    assert ops[0].height_m == 1.2 and ops[0].external and any("assumed 1200mm" in x for x in q)


def test_score_windows_by_floor():
    from plan2cost.document import score_windows_by_floor

    found = [{"floor": "ground", "kind": "window", "width_mm": 900, "count": 2}, {"floor": "first", "kind": "window", "width_mm": 600, "count": 5},
             {"floor": "first", "kind": "door", "width_mm": 900, "count": 9}]
    truth = {"_note": "x", "ground": {"900": 4, "600": 14}, "first": {"600": 4}}
    assert score_windows_by_floor(found, truth) == {"ground": {"900": (2, 4), "600": (0, 14)}, "first": {"600": (5, 4)}}
