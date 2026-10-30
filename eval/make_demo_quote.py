"""A synthetic contractor's quote made from a run's own bill, with errors planted, for the quote-audit scene of the demo and for testing the audit. It is not a real quote and says so on the page.
python -m eval.make_demo_quote <run id> [out.pdf]   prints what was planted, so the audit can be checked against it."""
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PICK = ["strip_footing_concrete_m3", "ground_slab_m3", "ext_blockwork_230_m2", "int_blockwork_230_m2", "frame_columns_concrete_m3", "frame_beams_concrete_m3", "suspended_slab_concrete_m3",
        "frame_steel_t", "external_wall_render_m2", "internal_wall_finish_m2", "floor_finish_m2", "ceiling_finish_m2", "roof_covering_m2", "roof_timbers_m"]


def plant(items: dict) -> tuple[list[dict], list[str]]:
    """Quote lines from the bill's items, and what was done to them."""
    lines, planted = [], []
    for k in PICK:
        it = items.get(k)
        if not it or not it.get("qty") or not it.get("rate"):
            continue
        q, r = float(it["qty"]), float(it["rate"])
        row = {"description": it["description"][:70], "unit": it["unit"], "qty": q, "rate": r, "amount": round(q * r)}
        if k == "ext_blockwork_230_m2":
            row["rate"] = round(r * 1.25)
            row["amount"] = round(q * row["rate"])
            planted.append(f"rate on {k} is 25% above the user's rate")
        elif k == "ground_slab_m3":
            row["qty"] = round(q * 1.2, 1)
            row["amount"] = round(row["qty"] * r)
            planted.append(f"quantity of {k} is 20% over the plan")
        elif k == "floor_finish_m2":
            row["amount"] = round(q * r * 0.9)
            planted.append(f"the line total of {k} does not equal quantity times rate")
        elif k == "roof_covering_m2":
            planted.append(f"{k} (roof covering) is left out of the quote")
            continue
        lines.append(row)
        if k == "int_blockwork_230_m2":
            lines.append({**row, "description": "Sandcrete blockwork internal partitions, as above (second item)"})  # the same work again
            planted.append(f"{k} is charged twice")
    return lines, planted


def write_pdf(lines: list[dict], total: int, path: str, currency: str = "NGN") -> None:
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, h - 50, "QUOTATION: two-storey residential building")
    c.setFont("Helvetica", 8)
    c.drawString(40, h - 64, "Synthetic quote made for a demonstration. Not a real contractor and not a real price.")
    y = h - 100
    c.setFont("Helvetica-Bold", 8)
    for x, t in ((40, "No"), (65, "Description"), (350, "Unit"), (390, "Qty"), (440, "Rate"), (495, "Amount")):
        c.drawString(x, y, t)
    c.setFont("Helvetica", 8)
    for i, ln in enumerate(lines, 1):
        y -= 18
        c.drawString(40, y, str(i))
        c.drawString(65, y, ln["description"])
        c.drawString(350, y, ln["unit"])
        c.drawRightString(425, y, f"{ln['qty']:,.1f}")
        c.drawRightString(485, y, f"{ln['rate']:,.0f}")
        c.drawRightString(560, y, f"{ln['amount']:,.0f}")
    y -= 28
    c.setFont("Helvetica-Bold", 9)
    c.drawString(65, y, f"TOTAL ({currency})")
    c.drawRightString(560, y, f"{total:,.0f}")
    c.save()


if __name__ == "__main__":
    run = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else f"workspace/demo_quote_{run}.pdf"
    boq = json.loads(Path(f"workspace/runs/{run}/run.json").read_text())["data"]["boq"]
    lines, planted = plant({i["key"]: i for i in boq["items"]})
    total = round(sum(l["amount"] for l in lines) * 1.0) + 150000  # a total that is 150,000 more than the lines add up to
    planted.append("the printed total is 150,000 more than the lines add up to")
    write_pdf(lines, total, out)
    print(out, "\n".join(["planted:"] + [f"- {p}" for p in planted]), sep="\n")
