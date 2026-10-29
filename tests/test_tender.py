from plan2cost.takeoff.bill import numbered, read_xlsx_bid, write_xlsx
from plan2cost.takeoff.tender import audit_bid, compare_bids

ITEMS = [{"key": "slab", "description": "Ground slab", "unit": "m3", "qty": 20.0, "rate": 100000, "besmm": "1.1"},
         {"key": "render", "description": "Render", "unit": "m2", "qty": 100.0, "rate": 4000}]
RATES = {"slab": 100000, "render": 4000}


def test_the_unpriced_bill_has_blank_rates_and_a_formula_the_contractor_can_fill(tmp_path):
    rows = numbered(ITEMS)
    write_xlsx(tmp_path / "u.xlsx", rows, False, "NGN", "Bill", "r1")
    write_xlsx(tmp_path / "p.xlsx", rows, True, "NGN", "Bill", "r1")
    u, p = read_xlsx_bid(str(tmp_path / "u.xlsx")), read_xlsx_bid(str(tmp_path / "p.xlsx"))
    assert u["1"]["rate"] is None and u["1"]["qty"] == 20.0 and p["1"]["rate"] == 100000


def test_a_returned_bill_is_checked_line_by_line_without_guessing():
    rows = numbered(ITEMS)
    bid = {"1": {"description": "Ground slab", "unit": "m3", "qty": 22.0, "rate": 160000, "amount": 3_520_000},
           "3": {"description": "Site clearance", "unit": "item", "qty": 1.0, "rate": 5000, "amount": 5000}}
    a = audit_bid(rows, bid, 3_525_000, RATES)
    assert {"quantity_changed", "rate", "missing_line", "added_item"} <= set(a["counts"])
    assert a["unpriced_items"] == ["2"] and a["total_at_issued_quantities"] == 20 * 160000


def test_a_blank_rate_is_unpriced_and_a_wrong_total_is_an_error():
    rows = numbered(ITEMS)
    bid = {"1": {"description": "x", "unit": "m3", "qty": 20.0, "rate": None, "amount": None},
           "2": {"description": "x", "unit": "m2", "qty": 100.0, "rate": 4000, "amount": 400000}}
    a = audit_bid(rows, bid, 410000, RATES)
    assert a["counts"]["unpriced"] == 1 and a["counts"]["total"] == 1


def test_three_bids_show_a_rate_far_from_the_middle():
    rows = numbered(ITEMS[:1])
    mk = lambda r: {"1": {"description": "", "unit": "m3", "qty": 20.0, "rate": r, "amount": 20 * r}}
    c = compare_bids(rows, {"a": mk(100), "b": mk(105), "c": mk(200)})
    assert [f["code"] for f in c["peer_flags"]["c"]] == ["peer_rate"] and not c["peer_flags"]["a"]
