import cv2
import numpy as np

from plan2cost.drawing.model import DrawingModel, build_model, stable_order
from plan2cost.drawing.markup import draw_markup
from plan2cost.drawing.qc import check_dangling, check_double_counting, check_extents, check_free_ends, run_checks
from plan2cost.drawing.walls_cv import Wall


def box_walls(w=8000.0, d=6000.0, t=230.0):
    """A rectangle of four walls plus one partition, centre-line coordinates in mm."""
    return [Wall("h", 0, 0, w, t), Wall("h", d, 0, w, t), Wall("v", 0, 0, d, t), Wall("v", w, 0, d, t), Wall("v", w / 2, 0, d, 150.0)]


def result_for(walls, fractions=None, scale="printed dimensions"):
    return {"_walls": walls, "_fractions": fractions or [1, 1, 1, 1, 0], "_unit": "pt", "_mm_per_unit": 30.0, "route": "vector", "confidence": "high", "scale": scale,
            "_calibration": {"method": "printed dimensions against the lines they measure", "agree": 0.7, "printed_overall_mm": [8000, 6000]}, "length_m": 8.0, "width_m": 6.0}


def test_ids_are_stable_whatever_the_order_the_walls_arrive_in():
    walls = box_walls()
    shuffled = [walls[i] for i in (3, 0, 4, 2, 1)]
    a = build_model(result_for(walls), "ground", 1)
    b = build_model(result_for(shuffled, [1, 1, 0, 1, 1]), "ground", 1)
    assert [(e.id, e.orient, e.x0_mm, e.y0_mm) for e in a.elements] == [(e.id, e.orient, e.x0_mm, e.y0_mm) for e in b.elements]
    assert a.elements[0].id == "W-001" and stable_order(walls)[0] == 0


def test_the_model_records_totals_connections_and_the_calibration():
    m = build_model(result_for(box_walls()), "ground", 3)
    assert m.totals["total_m"] == 8 + 8 + 6 + 6 + 6 and m.totals["external_m"] == 28.0 and m.totals["internal_m"] == 6.0
    corner = next(e for e in m.elements if e.orient == "h" and e.y0_mm == 0)
    assert len(corner.connected) >= 3  # meets both side walls and the partition
    assert m.calibrations[0].evidence == "directly labelled" and m.calibrations[0].confidence == "high"


def test_a_clean_box_has_no_warnings():
    m = build_model(result_for(box_walls()), "ground", 1)
    assert [i for i in m.issues if i.severity != "info"] == []


def test_duplicate_runs_are_flagged_and_the_building_size_is_checked():
    walls = box_walls() + [Wall("h", 40.0, 1000, 3000, 230.0)]  # the same top wall found again, overlapping
    m = build_model(result_for(walls, [1, 1, 1, 1, 0, 1]), "ground", 1)
    assert any(i.code == "overlap" for i in check_double_counting(m))
    m2 = build_model(result_for(box_walls()), "ground", 1)
    assert check_extents(m2, [8000, 6000]) == [] and any(i.severity == "warn" for i in check_extents(m2, [20000, 15000]))


def test_a_run_past_the_building_and_ends_that_meet_nothing_are_flagged():
    walls = box_walls() + [Wall("h", 3000.0, -5000.0, 0.0, 230.0)]  # a long run sticking out of the west wall
    m = build_model(result_for(walls, [1, 1, 1, 1, 0, 1]), "ground", 1)
    assert any(i.code == "dangling" for i in check_dangling(m))
    loose = [Wall("h", 1000.0 * i, 0, 3000, 230.0) for i in range(6)] + [Wall("v", 5000.0 + 1000 * i, 0, 3000, 230.0) for i in range(3)]
    ml = build_model(result_for(loose, [0.0] * 9), "ground", 1)
    assert any(i.code == "free_ends" for i in check_free_ends(ml))


def test_the_model_round_trips_through_json_and_the_markup_is_written(tmp_path):
    m = build_model(result_for(box_walls()), "ground", 1)
    m.save(tmp_path / "m.json")
    again = DrawingModel.load(tmp_path / "m.json")
    assert [e.id for e in again.elements] == [e.id for e in m.elements] and again.calibrations[0].method == m.calibrations[0].method
    img = tmp_path / "plan.png"
    cv2.imwrite(str(img), np.full((400, 500, 3), 255, np.uint8))
    m.calibrations[0].mm_per_unit = 20.0  # 8000mm -> 400 px, 6000mm -> 300 px
    out = draw_markup(m, str(tmp_path / "markup.jpg"), image=str(img))
    assert cv2.imread(out) is not None and run_checks(m, [8000, 6000]) is not None


def test_the_model_review_only_adds_issues_and_ignores_ids_it_does_not_know(monkeypatch):
    import plan2cost.kit.client as client
    from plan2cost.facts.review import review_model

    monkeypatch.setattr(client, "image_part", lambda p: {"type": "text", "text": "image"})
    monkeypatch.setattr(client, "chat_json", lambda content: {"missed": [{"where": "north edge", "what": "outer wall has no line"}], "not_walls": [{"id": "002", "why": "furniture"}, {"id": "099", "why": "unknown"}],
                                                            "duplicates": [{"ids": ["001", "003"]}], "wrong_side": [{"id": "005", "why": "inside"}], "overall": "x"})
    m = build_model(result_for(box_walls()), "ground", 1)
    before = (m.totals["total_m"], len(m.elements))
    issues = review_model(m, "unused.jpg")
    assert {i.code for i in issues} == {"review_missed", "review_not_wall", "review_duplicate", "review_side"}
    assert all(i.source == "model review" for i in issues) and all(i.elements == [] or all(e in {x.id for x in m.elements} for e in i.elements) for i in issues)
    assert (m.totals["total_m"], len(m.elements)) == before  # a review never changes a measurement


def test_located_openings_set_the_side_and_the_rest_stays_on_the_schedule():
    from plan2cost.tools.estimate import merge_located_openings

    schedule = [{"label": "AW1", "width_m": 0.6, "height_m": 1.8, "count": 22, "kind": "window", "external": True},
                {"label": "TD2", "width_m": 0.9, "height_m": 2.1, "count": 10, "kind": "door", "external": False}]
    out = merge_located_openings(schedule, {"ground": {"AW1": {"external": 12, "internal": 1}}, "first": {"AW1": {"external": 5, "internal": 0}}})
    aw = [(o.count, o.external) for o in out if o.label == "AW1"]
    assert sorted(aw) == sorted([(17, True), (1, False), (4, True)])  # 17 external and 1 internal found; the 4 not found keep the old rule
    assert sum(o.count for o in out if o.label == "AW1") == 22 and [(o.count, o.external) for o in out if o.label == "TD2"] == [(10, False)]
    assert sum(o.count for o in merge_located_openings(schedule, {"x": {"AW1": {"external": 30, "internal": 0}}}) if o.label == "AW1") == 22  # never more than scheduled
