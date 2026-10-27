import json
from pathlib import Path


def load_rates(path: str = "data/rates.json") -> dict:
    return json.loads(Path(path).read_text())


def price(quantities: dict, rates: dict) -> dict:
    lines = {k: round(v * rates["rates"].get(k, 0), 2) for k, v in quantities.items()}
    return {"currency": rates["currency"], "lines": lines, "total": round(sum(lines.values()), 2)}
