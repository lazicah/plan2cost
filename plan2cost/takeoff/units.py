"""Rounding rules from BESMM4."""
from decimal import ROUND_HALF_UP, Decimal


def to_10mm(x: float) -> float:
    """BESMM4 1.5.2: dimensions to the nearest 10mm (5mm and over rounds up)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
