"""The bill as a document. A priced bill goes to a client (rates include the contractor's overhead, profit and other costs); an unpriced bill
(quantities only) goes out for tender and the contractor fills in the rates. Preliminaries, overhead and profit live inside the rates, so the
bill has no separate section for them. Items are numbered so a returned bill can be matched line by line without guessing."""
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font

HEAD = ("No", "BESMM4", "Description", "Unit", "Qty", "Rate", "Amount")
NOTE = ("Price every item. Rates must include overhead, profit, preliminaries and all other costs: there is no separate item for them. "
        "Do not change quantities or descriptions; qualify in a covering letter instead.")


def numbered(items: list[dict]) -> list[dict]:
    """The BoQ lines with a stable item number (their order in the bill)."""
    return [{"no": str(n), "besmm": i.get("besmm", ""), "description": i["description"], "unit": i["unit"], "qty": i["qty"], "rate": i.get("rate"), "key": i["key"]}
            for n, i in enumerate(items, 1)]


def write_xlsx(path: str | Path, rows: list[dict], priced: bool, currency: str, title: str, run_id: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Bill"
    ws["A1"], ws["A1"].font = f"{title} ({'priced' if priced else 'unpriced, for tender'}; {currency})", Font(bold=True, size=13)
    ws["A2"] = NOTE
    ws.append([])
    ws.append(list(HEAD))
    for c in ws[4]:
        c.font = Font(bold=True)
    first = ws.max_row + 1
    for r in rows:
        n = ws.max_row + 1
        has_rate = priced and r["rate"]
        ws.append([int(r["no"]), r["besmm"], r["description"], r["unit"], r["qty"], r["rate"] if has_rate else None, f"=E{n}*F{n}"])
        ws[f"C{n}"].alignment = Alignment(wrap_text=True, vertical="top")
    last = ws.max_row
    ws.append(["", "", "Total", "", "", "", f"=SUM(G{first}:G{last})"])
    ws[f"C{ws.max_row}"].font = ws[f"G{ws.max_row}"].font = Font(bold=True)
    for col, w in zip("ABCDEFG", (6, 16, 80, 7, 11, 14, 16)):
        ws.column_dimensions[col].width = w
    for r in range(first, ws.max_row + 1):
        for col in "FG":
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
