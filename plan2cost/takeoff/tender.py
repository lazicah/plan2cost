"""Audit of bids returned on our unpriced bill. Every contractor prices the same items and quantities, so lines match by item number and nothing is
guessed. Code does all the comparing; a flag is a question for the contractor, not an accusation. Thresholds are defaults, to be set by a surveyor."""
from statistics import median

from plan2cost.takeoff.audit import MATH_TOL, RATE_TOL, flag, unit_of

PEER_TOL = 0.25  # a rate this far from the median of the other bids is worth a question


def audit_bid(issued: list[dict], bid: dict[str, dict], stated_total: float | None, rates: dict) -> dict:
    """`issued` are the numbered bill rows; `bid` the contractor's lines by item number; `rates` the user's own rates by BoQ key."""
    flags, repriced, blanks = [], 0.0, []
    for r in issued:
        b = bid.get(r["no"])
        if b is None:
            blanks.append(r["no"])
            flags.append(flag("missing_line", "warn", r["no"], f"Item {r['no']} ({r['description'][:60]}) is not in the returned bill.", "Ask for it to be priced."))
            continue
        if b["rate"] in (None, 0):
            blanks.append(r["no"])
            flags.append(flag("unpriced", "warn", r["no"], f"Item {r['no']} ({r['description'][:60]}) has no rate.",
                               "Ask for a rate or confirmation that it is included in another item."))
            continue
        repriced += r["qty"] * b["rate"]
        if b["qty"] is not None and abs(b["qty"] - r["qty"]) > 1e-6:
            flags.append(flag("quantity_changed", "warn", r["no"], f"Item {r['no']}: the quantity was changed from {r['qty']:g} to {b['qty']:g} {r['unit']}.",
                               "Bidders price our quantities; ask why it was changed, and price the bid at the issued quantity."))
        if b["unit"] and unit_of(b["unit"]) != unit_of(r["unit"]):
            flags.append(flag("unit_changed", "warn", r["no"], f"Item {r['no']}: unit changed from {r['unit']} to {b['unit']}.", "Ask for the rate per issued unit."))
        if b["qty"] is not None and b["amount"] is not None and abs(b["qty"] * b["rate"] - b["amount"]) > MATH_TOL * max(b["qty"] * b["rate"], 1):
            flags.append(flag("arithmetic", "error", r["no"], f"Item {r['no']}: {b['qty']:g} x {b['rate']:,.2f} is {b['qty'] * b['rate']:,.2f}, but the bill shows {b['amount']:,.2f}.",
                               "Ask the contractor to correct this line."))
        mine = rates.get(r["key"])
        if mine and abs(b["rate"] - mine) / mine > RATE_TOL:
            d = (b["rate"] - mine) / mine
            flags.append(flag("rate", "warn" if d > 0 else "info", r["no"], f"Item {r['no']}: rate {b['rate']:,.2f} against your {mine:,.2f} ({d:+.0%}).",
                               "Ask what the rate includes." if d > 0 else "A low rate can mean lower grade or work left out; ask what is allowed for.", ratio=round(1 + d, 2)))
    known = {r["no"] for r in issued}
    for no in sorted(set(bid) - known, key=lambda x: (len(x), x)):
        flags.append(flag("added_item", "info", no, f"Item {no} ({bid[no]['description'][:60]}) is not in our bill.", "Ask what it covers and why it is added."))
    shown = sum(b["amount"] or 0 for b in bid.values())
    if stated_total is not None and abs(shown - stated_total) > 1:
        flags.append(flag("total", "error", "total", f"The lines add up to {shown:,.2f} but the total shown is {stated_total:,.2f}.", "Ask which is right."))
    order = {"error": 0, "warn": 1, "info": 2}
    flags.sort(key=lambda f: order[f["severity"]])
    return {"total_at_issued_quantities": round(repriced, 2), "unpriced_items": blanks, "flags": flags,
            "counts": {c: sum(f["code"] == c for f in flags) for c in sorted({f["code"] for f in flags})}}


def compare_bids(issued: list[dict], bids: dict[str, dict[str, dict]]) -> dict:
    """Side by side. A bid with unpriced items is shown at the total of what it did price, never ranked as cheapest on that basis."""
    table, peer_flags = [], {name: [] for name in bids}
    for r in issued:
        row = {"no": r["no"], "description": r["description"], "unit": r["unit"], "qty": r["qty"], "rates": {n: (b.get(r["no"]) or {}).get("rate") for n, b in bids.items()}}
        got = {n: v for n, v in row["rates"].items() if v}
        if len(got) >= 3:
            m = median(got.values())
            for n, v in got.items():
                if abs(v - m) / m > PEER_TOL:
                    peer_flags[n].append(flag("peer_rate", "info", r["no"], f"Item {r['no']}: {n}'s rate {v:,.2f} is {(v - m) / m:+.0%} from the middle of the bids ({m:,.2f}).",
                                               "Ask what the rate includes.", ratio=round(v / m, 2)))
        table.append(row)
    return {"items": table, "peer_flags": peer_flags}
