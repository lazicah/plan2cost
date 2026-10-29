from plan2cost.takeoff.audit import QuoteLine, audit, number_printed, unit_of

ITEMS = {"slab": {"description": "Ground slab", "unit": "m3", "qty": 20.0}, "render": {"description": "Render", "unit": "m2", "qty": 100.0},
         "paint": {"description": "Paint", "unit": "m2", "qty": 100.0}}
RATES = {"slab": 100000, "render": 4000, "paint": 4000}


def line(no, key, unit, qty, rate, amount):
    return QuoteLine(no, "x", unit, qty, rate, amount, key=key)


def codes(res):
    return sorted(f["code"] for f in res["flags"])


def test_a_clean_quote_has_no_warnings_but_what_it_leaves_out():
    res = audit([line("1", "slab", "m³", 20, 100000, 2_000_000), line("2", "render", "sqm", 100, 4000, 400_000)], 2_400_000, ITEMS, RATES)
    assert codes(res) == ["missing"] and res["flags"][0]["line"] == "paint" and res["our_priced_work_not_in_quote"] == 400000


def test_many_missing_items_are_rolled_up():
    items = {f"k{i}": {"description": f"item {i}", "unit": "m2", "qty": 1.0} for i in range(12)} | {"u": {"description": "no rate", "unit": "m", "qty": 1.0}}
    res = audit([], None, items, {f"k{i}": 100 + i for i in range(12)})
    assert len(res["flags"]) == 7 and res["flags"][0]["line"] == "k11" and res["our_priced_work_not_in_quote"] > 0


def test_a_total_that_is_a_little_off_is_still_caught():
    res = audit([line("1", "slab", "m3", 20, 100000, 2_000_000)], 2_010_000, ITEMS, RATES)
    assert "total" in codes(res)


def test_arithmetic_and_total_errors_are_caught():
    res = audit([line("1", "slab", "m3", 20, 100000, 2_500_000)], 3_000_000, ITEMS, RATES)
    assert {"arithmetic", "total"} <= set(codes(res))


def test_quantity_rate_and_unit_differences_are_flagged_with_what_to_ask():
    res = audit([line("1", "slab", "m3", 30, 150000, 4_500_000), line("2", "render", "m3", 100, 4000, 400_000)], None, ITEMS, RATES)
    c = codes(res)
    assert "quantity" in c and "rate" in c and "unit" in c
    assert all(f["ask"] for f in res["flags"])


def test_small_differences_are_not_flagged_and_double_charging_is():
    res = audit([line("1", "render", "m2", 105, 4100, 430_500), line("2", "render", "m2", 100, 4000, 400_000)], None, ITEMS, RATES)
    assert "quantity" not in codes(res) and "duplicate" in codes(res)


def test_unmatched_lines_are_questions_not_errors():
    res = audit([line("1", "", "item", 1, 50000, 50000)], None, ITEMS, RATES)
    assert [f["severity"] for f in res["flags"] if f["code"] == "not_in_boq"] == ["info"]


def test_numbers_must_be_printed_on_the_page():
    text = "1  Ground slab  m3  20.00  100,000.00  2,000,000.00"
    assert number_printed(2_000_000, text) and number_printed(20, text) and not number_printed(25, text)
    assert unit_of("Sq.m.") == "m2" and unit_of("Nr") == "no"


def test_a_quote_that_was_given_must_be_audited_before_the_boq_is_filed():
    from plan2cost.agent.verify import verify_boq
    from plan2cost.kit.progress import Run

    run = Run.new("a.pdf", "x", quote="q.pdf")
    run.checklist, run.data = [{"id": "C1", "status": "proven"}], {"boq": {}}
    assert any("audit_quote" in p for p in verify_boq(run))
    run.data["audit"] = {}
    assert verify_boq(run) == []
