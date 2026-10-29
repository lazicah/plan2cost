"""Draw what the raster route finds: python -m eval.draw_raster_walls <plan> <px> <kind> <out.jpg>  (block size taken as 225 at that ruler)."""
import sys

import cv2

from plan2cost.drawing.interpret import bin_width
from plan2cost.drawing.raster_lines import vectorise_multi
from plan2cost.drawing.vector_walls import find_walls_vector

if __name__ == "__main__":
    n, px, kind, out = int(sys.argv[1]), float(sys.argv[2]), sys.argv[3], sys.argv[4]
    block = float(sys.argv[5]) if len(sys.argv) > 5 else 225.0
    img = cv2.imread(f"reference/plan{n}/ground-floor.jpg")
    lines = vectorise_multi(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    for l in lines:
        l.raw, l.w = l.w, bin_width(l.w)
    s = block / px
    walls, info = find_walls_vector(lines, s, primitive=kind, min_length_m=25, min_joints=4)
    for w in walls:
        c, a, b = w.centre_mm / s, w.start_mm / s, w.end_mm / s
        p1, p2 = ((int(a), int(c)), (int(b), int(c))) if w.orient == "h" else ((int(c), int(a)), (int(c), int(b)))
        cv2.line(img, p1, p2, (0, 0, 255), 7)
    cv2.imwrite(out, cv2.resize(img, (img.shape[1] // 3, img.shape[0] // 3)))
    print(len(walls), round(sum(w.length_mm for w in walls) / 1000, 1))
