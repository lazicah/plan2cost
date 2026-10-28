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
