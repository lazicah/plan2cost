"""Contractor quote audit: the quote's lines against our BoQ. Code does every comparison; the model only read the quote and suggested which BoQ
line each quote line matches. Each flag says in plain words what is different and what to ask the contractor. A flag is a question, not an accusation."""
import re
from dataclasses import dataclass

QTY_TOL = 0.10  # quantity differences under 10% are not flagged: measurement conventions differ
RATE_TOL = 0.15
MATH_TOL = 0.005
UNITS = {"m2": "m2", "m²": "m2", "sqm": "m2", "sq.m": "m2", "sm": "m2", "m3": "m3", "m³": "m3", "cum": "m3", "cu.m": "m3", "m": "m", "lm": "m", "no": "no", "nr": "no",
         "item": "item", "sum": "item", "ls": "item", "t": "t", "tonne": "t", "tonnes": "t", "kg": "kg"}


@dataclass
class QuoteLine:
    no: str
    description: str
    unit: str
    qty: float | None
    rate: float | None
    amount: float | None
    page: int = 1
    key: str = ""  # the BoQ line it was matched to, empty if none


def unit_of(u: str) -> str:
    return UNITS.get(re.sub(r"[\s.]+$", "", str(u).strip().lower()), str(u).strip().lower())


def number_printed(value: float | None, text: str) -> bool:
    """Is the number on the page? Thousands separators and trailing zeros are ignored (1,250.00 matches 1250)."""
    if value is None:
        return True
    digits = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", text)
    forms = {f"{value:.2f}", f"{value:g}", f"{value:.1f}", str(int(value)) if float(value).is_integer() else f"{value:g}"}
    return any(re.search(rf"(?<![\d.]){re.escape(f)}0*(?![\d])", digits) for f in forms)


def flag(code: str, severity: str, line: str, message: str, ask: str, **extra) -> dict:
    return {"code": code, "severity": severity, "line": line, "message": message, "ask": ask, **extra}


def check_arithmetic(lines: list[QuoteLine], stated_total: float | None) -> list[dict]:
    out = []
    for l in lines:
        if l.qty is not None and l.rate is not None and l.amount is not None:
            want = l.qty * l.rate
            if abs(want - l.amount) > MATH_TOL * max(want, 1):
                out.append(flag("arithmetic", "error", l.no, f"Line {l.no}: {l.qty:g} x {l.rate:,.2f} is {want:,.2f}, but the quote shows {l.amount:,.2f}.",
                                 "Ask the contractor to correct this line.", expected=round(want, 2), shown=l.amount))
    shown = sum(l.amount or 0 for l in lines)
    if stated_total is not None and lines and abs(shown - stated_total) > 1:  # amounts are added exactly, so the total should match to the unit
        out.append(flag("total", "error", "total", f"The lines add up to {shown:,.2f} but the quote's total is {stated_total:,.2f}.",
                         "Ask which is right; lines may be missing from this copy or the total may be wrong.", expected=round(shown, 2), shown=stated_total))
    return out


def compare(lines: list[QuoteLine], items: dict, rates: dict) -> list[dict]:
    """`items` is our BoQ by key (description, unit, qty, rate); `rates` the user's own rates."""
    out, seen = [], {}
    for l in lines:
        if not l.key:
            out.append(flag("not_in_boq", "info", l.no, f"Line {l.no} ({l.description[:60]}) matches nothing in our BoQ.",
                             "Ask what it covers; it may be extra work, a different way of describing something we have, or something we left out."))
            continue
        if l.key in seen:
            out.append(flag("duplicate", "warn", l.no, f"Lines {seen[l.key]} and {l.no} both match '{items[l.key]['description'][:50]}'; the work may be charged twice.",
                             "Ask whether these are the same work."))
        seen.setdefault(l.key, l.no)
        it = items[l.key]
        if l.unit and unit_of(l.unit) != unit_of(it["unit"]):
            out.append(flag("unit", "warn", l.no, f"Line {l.no} is in {l.unit} but we measure this in {it['unit']}, so quantities and rates cannot be compared directly.",
                             "Ask for the quantity in our unit or the working."))
            continue
        if l.qty is not None and it["qty"]:
            d = (l.qty - it["qty"]) / it["qty"]
            if abs(d) > QTY_TOL:
                out.append(flag("quantity", "warn", l.no, f"Line {l.no}: the quote has {l.qty:g} {it['unit']}, we measured {it['qty']:g} ({d:+.0%}).",
                                 "Ask how the contractor measured it." if d > 0 else "Ask whether part of the work is left out.", quote=l.qty, ours=it["qty"]))
        mine = rates.get(l.key)
        if l.rate is not None and mine:
            d = (l.rate - mine) / mine
            if abs(d) > RATE_TOL:
                out.append(flag("rate", "warn" if d > 0 else "info", l.no, f"Line {l.no}: the rate is {l.rate:,.2f} per {it['unit']}, against your rate of {mine:,.2f} ({d:+.0%}).",
                                 "Ask what the rate includes (materials, labour, profit)." if d > 0 else "A low rate may mean a lower grade of material or work; ask what is allowed for.",
                                 quote=l.rate, ours=mine))
    return out


def missing(lines: list[QuoteLine], items: dict, rates: dict, show: int = 5) -> list[dict]:
    """Work in our BoQ that no quote line covers: the quote may be cheaper only because it leaves it out. The biggest priced items are listed one by
    one; the rest are rolled up so the list stays readable."""
    got = {l.key for l in lines if l.key}
    left = [(k, it, round(it["qty"] * rates[k], 2) if rates.get(k) else None) for k, it in items.items() if k not in got]
    priced = sorted((x for x in left if x[2]), key=lambda x: -x[2])
    unpriced = [x for x in left if not x[2]]
    out = [flag("missing", "warn", k, f"Nothing in the quote covers: {it['description'][:80]} ({it['qty']:g} {it['unit']}, about {w:,.0f} at your rates).",
                 "Ask whether it is included in another line or left out.", worth=w) for k, it, w in priced[:show]]
    rest = priced[show:]
    if rest:
        out.append(flag("missing", "info", "more", f"{len(rest)} smaller priced items are also not in the quote, together about {sum(x[2] for x in rest):,.0f} at your rates "
                         f"(for example {', '.join(x[1]['description'][:30] for x in rest[:3])}).", "Ask whether they are included in other lines.", worth=sum(x[2] for x in rest)))
    if unpriced:
        out.append(flag("missing", "info", "unpriced", f"{len(unpriced)} items with no rate of yours are not in the quote either (for example "
                         f"{', '.join(x[1]['description'][:30] for x in unpriced[:3])}).", "Add your rate for them to see what they are worth, or ask the contractor."))
    return out


def audit(lines: list[QuoteLine], stated_total: float | None, items: dict, rates: dict) -> dict:
    flags = check_arithmetic(lines, stated_total) + compare(lines, items, rates) + missing(lines, items, rates)
    order = {"error": 0, "warn": 1, "info": 2}
    flags.sort(key=lambda f: order[f["severity"]])
    matched = {l.key for l in lines if l.key}
    ours = round(sum(items[k]["qty"] * rates[k] for k in matched if rates.get(k)), 2)
    quoted = round(sum(l.amount or 0 for l in lines if l.key), 2)
    omitted = round(sum(f.get("worth") or 0 for f in flags if f["code"] == "missing"), 2)
    return {"lines": len(lines), "matched": len(matched), "flags": flags, "quote_total_on_matched_lines": quoted, "our_total_on_matched_lines": ours,
            "our_priced_work_not_in_quote": omitted,
            "counts": {c: sum(f["code"] == c for f in flags) for c in sorted({f["code"] for f in flags})}}
