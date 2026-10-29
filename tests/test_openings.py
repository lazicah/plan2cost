from plan2cost.drawing_model import build_model
from plan2cost.openings import candidates, counts_by_mark, dimension_candidates
from plan2cost.walls_cv import Wall
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
    import plan2cost.dims as dims
    from plan2cost.dims import DimToken

    m = build_model(result_for(box_walls()), "ground", 1)  # 30 mm per point
    # a horizontal chain 2 m above the top wall (y = -2000 mm), a 1200 dimension centred at x = 3000 mm: points = mm / 30
    tok = DimToken(1200, 3000 / 30 - 10, -2000 / 30 - 3, 3000 / 30 + 10, -2000 / 30 + 3)
    monkeypatch.setattr(dims, "dimension_tokens", lambda pdf, page: [tok, DimToken(777, 0, 0, 10, 6)])
    c = dimension_candidates(m, "x.pdf", 1, {1200}, [])
    assert len(c) == 1 and c[0]["wall"] == "W-001" and c[0]["width_mm"] == 1200 and abs((c[0]["x0"] + c[0]["x1"]) / 2 - 3000) < 1
    assert dimension_candidates(m, "x.pdf", 1, {1200}, [{"wall": "W-001", "x0": 2500, "x1": 3500, "y0": 0, "y1": 0}]) == []  # a gap already there


def test_counts_by_mark_split_by_the_side_of_the_wall():
    from plan2cost.drawing_model import Element

    m = build_model(result_for(box_walls()), "ground", 1)
    for i, (sub, mark) in enumerate([("external", "W1"), ("external", "W1"), ("internal", "W1"), ("internal", "D2"), ("external", "")]):
        m.elements.append(Element(f"WN-{i}", "window", sub, 1, "ground", "h", 0, 0, 900, 0, 0.9, 230.0, mark=mark))
    assert counts_by_mark(m) == {"W1": {"external": 2, "internal": 1}, "D2": {"external": 0, "internal": 1}}
