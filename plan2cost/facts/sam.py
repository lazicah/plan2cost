"""SAM 3.1 through the Meta Model API: a concept phrase, or points and boxes on objects we already located, in; boxes and pixel masks out.

The mask is the pixel region to measure, so lengths and areas come from the mask and the drawing's scale, not from the model's words.
Output is the documented special-token text; masks are decoded with Meta's own parser package (meta-sam-parser)."""
import base64
import re
from dataclasses import dataclass

import numpy as np
from meta_sam_parser import SegmentationMask, build_object_prompt, decode_mask_to_raster
from meta_sam_parser import FramePrompt, PromptObject, PromptPoint

from plan2cost.kit.client import get_client

RECORD = re.compile(r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|><\|mask;x=0;y=0;data=(\d+),(\d+),(.)([^|]*)\|>")
ENCODINGS = {"~": "lossless", "!": "one_bit"}


@dataclass
class Segment:
    """One object SAM found: its id, its box in source pixels, and its pixel mask."""
    object_id: int
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 (inclusive) in source pixels
    mask: np.ndarray  # bool, source-sized (frame w x h)

    @property
    def area_px(self) -> int:
        return int(self.mask.sum())


def parse(text: str) -> list[Segment]:
    """Decode SAM's special-token text reply into segments with full-size masks."""
    segs = []
    for oid, x1, y1, x2, y2, w, h, mh, mw, enc, payload in RECORD.findall(text):
        raster = decode_mask_to_raster(SegmentationMask(ENCODINGS[enc], enc + payload, int(mw), int(mh)))
        small = (np.frombuffer(raster, dtype=np.uint8).reshape(int(mh), int(mw)) > 0)
        full = np.zeros((int(h), int(w)), bool)
        full[int(y1):int(y1) + int(mh), int(x1):int(x1) + int(mw)] = small  # the mask raster covers the box region
        segs.append(Segment(int(oid), (int(x1), int(y1), int(x2), int(y2)), full))
    return segs


def _call(prompt_text: str, image_path: str) -> str:
    b64 = base64.b64encode(open(image_path, "rb").read()).decode()
    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    r = get_client().responses.create(model="sam-3.1", input=[{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": prompt_text}, {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}]}])
    return r.output_text


def segment_concept(image_path: str, phrase: str) -> list[Segment]:
    """Every instance of a noun phrase. Zero matches is a normal answer."""
    return parse(_call(phrase, image_path))


def segment_points(image_path: str, size: tuple[int, int], points: dict[int, tuple[int, int]]) -> list[Segment]:
    """One object per id, each marked by a positive point inside it (pixel coordinates of the image as sent)."""
    objects = [PromptObject(id=i, prompts=[FramePrompt(points=[PromptPoint(x=x, y=y)])]) for i, (x, y) in points.items()]
    return parse(_call(build_object_prompt(size=size, objects=objects), image_path))
