"""The model reads a contractor's quote and suggests which of our BoQ lines each quote line matches. Both are only readings: every number must be
printed on the quote page (when it has a text layer) and every suggested match must be a real BoQ key; the comparison is code (takeoff/audit.py)."""

from plan2cost.kit.client import chat_json, image_part
from plan2cost.kit.pdf import page_count, page_text, render_pages
from plan2cost.takeoff.audit import QuoteLine, number_printed

READ_PROMPT = """You are reading a contractor's quote for a building project, for a quantity surveyor. Extract every priced line exactly as printed.
Rules:
- One entry per line of the quote that has a description. Copy the description, unit, quantity, rate and amount as printed; use null for anything not printed.
- Never calculate, correct or fill in a number. If a number is unreadable use null.
- "no" is the item number printed on the quote (or the row number if none).
- "total" is the grand total if one is printed, else null.
Reply with JSON only: {"lines": [{"no": str, "description": str, "unit": str|null, "qty": number|null, "rate": number|null, "amount": number|null, "page": int}], "total": number|null, "currency": str|null}"""

MATCH_PROMPT = """You match contractor quote lines to the lines of our Bill of Quantities. For each quote line give the key of the BoQ line it is the same work as, or null
if none is. Match on the work described (material, grade, thickness, what it is for), not on price. When a quote line bundles several BoQ lines choose the main
one. Reply with JSON only: {"matches": [{"no": str, "key": str|null}]}.
BoQ lines:
"""


def read_quote(path: str, scratch: str) -> dict:
    """Lines and total from a quote (PDF or image). Numbers not printed on the page are dropped from the line and reported in `unverified`."""
    pdf = path.lower().endswith(".pdf")
    pages = list(range(1, page_count(path) + 1)) if pdf else [1]
    images = render_pages(path, pages, scratch, dpi=150) if pdf else [path]
    text = {n: page_text(path, n) for n in pages} if pdf else {}
    hint = "\n".join(f"--- text on page {n} ---\n{t[:3000]}" for n, t in text.items() if t.strip())
    data = chat_json([{"type": "text", "text": f"{READ_PROMPT}\n{hint}"}, *[image_part(p) for p in images]])
    lines, unverified = [], []
    for i, r in enumerate(data.get("lines", []), 1):
        page = int(r.get("page") or 1)
        t = text.get(page, "")
        for f in ("qty", "rate", "amount"):
            if r.get(f) is not None and t.strip() and not number_printed(float(r[f]), t):
                unverified.append(f"line {r.get('no') or i}: {f} {r[f]} is not printed on page {page}")
                r[f] = None
        lines.append(QuoteLine(str(r.get("no") or i), str(r.get("description", "")), str(r.get("unit") or ""), r.get("qty"), r.get("rate"), r.get("amount"), page))
    total = data.get("total")
    if total is not None and text and not any(number_printed(float(total), t) for t in text.values()):
        unverified.append(f"total {total} is not printed on the quote")
        total = None
    return {"lines": lines, "total": total, "currency": data.get("currency"), "unverified": unverified}


def match_lines(lines: list[QuoteLine], items: dict) -> None:
    """Fill `key` on each line from the model's suggestion; anything that is not a real BoQ key is ignored."""
    listing = "\n".join(f"- {k}: {v['description']} [{v['unit']}]" for k, v in items.items())
    listed = "\n".join(f"{l.no}: {l.description} [{l.unit}]" for l in lines)
    got = chat_json([{"type": "text", "text": f"{MATCH_PROMPT}{listing}\n\nQuote lines:\n{listed}"}])
    by_no = {str(m.get("no")): m.get("key") for m in got.get("matches", [])}
    for l in lines:
        k = by_no.get(l.no)
        l.key = k if k in items else ""
