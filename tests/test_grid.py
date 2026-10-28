from plan2cost.grid import Grid, GridLine, calibrate


def grid():
    return Grid([GridLine("1", 100, "x"), GridLine("2", 151, "x"), GridLine("3", 253, "x")], [GridLine("A", 50, "y"), GridLine("B", 135, "y")])


def test_bays_use_the_scale_to_give_millimetres():
    g = grid()
    g.mm_per_pt = 35.28
    assert g.bays("x") == [("1", "2", 1799), ("2", "3", 3599)] and g.bays("y") == [("A", "B", 2999)]


def test_scale_is_fitted_to_printed_chains_and_refused_when_nothing_matches():
    g = calibrate(grid(), [1800, 3600, 3000, 9600])
    assert round(g.mm_per_pt, 1) == 35.3 and "bays match" in g.scale_basis
    assert calibrate(grid(), [111, 222]).mm_per_pt is None
