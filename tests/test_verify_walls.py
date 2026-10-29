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


def test_a_run_found_twice_is_dropped_only_when_the_model_says_one_wall():
    walls = box_walls() + [Wall("h", 40.0, 1000.0, 3000.0, 230.0)]
    m = build_model(result_for(walls, [1, 1, 1, 1, 0, 1]), "ground", 1)
    n = len(m.walls())
    assert merge_duplicates(m, BLANK, SCALE, ask=lambda p, c: {"same_wall": False}) == [] and len(m.walls()) == n
    log = merge_duplicates(m, BLANK, SCALE, ask=lambda p, c: {"same_wall": True, "why": "one wall"})
    assert [i.code for i in log] == ["merged"] and len(m.walls()) == n - 1


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
