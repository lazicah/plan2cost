"""Where each BoQ line sits in the bill. The order is the author's My Duplex bill: substructure, superstructure, internal finishes, services, external works (data/bill_structure.json)."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def structure() -> dict:
    """The bill's structure (data/bill_structure.json): bill numbers and names, groups, and which key goes where."""
    return json.loads(Path("data/bill_structure.json").read_text())


def bill_of(key: str) -> int:
    """The bill number of a line; a line nobody placed goes last, in external works, so it is never lost."""
    s = structure()
    if key in s["keys"]:
        return s["keys"][key]
    return next((n for p, n in s["prefixes"].items() if key.startswith(p)), 16)


def bill_name(n: int) -> str:
    """The name of a bill number (Substructure, Frame...)."""
    return structure()["bills"][str(n)]


def group_of(n: int) -> str:
    """The group (SUBSTRUCTURE, SUPERSTRUCTURE...) a bill number belongs to."""
    return next((g for g, bills in structure()["groups"] if n in bills), "EXTERNAL WORKS")


def order(items: list) -> list:
    """Items in bill order, each keeping its place among the lines of its own bill. Sets `bill` on every item."""
    for i in items:
        i.bill = bill_of(i.key)
    return sorted(items, key=lambda i: i.bill)
