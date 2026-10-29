"""The BESMM4 master bill: every item that can be measured, with its code, wording and unit. It is the NIQS's text, so it is not in the repo;
point P2C_BESMM_XLSX at your copy (default reference/rules/Detailed BOQ Description BESMM4.xlsx). Not every item applies to every project:
the agent picks the relevant ones and asks the user when an item is conditional."""
import os
import re
from functools import lru_cache
from pathlib import Path

DEFAULT = "reference/rules/Detailed BOQ Description BESMM4.xlsx"
STOP = {"the", "of", "and", "to", "a", "in", "for", "on", "with", "from", "by"}


def path() -> str | None:
    p = os.environ.get("P2C_BESMM_XLSX") or DEFAULT
    return p if Path(p).exists() else None


@lru_cache(maxsize=1)
def items() -> list[dict]:
    """Measurable items only (a code, a wording and a unit); preambles, headings and information lines are left out."""
    import openpyxl

    p = path()
    if not p:
        return []
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    out, heading = [], {}  # heading rows (no unit) give the leaves below them their context, e.g. "Finish to Walls" over "> 600mm wide."
    for r in wb.worksheets[0].iter_rows(values_only=True):
        code, desc, unit = (str(r[0]).strip() if r[0] else ""), re.sub(r"\s+", " ", str(r[1] or "")).strip(), str(r[3] or "").strip()
        if not (code and desc and re.fullmatch(r"\d+(\.\d+)+", code)):
            continue
        if not unit:
            heading[code] = desc
        elif unit.lower() not in ("unit", "item"):
            parent = heading.get(code.rsplit(".", 1)[0])
            out.append({"code": code, "description": f"{parent}; {desc}" if parent and parent != desc else desc, "unit": unit})
    return out


def find(query: str, top: int = 8) -> list[dict]:
    """Items whose code or wording carries every word of the query, best match first."""
    terms = [t for t in re.findall(r"[a-z0-9.]+", query.lower()) if t not in STOP]
    scored = []
    for it in items():
        text = f"{it['code']} {it['description']}".lower()
        if terms and all(t in text for t in terms):
            scored.append((sum(text.count(t) for t in terms) - len(text) / 500, it))
    return [it for _, it in sorted(scored, key=lambda s: -s[0])[:top]]


def get(code: str) -> dict | None:
    return next((it for it in items() if it["code"] == code), None)
