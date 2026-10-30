from plan2cost.drawing.model import build_model
from plan2cost.drawing.openings import candidates, dimension_candidates
from tests.test_drawing_model import box_walls, result_for


def model_with_gaps():
    walls = box_walls()
    walls[0].gaps = [(1000.0, 1900.0), (4000.0, 4600.0), (50.0, 700.0), (7500.0, 7950.0)]  # the last two are at the ends of the run
    return build_model(result_for(walls), "ground", 1)


def test_gaps_become_candidates_with_width_and_side_and_end_gaps_are_not_openings():
    m = model_with_gaps()
    c = candidates(m)
    assert [x["width_mm"] for x in c] == [900, 600] and all(x["wall"] == "W-001" and x["external"] for x in c)
    assert c[0]["y0"] == c[0]["y1"] == 0.0 and c[0]["x0"] == 1000.0


def test_a_printed_width_makes_a_candidate_on_the_nearest_wall_of_the_chain_direction(monkeypatch):
    import plan2cost.drawing.dims as dims
    from plan2cost.drawing.dims import DimToken

    m = build_model(result_for(box_walls()), "ground", 1)  # 30 mm per point
    # a horizontal chain 2 m above the top wall (y = -2000 mm), a 1200 dimension centred at x = 3000 mm: points = mm / 30
    tok = DimToken(1200, 3000 / 30 - 10, -2000 / 30 - 3, 3000 / 30 + 10, -2000 / 30 + 3)
    monkeypatch.setattr(dims, "dimension_tokens", lambda pdf, page: [tok, DimToken(777, 0, 0, 10, 6)])
    c = dimension_candidates(m, "x.pdf", 1, {1200}, [])
    assert len(c) == 1 and c[0]["wall"] == "W-001" and c[0]["width_mm"] == 1200 and abs((c[0]["x0"] + c[0]["x1"]) / 2 - 3000) < 1
    assert dimension_candidates(m, "x.pdf", 1, {1200}, [{"wall": "W-001", "x0": 2500, "x1": 3500, "y0": 0, "y1": 0}]) == []  # a gap already there

def test_a_window_drawn_inside_the_wall_with_a_sill_line_is_a_candidate_but_plain_wall_is_not():
    import cv2
    import numpy as np

    from plan2cost.drawing.openings import jamb_candidates

    scale = 0.1  # px per mm: a 230 mm wall is 23 px thick
    img = np.full((400, 1000, 3), 255, np.uint8)
    m = build_model(result_for(box_walls()[:4]), "ground", 1)
    for e in m.walls():  # move the model onto the picture: shift everything by 1000 mm so the band is on the picture
        e.x0_mm, e.x1_mm, e.y0_mm, e.y1_mm = e.x0_mm + 1000, e.x1_mm + 1000, e.y0_mm + 1000, e.y1_mm + 1000
    top = next(e for e in m.walls() if e.orient == "h" and e.y0_mm == 1000)
    cy, h = int(top.y0_mm * scale), 11
    for x0, x1, window in ((100, 300, False), (300, 420, True), (420, 700, False)):  # plain wall, a 1200 mm window, plain wall: two thick faces, and a sill line in the window
        cv2.rectangle(img, (x0, cy - h), (x1, cy - h + 3), (0, 0, 0), -1)
        cv2.rectangle(img, (x0, cy + h - 3), (x1, cy + h), (0, 0, 0), -1)
        if window:
            cv2.rectangle(img, (x0, cy - 1), (x1, cy + 1), (0, 0, 0), -1)
    for x in (100, 300, 420, 700):  # heavy jamb lines across the wall
        cv2.rectangle(img, (x - 1, cy - h), (x + 2, cy + h), (0, 0, 0), -1)
    found = [c for c in jamb_candidates(m, img, scale, []) if c["wall"] == top.id]
    assert len(found) == 1 and 1100 <= found[0]["width_mm"] <= 1250 and found[0]["source"] == "between jamb lines"  # the two plain walls have no sill line


def test_a_door_between_a_wall_end_and_the_next_wall_is_a_candidate_and_a_wall_that_meets_is_not():
    from plan2cost.drawing.openings import end_gap_candidates
    from plan2cost.drawing.walls_cv import Wall

    walls = box_walls()[:4] + [Wall("v", 4000.0, 0.0, 2500.0, 230.0)]  # a partition that stops 3.5 m short of the bottom wall: too far to be a door
    m = build_model(result_for(walls, [1, 1, 1, 1, 0]), "ground", 1)
    assert end_gap_candidates(m, []) == []
    walls = box_walls()[:4] + [Wall("v", 4000.0, 0.0, 5000.0, 230.0)]  # stops 1.0 m short of the bottom wall (y = 6000): clear gap of 885 mm to its face
    m = build_model(result_for(walls, [1, 1, 1, 1, 0]), "ground", 1)
    c = end_gap_candidates(m, [])
    assert len(c) == 1 and c[0]["orient"] == "v" and 850 <= c[0]["width_mm"] <= 900 and c[0]["source"] == "between a wall end and the next wall"
    assert end_gap_candidates(m, c) == []  # not doubled when a gap was already found there
