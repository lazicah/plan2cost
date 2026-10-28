import numpy as np

from plan2cost.walls_cv import find_walls, girth_by_thickness


def drawing():
    """A 4 m x 3 m room with 230mm walls at 20 mm per pixel, faces as 1px lines, and a 1 m door gap in the bottom wall."""
    img = np.full((300, 400), 255, np.uint8)
    t = 12  # 230mm at 20mm/px
    for y in (50, 50 + t, 200, 200 + t):  # top and bottom wall faces
        img[y, 40:240] = 0
    img[200, 120:170] = 255  # opening in the bottom wall's upper face...
    img[200 + t, 120:170] = 255  # ...and its lower face
    for x in (40, 40 + t, 228, 228 + t):  # left and right wall faces
        img[50:212, x] = 0
    img[100, 10:390] = 0  # a long dimension line with no partner: must not become a wall
    return img


def test_walls_are_paired_faces_merged_across_the_door_and_dimension_lines_ignored():
    walls = find_walls(drawing(), mm_per_px=20.0, region_px=(0, 0, 400, 300), min_run_mm=800)
    horiz = [w for w in walls if w.orient == "h"]
    assert len(walls) == 4 and all(abs(w.thickness_mm - 240) < 40 for w in walls)
    bottom = max(horiz, key=lambda w: w.centre_mm)
    assert abs(bottom.length_mm - 4000) < 60  # full run: the door gap is bridged
    g = girth_by_thickness(walls)
    assert list(g) == [230] and abs(g[230] - (2 * 4.0 + 2 * 3.24)) < 0.3
