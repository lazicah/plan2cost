"""Vector content of a PDF page: straight segments with their stroke weight, in page points. This is the exact route for CAD plans exported
as vectors (no pixels, no thresholds). The page is read through pdftocairo's SVG, which applies the page rotation and every transform."""
import re
import subprocess
from dataclasses import dataclass

from plan2cost.kit.pdf import pdftoppm


@dataclass
class Seg:
    """A straight stroke from a PDF page, in points: its ends, its stroke width (0 for the edge of a filled shape), and whether it is dashed or came from a filled shape."""
    x0: float
    y0: float
    x1: float
    y1: float
    w: float  # stroke width in points; 0 for the edge of a filled shape
    dashed: bool = False
    filled: bool = False

    @property
    def length(self) -> float:
        return ((self.x1 - self.x0) ** 2 + (self.y1 - self.y0) ** 2) ** 0.5


@dataclass
class Page:
    """A PDF page's size in points and its straight segments; curves (door swings, round fixtures) are only counted."""
    width: float
    height: float
    segs: list[Seg]
    curves: int = 0  # arcs and curves (door swings, round fixtures), not measured here


def read_page(pdf: str, page: int) -> Page:
    """Read the vector line work of a PDF page (through pdftocairo's SVG output) into straight segments with their stroke widths."""
    exe = pdftoppm().replace("pdftoppm", "pdftocairo")
    svg = subprocess.run([exe, "-svg", "-f", str(page), "-l", str(page), pdf, "-"], capture_output=True, text=True).stdout
    size = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    segs, curves = [], 0
    for m in re.finditer(r"<path ([^>]*?)/>", svg):
        attrs = m.group(1)
        d = re.search(r' d="([^"]*)"', attrs)
        if not d or "glyph" in attrs:
            continue
        path = d.group(1)
        if re.search(r"[CcSsQqAa]", path):
            curves += 1
            continue
        t = re.search(r'transform="matrix\(([^)]*)\)"', attrs)
        a, b, c, dd, e, f = ([float(x) for x in t.group(1).split(",")] if t else [1, 0, 0, 1, 0, 0])
        w = re.search(r'stroke-width="([\d.]+)"', attrs)
        stroked = 'stroke="rgb' in attrs and 'stroke="none"' not in attrs
        filled = 'fill="none"' not in attrs and "fill=" in attrs
        if not stroked and not filled:
            continue
        for sub in re.split(r"(?=M )", path):
            nums = [float(x) for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", sub)]
            pts = [(a * nums[i] + c * nums[i + 1] + e, b * nums[i] + dd * nums[i + 1] + f) for i in range(0, len(nums) - 1, 2)]
            if len(pts) < 2:
                continue
            if "Z" in sub and pts[0] != pts[-1]:
                pts.append(pts[0])
            for p, q in zip(pts, pts[1:]):
                if p != q:
                    segs.append(Seg(p[0], p[1], q[0], q[1], float(w.group(1)) * abs(a) if (w and stroked) else 0.0, "dasharray" in attrs, filled and not stroked))
    return Page(float(size.group(1)), float(size.group(2)), segs, curves)
