import numpy as np

from plan2cost.facts.tags import clean, dedupe, read_tags, tiles, to_sheet_mm


def test_tiles_cover_the_page_and_overlap_so_a_cut_tag_is_whole_in_the_next_tile():
    ts = tiles(1000, 3000)
    assert len(ts) == 4 and min(t[0] for t in ts) == 0 and max(t[2] for t in ts) == 3000 and min(t[1] for t in ts) == 0 and max(t[3] for t in ts) == 1000
    assert ts[0][2] > ts[1][0]  # neighbours overlap


def test_a_place_on_a_tile_becomes_sheet_millimetres_and_bad_entries_are_dropped():
    tile = (1000, 500, 2000, 1500)
    assert to_sheet_mm(tile, 0.5, 0.5, 0.1) == (15000.0, 10000.0)
    got = clean([{"tag": "w3", "x": 0.5, "y": 0.5}, {"tag": "Kitchen", "x": 0.1, "y": 0.1}, {"tag": "D1", "x": 1.4, "y": 0.2}, {"tag": "D2"}, "junk"], tile, 0.1)
    assert got == [("W3", 15000.0, 10000.0)]


def test_the_same_tag_seen_in_two_overlapping_tiles_counts_once_but_two_of_the_same_kind_apart_count_twice():
    assert dedupe([("W1", 1000, 1000), ("W1", 1300, 1100), ("W1", 9000, 1000), ("D1", 1000, 1000)]) == [("W1", 1000, 1000), ("W1", 9000, 1000), ("D1", 1000, 1000)]


def test_a_plan_that_does_not_tag_its_openings_costs_one_call():
    calls = []

    def ask(prompt, path):
        calls.append(prompt[:20])
        return {"tagged": False}

    assert read_tags(np.zeros((100, 300, 3), np.uint8), 0.1, ask=ask) == [] and len(calls) == 1
