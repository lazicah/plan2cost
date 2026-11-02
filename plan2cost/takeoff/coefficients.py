"""Rules of thumb for estimating material from a floor plan alone, kept as ranges with their sources (data/coefficients.json). They are for a rough estimate when
there is no detailed drawing: a measured quantity from the drawings always replaces one of these. Every entry has a low, typical and high value, and a rough
estimate shows the spread instead of one number."""
import json
from functools import lru_cache
from pathlib import Path

PATH = Path("data/coefficients.json")
CONFIDENCE = ("high", "medium", "low")


@lru_cache(maxsize=1)
def load() -> dict:
    """The whole coefficient table."""
    return json.loads(PATH.read_text())


def entry(id: str) -> dict:
    """One coefficient by id; an unknown id is an error."""
    for e in load()["entries"]:
        if e["id"] == id:
            return e
    raise KeyError(f"no coefficient {id!r}")


def value(id: str, which: str = "typical") -> float:
    """One number from a coefficient: low, typical or high."""
    return entry(id)[which]


def spread(id: str) -> tuple[float, float, float]:
    """A coefficient's (low, typical, high)."""
    e = entry(id)
    return e["low"], e["typical"], e["high"]


def group(name: str) -> list[dict]:
    """All the coefficients in a group (concrete, roof, frame...)."""
    return [e for e in load()["entries"] if e["group"] == name]


def problems(data: dict | None = None) -> list[str]:
    """Everything wrong with the table: unordered ranges, unknown sources, duplicates, entries with no source."""
    data = data or load()
    out, seen = [], set()
    for e in data["entries"]:
        i = e["id"]
        if i in seen:
            out.append(f"{i}: duplicate id")
        seen.add(i)
        if not e["low"] <= e["typical"] <= e["high"]:
            out.append(f"{i}: low, typical and high are not in order")
        if not e["sources"] or any(s not in data["sources"] for s in e["sources"]):
            out.append(f"{i}: missing or unknown source")
        if e["confidence"] not in CONFIDENCE:
            out.append(f"{i}: confidence must be one of {CONFIDENCE}")
        if e["unit"] == "fraction" and not 0 <= e["low"] <= e["high"] <= 1.5:
            out.append(f"{i}: a fraction outside 0 to 1.5")
        if e["group"] == "benchmark" and "never a rate" not in e.get("note", "") and "sanity" not in e.get("note", ""):
            out.append(f"{i}: a price benchmark must say it is a sanity check and not a rate")
    return out
