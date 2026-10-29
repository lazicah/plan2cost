from plan2cost.drawing.dims import DimToken, chains


def row(y, xs, value=600):
    return [DimToken(value, x, y, x + 9, y + 6) for x in xs]


def test_chains_need_a_row_of_tokens():
    toks = row(100, [10, 60, 110, 160]) + row(400, [10, 60]) + row(700, [10, 60, 110, 160])
    assert len(chains(toks)) == 2  # the two-token row is not a chain