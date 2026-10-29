from plan2cost.drawing.strips import Run, StripLayout, _coverage


def test_net_length_is_centre_length_less_the_bases():
    layout = StripLayout(runs=[Run("A", "x", "1", "3", 4.263, 1.35, "printed"), Run("1", "y", "A", "B", 2.325, 0.65, "printed")])
    assert layout.gross_m == 6.59
    assert layout.net_m == 4.59


def test_a_bay_with_dashed_edges_is_covered_and_one_without_is_not():
    # two dashed edges 7 points either side of a horizontal grid line at y=100, every other 10 points
    segs = [((x, 93.0), (x + 5, 93.0)) for x in range(0, 100, 10)] + [((x, 107.0), (x + 5, 107.0)) for x in range(0, 100, 10)]
    assert _coverage(segs, 100.0, 0, 100, True) > 0.4
    assert _coverage(segs, 200.0, 0, 100, True) == 0
