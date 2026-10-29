"""What the model reads off a plan image that code cannot get without a text layer: the stated scale and the overall printed dimensions.
The numbers are only used as checks against what code measures (a misread value disagrees with the measured extent), never as lengths."""
import tempfile

import cv2

from plan2cost.client import image_part

PROMPT = """This is an architectural floor plan. Read ONLY what is printed on it:
1. The drawing scale written in the title block (for example "1:100"), as the number after the colon, or null if you cannot read one.
2. The OVERALL dimension of the building along its horizontal direction and along its vertical direction: the longest dimension strings that span
   the whole building on each axis, in millimetres. Give every overall string you can read on each axis (there are often two or three: outer to outer,
   grid to grid). Do not give room dimensions.
Return only JSON: {"scale": 100 or null, "horizontal_mm": [numbers], "vertical_mm": [numbers]}"""


def read_page_facts(image_path: str, max_side: int = 2600) -> dict:
    from plan2cost.document import _chat

    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    k = max_side / max(h, w)
    if k < 1:
        img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    path = tempfile.mkstemp(suffix=".jpg")[1]
    cv2.imwrite(path, img)
    return _chat([{"type": "text", "text": PROMPT}, image_part(path)])
