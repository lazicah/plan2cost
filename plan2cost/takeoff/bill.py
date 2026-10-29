"""The bill as a document. A priced bill goes to a client (rates include the contractor's overhead, profit and other costs); an unpriced bill
(quantities only) goes out for tender and the contractor fills in the rates. Preliminaries, overhead and profit live inside the rates, so the
bill has no separate section for them. Items are numbered so a returned bill can be matched line by line without guessing."""
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font

HEAD = ("No", "BESMM4", "Description", "Unit", "Qty", "Rate", "Amount")
NOTE = ("Price every item. Rates must include overhead, profit, preliminaries and all other costs: there is no separate item for them. "
        "Do not change quantities or descriptions; qualify in a covering letter instead.")


BUDGET_NOTE = ("Budget estimate from floor plans. Lines marked 'measured' come from the plans; lines marked 'estimated' come from coefficients and show a low to high range. "
               "Not a bill for tender: quantities must be measured from full drawings first.")


def numbered(items: list[dict]) -> list[dict]:
    """The BoQ lines with a stable item number (their order in the bill)."""
    return [{"no": str(n), "besmm": i.get("besmm", ""), "description": i["description"], "unit": i["unit"], "qty": i["qty"], "rate": i.get("rate"), "key": i["key"],
             "basis": i.get("basis", "measured"), "qty_low": i.get("qty_low"), "qty_high": i.get("qty_high")} for n, i in enumerate(items, 1)]


def ranged(rows: list[dict]) -> bool:
    """A bill with estimated lines carries their range; it is a budget estimate, not a bill to send out for tender."""
    return any(r.get("basis") == "estimated" for r in rows)


def write_xlsx(path: str | Path, rows: list[dict], priced: bool, currency: str, title: str, run_id: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Bill"
    ws["A1"], ws["A1"].font = f"{title} ({'priced' if priced else 'unpriced, for tender'}; {currency})", Font(bold=True, size=13)
    ws["A2"] = BUDGET_NOTE if priced and ranged(rows) else NOTE
    ws.append([])
    extra = ("Basis", "Qty low", "Qty high", "Amount low", "Amount high") if priced and ranged(rows) else ()
    ws.append(list(HEAD) + list(extra))
    for c in ws[4]:
        c.font = Font(bold=True)
    first = ws.max_row + 1
    for r in rows:
        n = ws.max_row + 1
        has_rate = priced and r["rate"]
        row = [int(r["no"]), r["besmm"], r["description"], r["unit"], r["qty"], r["rate"] if has_rate else None, f"=E{n}*F{n}"]
        if extra:
            lo, hi = (r["qty_low"] if r.get("qty_low") is not None else r["qty"]), (r["qty_high"] if r.get("qty_high") is not None else r["qty"])
            row += [r.get("basis", "measured"), lo, hi, f"=I{n}*F{n}", f"=J{n}*F{n}"]
        ws.append(row)
        ws[f"C{n}"].alignment = Alignment(wrap_text=True, vertical="top")
    last = ws.max_row
    ws.append(["", "", "Total", "", "", "", f"=SUM(G{first}:G{last})"] + (["", "", "", f"=SUM(K{first}:K{last})", f"=SUM(L{first}:L{last})"] if extra else []))
    ws[f"C{ws.max_row}"].font = ws[f"G{ws.max_row}"].font = Font(bold=True)
    for col, w in zip("ABCDEFGHIJKL", (6, 16, 80, 7, 11, 14, 16, 11, 11, 11, 16, 16)):
        ws.column_dimensions[col].width = w
    for r in range(first, ws.max_row + 1):
        for col in "FGKL" if extra else "FG":
            ws[f"{col}{r}"].number_format = "#,##0.00"
    info = wb.create_sheet("Info")
    info.append(["run", run_id])
    info.append(["currency", currency])
    wb.save(path)


def read_xlsx_bid(path: str) -> dict[str, dict]:
    """A returned bill, by item number. Values are read as the contractor left them; nothing is corrected."""
    ws = load_workbook(path, data_only=True)["Bill"] if "Bill" in load_workbook(path, read_only=True).sheetnames else load_workbook(path, data_only=True).active
    head = next((i for i, row in enumerate(ws.iter_rows(values_only=True), 1) if row and row[0] == "No"), None)
    out: dict[str, dict] = {}
    if not head:
        return out
    for row in ws.iter_rows(min_row=head + 1, values_only=True):
        if not isinstance(row[0], (int, float)):
            continue
        qty, rate, amount = (float(v) if isinstance(v, (int, float)) else None for v in (row[4], row[5], row[6]))
        out[str(int(row[0]))] = {"description": str(row[2] or ""), "unit": str(row[3] or ""), "qty": qty, "rate": rate, "amount": amount}
    return out


def write_pdf(path: str | Path, rows: list[dict], priced: bool, currency: str, title: str, run_id: str) -> None:
    """The same bill as a PDF for reading and printing. The unpriced PDF has empty rate and amount columns."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    cell = st["BodyText"].clone("cell", fontSize=8, leading=10)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28, title=title)
    rng = priced and ranged(rows)
    data = [list(HEAD) + (["Basis", "Qty low to high"] if rng else [])]
    total = 0.0
    for r in rows:
        amount = r["qty"] * r["rate"] if priced and r["rate"] else None
        total += amount or 0
        data.append([r["no"], r["besmm"], Paragraph(r["description"].replace("&", "&amp;").replace("<", "&lt;"), cell), r["unit"], f"{r['qty']:,.2f}",
                     f"{r['rate']:,.2f}" if priced and r["rate"] else "", f"{amount:,.2f}" if amount else ""]
                    + ([r.get("basis", "measured"), f"{r['qty_low']:,.1f} to {r['qty_high']:,.1f}" if r.get("qty_low") is not None else ""] if rng else []))
    data.append(["", "", Paragraph("<b>Total</b>", cell), "", "", "", f"{total:,.2f}" if priced else ""] + (["", ""] if rng else []))
    table = Table(data, colWidths=[28, 62, 330, 34, 56, 64, 80] + ([52, 80] if rng else []), repeatRows=1)
    table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efece4")),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b9b5aa")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (4, 0), (6, -1), "RIGHT")]))
    doc.build([Paragraph(f"<b>{title}</b> ({'priced' if priced else 'unpriced, for tender'}; {currency})", st["Title"]), Paragraph(BUDGET_NOTE if rng else NOTE, cell), Spacer(1, 8), table])
