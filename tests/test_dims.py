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


def test_tight_slice_sits_inward_of_the_chain():
    from PIL import Image
    from plan2cost.openings_from_dims import tight_slice

    img = Image.new("RGB", (1000, 800))
    top = DimToken(600, 400, 100, 409, 106)   # horizontal token on the top chain
    crop = tight_slice(img, top, 1.0, "top")
    assert crop.size == (160, 400)             # 80pt wide x 200pt deep, doubled


def test_mirror_check_splits_flats_and_flags_difference():
    from plan2cost.openings_from_dims import mirror_check

    def rec(side, along, kind="window"):
        return {"floor": "ground", "width_mm": 600, "side": side, "kind": kind, "along_pts": along, "page_w_pts": 1000}

    recs = [rec("top", 100), rec("top", 800), rec("left", 300), rec("right", 300), rec("bottom", 120), rec("top", 130, "door")]
    assert mirror_check(recs) == {"ground": {"600": {"A": 3, "B": 2}}}
