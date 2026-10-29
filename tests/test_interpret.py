from plan2cost.drawing.interpret import _block_for, scale_from_overall
from plan2cost.drawing.scale import _mode, stated_scale, within_stated
from plan2cost.drawing.vector_walls import Line, axis_lines, drop_centreline_halves, largest_cluster, pair_walls
from plan2cost.drawing.vector import Seg
from plan2cost.drawing.walls_cv import Wall


def test_stated_scale_is_read_from_the_title_block_text():
    assert stated_scale("DRAWING TITLE FLOOR PLAN  SCALE: 1: 100  DATE") == 100
    assert stated_scale("nothing here") is None


def test_stated_scale_only_bounds_the_fit():
    s0 = 100 * 25.4 / 72  # 35.28 mm per point
    assert within_stated([5.0, 32.0, 40.4, 90.0], 100) == [32.0, 40.4]  # a sheet can be plotted smaller or larger than stated
    assert within_stated([5.0, 90.0], None) == [5.0, 90.0] and s0 > 35


def test_the_scale_is_the_clear_peak_of_the_votes():
    votes = [32.5, 32.4, 32.6, 32.5, 32.45, 40.0, 12.0, 70.0]
    m = _mode(votes)
    assert abs(m["mm_per_pt"] - 32.5) < 0.2 and m["dominance"] >= 2


def test_overall_dimensions_pick_the_factor_that_fits_both_axes():
    # extents measured at a first-pass scale are 15000 x 9000; the printed overall values are 22500 and 13500 (factor 1.5), plus a decoy
    f, err = scale_from_overall(15000, 9000, [22500, 13500, 4000])
    assert abs(f - 1.5) < 0.01 and err < 0.01
    assert scale_from_overall(15000, 9000, [22500, 9000]) is None  # the axes disagree: no fit is better than a wrong one


def test_the_dimension_fit_must_point_at_a_block_size():
    assert _block_for(1.0) == 225 and _block_for(0.667) == 150
    assert _block_for(1.5) is None  # 337mm is not a wall


def test_a_centre_line_down_a_wall_does_not_make_two_thin_walls():
    # faces at y=0 and y=7 (a 230 wall at 32.9 mm/pt) with a grid line at y=3.5 along the same span
    lines = [Line("h", 0.0, 0, 60, 0.24), Line("h", 7.0, 0, 60, 0.24), Line("h", 3.5, 0, 60, 0.24)]
    pieces = pair_walls(lines, 32.9, min_run_mm=350)
    kept = drop_centreline_halves(pieces)
    assert len(pieces) == 3 and len(kept) == 1 and abs(kept[0]["gap_pt"] - 7.0) < 0.01


def test_a_table_is_not_the_building():
    table = [Wall("h", 100.0 * i, 0, 3000, 230) for i in range(10)]  # many parallel lines, one direction only
    building = [Wall("h", 0, 0, 8000, 230), Wall("h", 6000, 0, 8000, 230), Wall("v", 0, 0, 6000, 230), Wall("v", 8000, 0, 6000, 230)]
    far = [Wall(w.orient, w.centre_mm + 90000, w.start_mm + 90000, w.end_mm + 90000, w.thickness_mm) for w in table]
    assert largest_cluster(far + building) == building


def test_collinear_pieces_join_into_one_line_and_dashes_are_ignored():
    segs = [Seg(0, 5, 10, 5, 1.0), Seg(10, 5, 25, 5, 1.0), Seg(40, 5, 50, 5, 1.0, dashed=True)]
    ls = axis_lines(segs, min_len_pt=2)
    assert len(ls) == 1 and ls[0].a == 0 and ls[0].b == 25


def test_extents_must_match_printed_overall_dimensions():
    from plan2cost.drawing.interpret import extents_match_printed

    assert extents_match_printed(14.03, 11.79, [14250, 12000, 3000, 600])  # outer extents are within a wall thickness of the grid strings
    assert extents_match_printed(11.8, 14.0, [14250, 12000])  # either axis order
    assert not extents_match_printed(30.0, 20.0, [14250, 12000])  # a network of grid lines spans something else
