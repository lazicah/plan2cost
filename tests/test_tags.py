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


def test_a_tag_is_put_at_its_true_place_and_one_that_is_not_there_is_dropped():
    from plan2cost.facts.tags import refine

    img = np.zeros((2000, 3000, 3), np.uint8)  # 0.1 px per mm: 20 m x 30 m... a 7 m square is 700 px
    first = [("W3", 10000.0, 10000.0), ("D1", 20000.0, 5000.0), ("W9", 15000.0, 15000.0)]

    def ask(prompt, path):
        if '"W3"' in prompt:
            return {"found": True, "x": 0.5, "y": 0.5}  # the tag is at the middle of the square around the first place
        if '"D1"' in prompt:
            return {"found": True, "x": 0.75, "y": 0.25}
        return {"found": False}  # W9 was misread
    got = refine(img, 0.1, first, ask=ask)
    assert [t[0] for t in got] == ["W3", "D1"] and got[0][1:] == (10000.0, 10000.0) and got[1][1] > 20000 and got[1][2] < 5000


def test_a_pdf_text_layer_with_opening_tags_is_read_as_text_and_one_without_is_left_to_the_model():
    from plan2cost.facts.tags import has_text_tags

    assert has_text_tags("KITCHEN W1 W2 D1 D2 BATH 3600 W3") and not has_text_tags("KITCHEN BEDROOM 3600 2400 A1 B2 C3 K1")  # grid bubbles and room codes are not opening tags
    assert not has_text_tags("W1 D1")


def test_tags_read_without_the_scale_come_back_as_fractions_of_the_picture():
    from plan2cost.facts.tags import read_tags_fractional

    img = np.zeros((1000, 2000, 3), np.uint8)

    def ask(prompt, path):
        if "Does this floor plan label" in prompt:
            return {"tagged": True}
        if "List every window or door tag" in prompt:
            return {"tags": [{"tag": "W1", "x": 0.5, "y": 0.5}]} if path.endswith("tile0.jpg") else {"tags": []}
        return {"found": True, "x": 0.5, "y": 0.5}  # the second look: the tag is at the middle of the square around its first place
    got = read_tags_fractional(img, ask=ask)
    assert len(got) == 1 and got[0][0] == "W1" and 0 < got[0][1] < 0.5 and 0 < got[0][2] < 0.5  # tile 0 is the top-left quarter
