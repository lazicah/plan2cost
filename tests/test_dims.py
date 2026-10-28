from plan2cost.dims import DimToken, chains, width_candidates


def row(y, xs, value=600):
    return [DimToken(value, x, y, x + 9, y + 6) for x in xs]


def test_chains_need_a_row_of_tokens():
    toks = row(100, [10, 60, 110, 160]) + row(400, [10, 60]) + row(700, [10, 60, 110, 160])
    assert len(chains(toks)) == 2  # the two-token row is not a chain


def test_same_window_on_two_chain_layers_counts_once():
    layer1 = row(100, [10, 60, 110, 160], 900) + row(100, [200], 600)
    layer2 = row(115, [10, 60, 110, 160], 900) + row(115, [200], 600)
    outer = row(400, [10, 60, 110, 160], 900)
    toks = layer1 + layer2 + outer
    assert len(width_candidates(toks, 600)) == 1
