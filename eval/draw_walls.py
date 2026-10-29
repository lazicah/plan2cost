"""Draw the measured walls over a plan page to check them by eye: python eval/draw_walls.py <pdf> <page> <out.jpg> (red external, blue internal)."""
import sys

import cv2

from plan2cost.drawing.measure import vector_scale
from plan2cost.kit.pdf import render_pages
from plan2cost.drawing.vector import read_page
from plan2cost.drawing.vector_walls import axis_lines, find_walls_vector
from plan2cost.drawing.walls_cv import external_fractions

if __name__ == "__main__":
    pdf, page, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    pg = read_page(pdf, page)
    lines = axis_lines(pg.segs)
    mm, basis = vector_scale(pdf, page, pg, lines)
    walls, info = find_walls_vector(lines, mm)
    px = 50.0
    fr = external_fractions(walls, (int(pg.height * mm / px) + 2, int(pg.width * mm / px) + 2), px)
    dpi = 100
    k = dpi / 72
    img = cv2.imread(render_pages(pdf, [page], "/tmp/draw_walls", dpi=dpi)[0])
    for w, f in zip(walls, fr):
        cp, a, b = w.centre_mm / mm * k, w.start_mm / mm * k, w.end_mm / mm * k
        p1, p2 = ((int(a), int(cp)), (int(b), int(cp))) if w.orient == "h" else ((int(cp), int(a)), (int(cp), int(b)))
        cv2.line(img, p1, p2, (0, 0, 255) if f >= 0.5 else (255, 0, 0), 4)
    cv2.imwrite(out, img)
    print(info.get("wall_weight"), len(walls), round(sum(w.length_mm for w in walls) / 1000, 1))
