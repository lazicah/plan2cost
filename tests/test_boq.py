from plan2cost.boq import foundation_boq, price_boq, strip_inputs
from plan2cost.tools.foundation import GridLine, PadBase, foundation_takeoff

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


def test_strip_girths_from_extracted_runs():
    from plan2cost.extract_foundation import strip_girths

    data = {"strip_runs": [{"length_mm": 50000, "count": 1}, {"length_mm": 10000, "count": 2}]}
    g = strip_girths(data, [PadBase("1", 1.2, 1.2, 5)])
    assert g == {"fdn_blockwork_girth_230_m": 70, "strip_trench_girth_230_m": 64}


def test_foundation_extras_priced_and_laterite_left_unpriced():
    import json
    from plan2cost.boq import foundation_extras

    items = foundation_extras([PadBase("1", 1.2, 1.2, 4, 0.25, ("06-Y1202@200c/c B",))], 20, slab_area_m2=200.55, fill_area_m2=184)
    out = price_boq(items, json.load(open("data/rates.json")))
    assert out["unpriced"] == ["laterite_m3"]
    assert {i.key for i in items} >= {"column_base_concrete_m3", "rebar_y12_foundations_t", "ground_slab_m3"}


def test_trench_width_is_three_times_the_block_unless_drawn():
    s225, log225, _ = strip_inputs(drawn={"block_mm": 225})
    s150, _, _ = strip_inputs(drawn={"block_mm": 150})
    assert (s225.width_mm, s150.width_mm) == (675, 450)
    assert next(a for a in log225 if a.name == "width_mm").source == "assumed"
    drawn, _, _ = strip_inputs(drawn={"block_mm": 225, "width_mm": 600})
    assert drawn.width_mm == 600
