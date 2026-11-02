import cv2
import numpy as np

from plan2cost.drawing.model import build_model, refresh
from plan2cost.drawing.walls_cv import Wall
from plan2cost.facts.verify_walls import add_missed, merge_duplicates, trim_overshoots, verify_walls
from tests.test_drawing_model import box_walls, result_for

SCALE = 0.1  # pixels to a millimetre
BLANK = np.full((700, 900, 3), 255, np.uint8)


def test_an_overshooting_run_is_trimmed_only_when_the_model_says_it_is_not_a_wall():
    walls = box_walls() + [Wall("h", 3000.0, 0.0, 10000.0, 150.0)]  # runs 2 m past the east wall
    m = build_model(result_for(walls, [1, 1, 1, 1, 0, 0]), "ground", 1)
    assert any(i.code == "dangling" for i in m.issues)
    assert trim_overshoots(m, BLANK, SCALE, ask=lambda p, c: {"on_wall": None, "why": "cannot tell"}) == []
    assert max(e.x1_mm for e in m.walls() if e.orient == "h") == 10000.0  # unsure: nothing changed
    log = trim_overshoots(m, BLANK, SCALE, ask=lambda p, c: {"on_wall": False, "why": "a thin grid line"})
    assert [i.code for i in log] == ["trimmed"] and max(e.x1_mm for e in m.walls() if e.orient == "h") == 8000.0
    refresh(m)
    assert not any(i.code == "dangling" for i in m.issues) and m.totals["total_m"] == 8 + 8 + 6 + 6 + 6 + 8


def test_a_run_found_twice_is_dropped_when_it_lies_inside_the_other_on_one_line():
    walls = box_walls() + [Wall("h", 40.0, 1000.0, 3000.0, 230.0)]
    m = build_model(result_for(walls, [1, 1, 1, 1, 0, 1]), "ground", 1)
    n = len(m.walls())
    log = merge_duplicates(m)
    assert [i.code for i in log] == ["merged"] and len(m.walls()) == n - 1
    refresh(m)
    assert not any(i.code == "overlap" for i in m.issues)


def test_runs_190_mm_apart_on_230_mm_walls_are_one_wall():
    walls = box_walls() + [Wall("h", 190.0, 500.0, 4000.0, 150.0)]  # an outer line 190 mm inside the top wall
    m = build_model(result_for(walls, [1, 1, 1, 1, 0, 1]), "ground", 1)
    assert any(i.code == "overlap" for i in m.issues)


def test_a_missed_partition_is_added_when_a_bar_is_there_and_both_ends_meet_walls(tmp_path):
    img = np.full((700, 900, 3), 255, np.uint8)
    cv2.rectangle(img, (393, 0), (407, 600), (0, 0, 0), -1)  # a 140 mm partition at x = 4000 mm, drawn on the plan but not measured
    path = str(tmp_path / "markup.png")
    cv2.imwrite(path, img)
    walls = box_walls()[:4]
    m = build_model(result_for(walls, [1, 1, 1, 1]), "ground", 1)
    m.markup_frame = [0, 0, 1.0, SCALE]
    ask = lambda p, c: {"missed": [{"box": [0.43, 0.0, 0.47, 0.9], "orient": "v", "what": "central partition"}]}
    log = add_missed(m, img, SCALE, path, ask=ask)
    assert [i.code for i in log] == ["added"]
    new = m.walls()[-1]
    assert new.subtype == "internal" and new.orient == "v" and abs(new.x0_mm - 4000) < 30 and 5.5 < new.length_m < 6.6 and new.confidence == "low"


def test_a_missed_wall_the_code_cannot_find_is_left_as_a_question(tmp_path):
    path = str(tmp_path / "markup.png")
    cv2.imwrite(path, BLANK)
    m = build_model(result_for(box_walls()[:4], [1, 1, 1, 1]), "ground", 1)
    m.markup_frame = [0, 0, 1.0, SCALE]
    n = len(m.walls())
    log = add_missed(m, BLANK, SCALE, path, ask=lambda p, c: {"missed": [{"box": [0.4, 0.1, 0.5, 0.9], "orient": "v", "what": "a partition"}]})
    assert [i.code for i in log] == ["missed_not_found"] and len(m.walls()) == n


def test_a_failed_model_call_skips_that_check_and_never_stops_the_run(monkeypatch, tmp_path):
    m = build_model(result_for(box_walls(), [1, 1, 1, 1, 0]), "ground", 1)
    path = str(tmp_path / "m.png")
    cv2.imwrite(path, BLANK)
    import plan2cost.facts.verify_walls as v

    monkeypatch.setattr(v, "_ask", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    assert verify_walls(m, BLANK, SCALE, path) is False


def test_a_pair_of_light_lines_is_not_a_wall_but_a_pair_of_heavy_ones_is():
    from plan2cost.facts.verify_walls import _bar

    def drawing(weight):
        img = np.full((300, 1000, 3), 255, np.uint8)
        for y in (100, 123):  # two lines 230 mm apart at 0.1 px per mm
            cv2.rectangle(img, (50, y), (950, y + weight - 1), (0, 0, 0), -1)
        return img

    assert _bar(drawing(5), SCALE, (0, 0, 10000, 3000), "h", min_face_px=3) is not None
    assert _bar(drawing(1), SCALE, (0, 0, 10000, 3000), "h", min_face_px=3) is None  # a porch edge, a kerb or a dimension chain
    assert _bar(drawing(1), SCALE, (0, 0, 10000, 3000), "h") is not None  # without the weight rule it would have been taken for a wall


def test_a_wall_of_light_lines_where_a_tag_stands_is_added_between_two_walls_up_to_the_door_gap():
    from plan2cost.facts.verify_walls import add_walls_at_tags

    img = np.full((600, 700, 3), 255, np.uint8)  # 0.1 px per mm
    for y in (100, 400):
        cv2.rectangle(img, (0, y - 2), (699, y + 2), (0, 0, 0), -1)  # two heavy horizontal walls
    for x in (250, 273):  # two light lines 230 mm apart, from y = 200 px down to the lower wall; between 100 and 200 px is the door gap
        cv2.line(img, (x, 200), (x, 398), (0, 0, 0), 1)
    walls = [Wall("h", 1000.0, 0.0, 7000.0, 230.0), Wall("h", 4000.0, 0.0, 7000.0, 230.0)]
    m = build_model(result_for(walls, [1, 1]), "ground", 1)
    log = add_walls_at_tags(m, [{"tag": "W3", "kind": "window", "x_mm": 2900.0, "y_mm": 3000.0}], img, SCALE)
    new = m.walls()[-1]
    assert [i.code for i in log] == ["added_at_tag"] and new.orient == "v" and 2400 < new.x0_mm < 2700 and new.confidence == "low"
    assert new.y0_mm < 1300 and new.y1_mm > 3800  # up to the upper wall across the door gap, down to the lower wall
    assert add_walls_at_tags(m, [{"tag": "W3", "kind": "window", "x_mm": 2900.0, "y_mm": 3000.0}], img, SCALE) == []  # already there: not added twice
