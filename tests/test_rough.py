from plan2cost.takeoff.boq import load_rates, price_boq
from plan2cost.takeoff.rough import FloorData, estimate
from plan2cost.takeoff.walls import Opening

RATES = load_rates()
OPS = [Opening("W1200", 1.2, 1.2, 12, "window", True, True), Opening("D900", 0.9, 2.1, 10, "door", False, True), Opening("D1200", 1.2, 2.1, 1, "door", True, True)]


def ground():
    return FloorData("ground", 80.0, 80.0, 39, 10.4, 17.2, 25.0, OPS, ["Kitchen", "Bath/wc", "Bath/wc", "Lounge"])


def first():
    return FloorData("first", 58.0, 48.0, 20, 10.4, 14.5, 17.0, [], ["Bedroom", "Bath/wc", "W.C"])


def run_estimate(floors, **inputs):
    base = {"storey_height_m": 3.0, "roof_type": "hip"}
    items, ass, work = estimate(floors, {**base, **inputs}, RATES["rates"])
    return {i.key: i for i in items}, ass, work, price_boq(list(items), RATES)


def test_every_estimated_line_has_an_ordered_range_and_names_its_coefficients():
    by, _, _, priced = run_estimate([ground(), first()])
    est = [i for i in by.values() if i.basis == "estimated"]
    assert est and all(i.qty_low <= i.qty <= i.qty_high and i.coef for i in est)
    assert priced["total_low"] <= priced["total"] <= priced["total_high"] and 0 < priced["estimated_share"] < 1


def test_measured_lines_have_no_range_and_come_from_the_plan_dimensions():
    by, _, work, _ = run_estimate([ground(), first()])
    assert by["ext_blockwork_230_m2"].basis == "measured" and by["ext_blockwork_230_m2"].qty_low is None
    assert work["gross_floor_area_m2"] == round(10.4 * 17.2 + 10.4 * 14.5, 1)


def test_the_storey_height_the_user_enters_scales_the_walls():
    low, *_ = run_estimate([ground(), first()], storey_height_m=3.0)
    high, *_ = run_estimate([ground(), first()], storey_height_m=3.6)
    assert high["ext_blockwork_230_m2"].qty > low["ext_blockwork_230_m2"].qty * 1.15


def test_roof_types_use_their_own_rules_and_a_flat_roof_is_a_slab():
    hip, _, _, _ = run_estimate([ground(), first()], roof_type="hip")
    gable, _, _, _ = run_estimate([ground(), first()], roof_type="gable")
    flat, _, _, _ = run_estimate([ground(), first()], roof_type="flat")
    assert hip["roof_covering_m2"].qty_high > gable["roof_covering_m2"].qty_high  # a hip roof allows for its complexity
    assert "roof_covering_m2" not in flat and {"roof_slab_concrete_m3", "roof_screed_m2", "roof_membrane_m2"} <= set(flat)


def test_a_pitch_entered_by_the_user_removes_the_pitch_range():
    free, *_ = run_estimate([ground(), first()], roof_type="gable")
    fixed, *_ = run_estimate([ground(), first()], roof_type="gable", pitch_deg=30, overhang_m=0.45)
    spread = lambda i: i.qty_high - i.qty_low  # noqa: E731
    assert spread(fixed["roof_covering_m2"]) < spread(free["roof_covering_m2"]) and fixed["roof_covering_m2"].qty_low == fixed["roof_covering_m2"].qty_high


def test_a_single_storey_building_has_no_beams_columns_slab_or_stairs_only_strip_foundation_and_lintels():
    by, ass, _, _ = run_estimate([ground()])
    assert not {"suspended_slab_concrete_m3", "staircase_concrete_m3", "frame_beams_concrete_m3", "frame_columns_concrete_m3", "frame_steel_t"} & set(by)
    assert "strip_footing_concrete_m3" in by and "column_base_concrete_m3" not in by and any(a["name"] == "frame_single_storey" for a in ass)


def test_lintels_are_concrete_formwork_and_steel_by_length_not_pieces():
    by, ass, _, _ = run_estimate([ground()])
    assert not [k for k in by if k.endswith("_nr") and k.startswith("lintel")]
    assert {"lintel_concrete_m3", "lintel_formwork_m2", "lintel_steel_kg"} <= set(by)
    assert by["lintel_steel_kg"].basis == "estimated" and by["lintel_concrete_m3"].rate == 153950 and by["lintel_steel_kg"].rate == 1699.13  # 1,699,135 a tonne
    assert any(a["name"] == "lintel_bearing_mm" for a in ass)


def test_wet_rooms_set_the_sanitary_fittings_and_openings_are_priced_from_their_size():
    by, _, _, _ = run_estimate([ground(), first()])
    assert by["sanitary_wc_nr"].qty == 4 and by["sanitary_sink_nr"].qty == 1
    assert by["opening_w1200_nr"].rate == 69000 and by["opening_d1200_nr"].rate == 80000 and by["opening_d900_nr"].rate == 38000  # standard finish level: the flush door


def test_no_column_base_lines_appear_when_the_plans_cannot_show_column_bases():
    by, ass, _, _ = run_estimate([ground(), first()])
    assert not {"column_base_concrete_m3", "pit_excavation_column_bases_m3"} & set(by) and any(a["name"] == "column_bases" for a in ass)


def test_openings_the_plan_reader_missed_are_added_as_estimated_lines_and_flagged():
    sparse = FloorData("ground", 80.0, 80.0, 39, 10.4, 17.2, 25.0, [Opening("W1200", 1.2, 1.2, 2, "window", True, True)], [])
    by, ass, _, _ = run_estimate([sparse, first()])
    assert by["windows_estimated_nr"].basis == "estimated" and by["windows_estimated_nr"].qty > 20 and "lintel_concrete_m3" in by and by["lintel_concrete_m3"].basis == "estimated"  # the lintels over estimated openings are in the lintel lines
    assert any(a["name"] == "windows_estimated" for a in ass)
    by, ass, _, _ = run_estimate([ground(), first()])  # 12 windows and 11 doors found on 329 m2: not enough either, but the full set below is
    full = FloorData("ground", 80.0, 80.0, 39, 10.4, 17.2, 25.0, [Opening("W1200", 1.2, 1.2, 20, "window", True, True), Opening("D900", 0.9, 2.1, 10, "door", False, True)], [])
    by, ass, _, _ = run_estimate([full, first()])
    assert "windows_estimated_nr" not in by and "doors_estimated_nr" not in by


def test_a_premium_finish_level_prices_the_same_quantities_higher():
    items, _, _ = estimate([ground(), first()], {"storey_height_m": 3.0, "roof_type": "hip"}, load_rates("premium")["rates"])
    std, pre = run_estimate([ground(), first()])[3], price_boq(items, load_rates("premium"))
    assert pre["total"] > std["total"] * 1.1 and {i.key: i.qty for i in items}["floor_finish_m2"] == run_estimate([ground(), first()])[0]["floor_finish_m2"].qty


def test_a_void_on_an_upper_floor_comes_off_the_slab_and_the_floor_finish():
    g, f = ground(), first()
    base, _, _, _ = run_estimate([g, f])
    f.void_m2 = 20.0
    by, ass, _, _ = run_estimate([g, f])
    assert by["suspended_slab_concrete_m3"].qty < base["suspended_slab_concrete_m3"].qty and by["floor_finish_m2"].qty < base["floor_finish_m2"].qty
    assert any(a["name"] == "voids" for a in ass)


def test_on_a_plan_that_tags_its_openings_the_tags_with_no_opening_found_are_counted_instead_of_a_guess_from_the_floor_area():
    sparse = FloorData("ground", 80.0, 80.0, 39, 10.4, 17.2, 25.0, [Opening("W1200", 1.2, 1.2, 2, "window", True, True)], [])
    sparse.tagged, sparse.unplaced = True, {"window": 7, "door": 3}
    by, ass, _, _ = run_estimate([sparse, first()])
    assert by["windows_estimated_nr"].qty == 7 and by["windows_estimated_nr"].qty_low == 5 and by["doors_estimated_nr"].qty == 3  # 0.7 of seven: a tag can be read twice
    assert "printed tags" in by["windows_estimated_nr"].description and any(a["name"] == "windows_from_tags" for a in ass)
    sparse.unplaced = {}
    by, _, _, _ = run_estimate([sparse, first()])
    assert "windows_estimated_nr" not in by  # every tag has its opening: nothing to add, and no guess from the floor area
