from plan2cost.takeoff.boq import foundation_boq, load_rates, price_boq, strip_inputs
from plan2cost.takeoff.foundation import GridLine, PadBase, foundation_takeoff

LINES = [GridLine("all", runs=[(104.835, 1)], deductions=[(35.145, 1)])]
PADS = [PadBase("1", 1.2, 1.2, 4)]


def test_missing_inputs_are_assumed_and_flagged():
    s, log, grade = strip_inputs(drawn={"width_mm": 600})
    assert s.width_mm == 600 and grade == 20
    by = {a.name: a for a in log}
    assert by["width_mm"].source == "drawing" and by["trench_depth_m"].source == "assumed"
    assert by["trench_depth_m"].basis


def test_boq_items_and_pricing_never_invent_rates():
    s, _, grade = strip_inputs()
    items = foundation_boq(foundation_takeoff(LINES, PADS, s), s, grade)
    assert items[0].description.startswith("Trench excavation") and items[0].unit == "m3"
    out = price_boq(items, {"currency": "NGN", "rates": {"trench_excavation_strip_m3": 1000}})
    assert out["total"] == items[0].qty * 1000
    assert "strip_footing_concrete_m3" in out["unpriced"]



def test_foundation_extras_are_all_priced_and_a_rate_in_both_bills_takes_the_higher():
    from plan2cost.takeoff.boq import foundation_extras

    items = foundation_extras([PadBase("1", 1.2, 1.2, 4, 0.25, ("06-Y1202@200c/c B",))], 20, slab_area_m2=200.55, fill_area_m2=184)
    rates = load_rates()
    out = price_boq(items, rates)
    assert out["unpriced"] == [] and rates["source"]["laterite_m3"] == "Asaba bill only"  # only the Asaba bill has a laterite rate
    assert rates["rates"]["frame_steel_t"] == 1699135 and rates["source"]["frame_steel_t"].startswith("both bills")  # Owerri 1,699,135 against Asaba 1,319,880
    assert {i.key for i in items} >= {"column_base_concrete_m3", "rebar_y12_foundations_t", "ground_slab_m3"}


def test_trench_width_is_three_times_the_block_unless_drawn():
    s225, log225, _ = strip_inputs(drawn={"block_mm": 225})
    s150, _, _ = strip_inputs(drawn={"block_mm": 150})
    assert (s225.width_mm, s150.width_mm) == (675, 450)
    assert next(a for a in log225 if a.name == "width_mm").source == "assumed"
    drawn, _, _ = strip_inputs(drawn={"block_mm": 225, "width_mm": 600})
    assert drawn.width_mm == 600


def test_substructure_extras_follow_the_authors_sheet():
    from plan2cost.takeoff.boq import StripSection, substructure_extras

    pads = [PadBase("1", 1.2, 1.2, 4, 0.25), PadBase("2", 1.4, 1.4, 5, 0.25), PadBase("3", 1.5, 1.5, 5, 0.25), PadBase("4", 1.6, 1.6, 4, 0.4), PadBase("5", 1.7, 1.7, 1, 0.45)]
    s = StripSection(width_mm=690, footing_thickness_m=0.225, trench_depth_m=1.35, block_mm=225)
    t = {"trench_excavation_strip_m3": 58, "pit_excavation_column_bases_m3": 48, "earthwork_support_m2": 299.52, "strip_footing_concrete_m3": 11,
         "fdn_blockwork_girth_225_m": 105, "fdn_blockwork_225_m2": 89}
    got = {i.key: i.qty for i in substructure_extras(t, s, pads, 70, 19.1, 10.5, {"column_base_concrete_m3": 12, "column_concrete_m3": 2.61})}
    # the author's 226 came from a manual 0.95 he chose at the time, not a rule, so it is not reproduced; the 400/450mm bases are the sheet before the author corrected them to 250
    assert got["topsoil_strip_m2"] == 238 and got["excavated_surface_treatment_m2"] == 300 and got["levelling_compaction_m2"] == 89
    assert got["blinding_foundations_m3"] == 7 and got["formwork_foundation_sides_m"] == 110  # metres of base sides (BESMM4 1.11.6.13.1)
    assert got["topsoil_disposal_m3"] == 36  # 238 m2 x 0.15m, whole units
    assert (got["disposal_off_site_m3"], got["backfill_around_foundations_m3"]) == (53, 53)


def test_the_finish_level_changes_only_the_lines_priced_for_different_specifications():
    std, pre = load_rates("standard"), load_rates("premium")
    changed = {k for k in std["rates"] if std["rates"][k] != pre["rates"][k]}
    assert changed == {"floor_finish_m2", "sanitary_wc_nr", "sanitary_basin_nr", "sanitary_sink_nr", "sanitary_shower_nr", "door_internal_nr", "electrical_light_nr", "roof_covering_m2"}
    assert all(std["rates"][k] < pre["rates"][k] for k in changed if k != "roof_covering_m2") and std["tier"] == "standard"
    assert std["rates"]["ext_blockwork_230_m2"] == pre["rates"]["ext_blockwork_230_m2"] and load_rates("nonsense")["tier"] == "standard"
