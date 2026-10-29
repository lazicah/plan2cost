from openpyxl import load_workbook

from plan2cost.takeoff import ml_bill
from plan2cost.takeoff.boq import price_boq
from plan2cost.takeoff.materials import bill_of_materials, table
from tests.test_rough import RATES
from tests.test_sections import items


def item(key, qty, unit="m3", rate=None, low=None, high=None, basis="measured"):
    return {"key": key, "description": key, "unit": unit, "qty": qty, "rate": rate, "qty_low": low, "qty_high": high, "basis": basis}


def lines(bm, name):
    return {ln["description"].split(" – ")[0]: ln for sec in bm["sections"] for s in sec["subs"] if s["name"] == name for ln in s["lines"]}


def test_concrete_gets_cement_sand_granite_and_casting_labour_from_the_authors_ratios():
    t = table()["ratios"]["concrete"]
    ln = lines(bill_of_materials([item("ground_slab_m3", 30)]), "Ground floor slab concrete")
    assert ln["Cement, 50 kg bag"]["qty"] == round(30 * t["cement_bag"] + 0.4999) and ln["Cement, 50 kg bag"]["unit"] == "bag" and ln["Cement, 50 kg bag"]["rate"] == 12500
    assert 6.0 <= t["cement_bag"] <= 7.2  # the author's bills: 5.9 to 7.2 bags per m3
    assert "Labour" in " ".join(d for d in ln) and ln["Granite"]["rate"] == 30000


def test_steel_is_counted_in_twelve_metre_lengths_with_bending_labour_on_the_weight():
    ln = lines(bill_of_materials([item("frame_steel_t", 2.0, "t")]), "Reinforcement (columns, beams, slabs and stairs)")
    assert 140 <= ln["Reinforcement bar, 12 m length (mixed sizes)"]["qty"] <= 156  # about 74 lengths a tonne
    labour = next(v for k, v in ln.items() if k.startswith("Labour"))
    assert labour["qty"] == 2000 and labour["rate"] == 100  # 2000 kg at 100 a kg


def test_an_estimated_line_keeps_its_range_through_the_recipe():
    ln = lines(bill_of_materials([item("frame_beams_concrete_m3", 20, low=10, high=36, basis="estimated")]), "Beams concrete")
    c = ln["Cement, 50 kg bag"]
    assert c["qty_low"] < c["qty"] < c["qty_high"] and c["basis"] == "estimated" and c["amount_low"] < c["amount"] < c["amount_high"]


def test_foundation_block_laying_costs_more_than_wall_block_laying():
    a = lines(bill_of_materials([item("fdn_blockwork_230_m2", 100, "m2")]), "Blockwork in foundation")
    b = lines(bill_of_materials([item("ext_blockwork_230_m2", 100, "m2")]), "Blockwork in external walls")
    assert next(v for k, v in a.items() if k.startswith("Labour"))["rate"] == 200 and next(v for k, v in b.items() if k.startswith("Labour"))["rate"] == 45


def test_a_line_with_no_recipe_is_carried_at_its_boq_rate_and_totals_add_up():
    bm = bill_of_materials([item("opening_w1200_nr", 4, "nr", rate=69000), item("ground_slab_m3", 10)])
    carried = [c for s in bm["sections"] for c in s["carried"]]
    assert len(carried) == 1 and carried[0]["amount"] == 276000
    parts = sum(s["amount"] for sec in bm["sections"] for s in sec["subs"]) + 276000
    assert abs(bm["total"] - parts) < 1 and bm["total_low"] <= bm["total"] <= bm["total_high"]


def test_a_whole_estimate_makes_a_bill_of_materials_in_bill_order_and_writes_both_files(tmp_path):
    its = items()
    price_boq(its, RATES)
    bm = bill_of_materials([i.__dict__ for i in its])
    assert [s["bill"] for s in bm["sections"]] == sorted(s["bill"] for s in bm["sections"]) and bm["sections"][0]["name"] == "Substructure"
    assert any(s["bill"] == 14 and s["carried"] for s in bm["sections"])  # sanitary fittings are carried at their rate
    ml_bill.write_xlsx(tmp_path / "m.xlsx", bm, "NGN", "Bill of materials and labour", "r1")
    ml_bill.write_pdf(tmp_path / "m.pdf", bm, "NGN", "Bill of materials and labour", "r1")
    wb = load_workbook(tmp_path / "m.xlsx")
    labels = [r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[1]]
    assert labels[1].startswith("02 Substructure") and labels[-1] == "Total" and (tmp_path / "m.pdf").read_bytes().startswith(b"%PDF")
    col = [r[0] for r in wb["Materials and labour"].iter_rows(min_row=5, values_only=True) if isinstance(r[0], str)]
    assert col[0] == "SUBSTRUCTURE" and col.index("SERVICES") > col.index("INTERNAL FINISHES")
