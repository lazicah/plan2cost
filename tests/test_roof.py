import math
from pathlib import Path

import pytest

from plan2cost.drawing.roof import Roof, dedupe, fit_extent_scale, skeleton
from plan2cost.drawing.vector import Seg
from plan2cost.facts.roof_spec import RoofSpec, levels, parse_spec
from plan2cost.takeoff.roof import pitch_from, roof_boq

SPEC_TEXT = ("0.55mm long-span aluminium roofing sheet on 50 x 50 mm timber purlins 50 x 150 mm timber rafters @ 1200 mm centres "
             "50 x 75 mm timber trusses 50x150 mm timber tie beam @ 1500 mm centres 75x50 mm wall plates")


def test_the_scale_needs_both_axes_to_agree_with_printed_dimensions():
    s, why = fit_extent_scale(281.6, 459.5, [5650, 12370, 17950, 20185], 100)
    assert abs(s - 43.92) < 0.05 and "12370 x 20185" in why
    s, why = fit_extent_scale(281.6, 459.5, [5650, 17950], 100)  # nothing fits the second axis
    assert s is None


def test_a_doubled_edge_is_one_line_and_two_real_lines_are_two():
    a, b = Seg(0, 0, 100, 0, 1.8), Seg(0, 4, 100, 4, 1.8)  # doubled edge, 4 pt apart
    c = Seg(0, 30, 100, 30, 1.8)  # a different line
    assert len(dedupe([a, b, c])) == 2


def test_the_skeleton_is_the_heaviest_weight_with_real_length():
    heavy = [Seg(i * 50, 0, i * 50 + 45, 0, 1.8) for i in range(10)]
    light = [Seg(0, i, 500, i, 0.24) for i in range(200)]
    assert skeleton(heavy + light) == heavy


def test_the_printed_specification_and_levels_are_read_with_their_quotes():
    cov, members = parse_spec(SPEC_TEXT)
    assert cov.startswith("0.55mm long-span aluminium roofing sheet")
    assert members["rafters"] == {"section_mm": [50, 150], "spacing_mm": 1200, "quote": "50 x 150 mm timber rafters @ 1200 mm centres"}
    assert members["purlins"]["spacing_mm"] is None and members["wall_plates"]["section_mm"] == [75, 50]
    w = lambda t, x0, y0, x1, y1: {"t": t, "x0": x0, "y0": y0, "x1": x1, "y1": y1}
    words = [w("Roof", 850, 201, 874, 214), w("Apex", 877, 201, 902, 214), w("10631", 871, 219, 902, 231),
             w("Conc.", 812, 327, 840, 339), w("Fascia", 844, 327, 876, 339), w("level", 879, 327, 902, 339), w("6750", 878, 344, 902, 356), w("3750", 878, 441, 902, 453)]
    assert levels(words) == {"apex_mm": 10631.0, "eaves_mm": 6750.0}


def test_pitch_comes_from_the_printed_rise_over_the_plan_run():
    p = pitch_from(3881, 5914)
    assert p.degrees == 33.3 and abs(p.slope_factor - 1 / math.cos(math.radians(33.3))) < 0.001
    assert pitch_from(0, 5000) is None


def roof():
    return Roof(43.9, "x", 227.22, 66.31, 9.5, 76.6, 26.5, 36.9, 13.1, 5.5, 5914.0, True)


def test_roof_lines_are_on_the_slope_and_what_the_drawing_does_not_say_is_asked():
    spec = RoofSpec(10, "0.55mm long-span aluminium roofing sheet", dict(zip(("purlins", "rafters", "trusses", "wall_plates"), (
        {"section_mm": [50, 50], "spacing_mm": None, "quote": ""}, {"section_mm": [50, 150], "spacing_mm": 1200, "quote": ""},
        {"section_mm": [50, 75], "spacing_mm": None, "quote": ""}, {"section_mm": [75, 50], "spacing_mm": None, "quote": ""}))), {"apex_mm": 10631, "eaves_mm": 6750})
    items, ask, w = roof_boq(roof(), spec, {}, 57.66)
    by = {i.key: i for i in items}
    assert by["roof_covering_m2"].qty == 272 and "33 degree pitch" in by["roof_covering_m2"].description
    assert by["roof_rafters_m"].qty == math.ceil(w["slope_area_m2"] / 1.2 - 1e-6) and by["roof_wall_plates_m"].qty == 58
    assert "roof_purlins_m" not in by and any("purlins" in q for q in ask) and any("trusses" in q for q in ask) and any("fascia" in q for q in ask)
    items, ask, _ = roof_boq(roof(), spec, {"purlin_spacing_mm": 900}, 57.66)
    assert any(i.key == "roof_purlins_m" for i in items)


def test_without_printed_levels_the_pitch_is_asked_not_assumed():
    items, ask, _ = roof_boq(roof(), RoofSpec(10, "", {}, {}), {}, 57.66)
    assert items == [] and "pitch" in ask[0]


@pytest.mark.skipif(not Path("reference/plan2").exists(), reason="the author's drawings are local only")
def test_plan_2_roof_plan_measures_to_the_printed_overall_dimensions():
    from plan2cost.drawing.roof import measure_roof

    r = measure_roof("reference/plan2/ARCHITECTURAL DRAWINGS FOR PROPOSED RESIDENTIAL DEVELOPMENT - MR JESUIT NWACHUKWU.pdf", 5)
    assert abs(r.mm_per_pt - 43.92) < 0.1 and 220 < r.plan_area_m2 < 235 and 5800 < r.half_span_mm < 6000 and r.diagonal_angles_ok
