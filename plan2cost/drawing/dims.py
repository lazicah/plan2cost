"""Printed dimensions from a PDF's text layer, with positions. A deterministic candidate finder: the model then decides, from a
crop around each candidate, whether it is a window, a door or just a wall segment. Raster drawings have no text layer; they
fall back to the model reading the plan tiles."""
import re
import subprocess
from dataclasses import dataclass

from plan2cost.kit.pdf import pdftoppm


@dataclass
class DimToken:
    value: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def vertical(self) -> bool:
        """Rotated text (taller than wide) belongs to a vertical dimension chain."""
        return (self.y1 - self.y0) > (self.x1 - self.x0)

    @property
    def along(self) -> float:
        """Position along the wall the dimension runs beside: y for vertical chains, x for horizontal ones."""
        return (self.y0 + self.y1) / 2 if self.vertical else (self.x0 + self.x1) / 2

    @property
    def across(self) -> float:
        return (self.x0 + self.x1) / 2 if self.vertical else (self.y0 + self.y1) / 2


def dimension_tokens(pdf: str, page: int) -> list[DimToken]:
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    html = subprocess.run([exe, "-f", str(page), "-l", str(page), "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    return [DimToken(int(w), float(a), float(b), float(c), float(d))
            for a, b, c, d, w in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(\d{3,5})<', html)]


def chains(tokens: list[DimToken], min_tokens: int = 4, tolerance_pts: float = 3.0) -> list[list[DimToken]]:
    """A dimension chain is a row (or column) of numbers sharing one line. Rotated text forms vertical chains."""
    out = []
    for vertical in (False, True):
        group = sorted((t for t in tokens if t.vertical == vertical), key=lambda t: t.across)
        cur: list[DimToken] = []
        for t in group:
            if cur and t.across - cur[-1].across > tolerance_pts:
                if len(cur) >= min_tokens:
                    out.append(cur)
                cur = []
            cur.append(t)
        if len(cur) >= min_tokens:
            out.append(cur)
    return out
