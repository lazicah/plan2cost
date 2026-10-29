"""Coverage of the estimate against the reference list of BoQ items (reference/trades_checklist.json, derived from the author's sample BoQs). The list
stays local: it is read from P2C_TRADES_CHECKLIST or reference/trades_checklist.json. Our own mapping (data/checklist_map.json) holds only item ids
and our BoQ keys. The report says what the estimate covers and what it does not, per trade, so a partial estimate is never mistaken for a full one."""
import json
import os
from pathlib import Path

DEFAULT = "reference/trades_checklist.json"


def path() -> str | None:
    p = os.environ.get("P2C_TRADES_CHECKLIST") or DEFAULT
    return p if Path(p).exists() else None


def load() -> dict | None:
    p = path()
    return json.loads(Path(p).read_text()) if p else None


def building_type(floors: int) -> str:
    return "duplex" if floors >= 2 else "bungalow"


def how_to_get(item: dict) -> str:
    """Where a quantity comes from: read off the drawings, computed from other items, or only the user can say (the item's measured_from)."""
    m = item["measured_from"]
    if m == "derived":
        return "derive from another item with a coefficient the author confirms"
    if "allowance" in m:
        return "not measurable from the drawings: ask the user or state an allowance" + (f" (or read the {m.split('|')[0]})" if "|" in m else "")
    return f"read from the {m.replace('|', ' or ')}"


def coverage(boq_keys: list[str], floors: int = 2, checklist: dict | None = None, mapping: dict | None = None) -> dict | None:
    """For every required item of this building type: covered, partial or not built, with what is missing. None if the checklist is not available."""
    checklist = checklist or load()
    if not checklist:
        return None
    mapping = mapping or json.loads(Path("data/checklist_map.json").read_text())["items"]
    btype = building_type(floors)
    have = set(boq_keys)
    trades: dict = {}
    for t in checklist["trades"]:
        rows = []
        for it in t["items"]:
            if it["required"] and btype in it["applies_to"]:
                m = mapping.get(it["id"])
                present = bool(m) and (any(k in have for k in m.get("keys", [])) or (m.get("prefix") and any(k.startswith(m["prefix"]) for k in have)))
                status = m["status"] if present else "not built"
                rows.append({"id": it["id"], "description": it["description"], "unit": it["unit"], "status": status,
                             "how": how_to_get(it) if status != "covered" else "", "missing": (m or {}).get("missing", "") if status == "partial" else ""})
        if rows:
            trades[t["id"]] = rows
    flat = [r for rows in trades.values() for r in rows]
    n = len(flat)
    count = lambda s: sum(1 for r in flat if r["status"] == s)
    return {"building_type": btype, "required": n, "covered": count("covered"), "partial": count("partial"), "not_built": count("not built"),
            "share_covered": round(count("covered") / n, 2) if n else 0.0, "share_covered_or_partial": round((count("covered") + count("partial")) / n, 2) if n else 0.0,
            "trades": {k: {"covered": sum(r["status"] == "covered" for r in v), "partial": sum(r["status"] == "partial" for r in v),
                           "not_built": sum(r["status"] == "not built" for r in v), "required": len(v)} for k, v in trades.items()},
            "items": flat}


def statement(cov: dict) -> str:
    """One plain sentence for the user: what the estimate covers and which trades it leaves out."""
    left = [k.replace("_", " ") for k, v in cov["trades"].items() if v["covered"] + v["partial"] == 0]
    part = [k.replace("_", " ") for k, v in cov["trades"].items() if 0 < v["covered"] + v["partial"] < v["required"]]
    s = f"This estimate covers {cov['covered']} of {cov['required']} required items fully and {cov['partial']} partly ({cov['building_type']})."
    if left:
        s += f" Not included at all: {', '.join(left)}."
    if part:
        s += f" Only partly included: {', '.join(part)}."
    return s


TRADE_WORDS = {"substructure": ("foundation", "substructure", "excavat", "footing", "hardcore"), "superstructure": ("wall", "block", "column", "beam", "lintel", "slab", "stair"),
               "roofing_ceiling": ("roof", "ceiling", "rafter", "truss"), "finishes": ("finish", "plaster", "paint", "tile", "floor"), "doors_windows": ("door", "window", "opening"),
               "electrical": ("electric", "socket", "light", "wiring"), "plumbing_drainage": ("plumb", "drain", "sanitary", "toilet", "septic", "water"),
               "external_works": ("external works", "fence", "gate", "borehole", "generator")}


def trades_missing(questions: list[str], floors_hint: int = 2, checklist: dict | None = None) -> list[dict]:
    """The trades the agent's checklist does not mention at all, each with how its required items would be got (from a drawing, derived, or by asking).
    A trade left out is not an error: the estimate then says it is not covered. This only makes sure it is a decision, not an oversight."""
    checklist = checklist or load()
    if not checklist:
        return []
    text = " ".join(questions).lower()
    out = []
    btype = building_type(floors_hint)
    for t in checklist["trades"]:
        words = TRADE_WORDS.get(t["id"])
        if not words or any(w in text for w in words):
            continue
        req = [i for i in t["items"] if i["required"] and btype in i["applies_to"]]
        if req:
            out.append({"trade": t["id"], "required_items": len(req), "from": sorted({how_to_get(i) for i in req})})
    return out
