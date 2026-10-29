import cv2
import numpy as np

from plan2cost.drawing_model import DrawingModel, build_model, stable_order
from plan2cost.markup import draw_markup
from plan2cost.qc import check_dangling, check_double_counting, check_extents, check_free_ends, run_checks
from plan2cost.walls_cv import Wall


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
