"""A realistic illustration of the 3D massing: a screenshot of the 3D view goes to Muse Image with a prompt built from what was measured (roof type, storeys, and the windows and doors
visible from this camera), and the picture is saved with the run. Two Meta models then count the windows and doors in the picture independently: SAM 3.1 (which also outlines each one, and
that overlay is saved) and Muse Spark. If neither matches the view it came from, it is made once more with that said, and the result says whether it matched. It is an artist's
impression: the finishes, the proportions and the exact window positions are the model's interpretation, so it is labelled illustrative everywhere and never feeds a quantity."""
import io
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from plan2cost.agent.massing import massing
from plan2cost.kit.imagegen import edit_image
from plan2cost.kit.progress import Run

ROOF_WORDS = {"hip": "a HIP roof (four sloping faces meeting at a ridge, with no vertical gable end)", "gable": "a GABLE roof (two sloping faces and two vertical gable ends)",
              "flat": "a FLAT roof (a flat slab roof with a low parapet, no slope)"}
COUNT_PROMPT = """Look at this picture of a house. Count the windows and the doors you can see on the house (an entrance door counts as a door; a window with several panes is one window; a sliding glass
door is a door). Return only JSON: {"windows": number, "doors": number}"""


def render_prompt(m: dict, visible: dict | None = None, feedback: str = "") -> str:
    """The prompt for the picture: what the building is (storeys, roof type) and which windows and doors the view shows (those seen from the camera, or the whole building when no counts are given); `feedback` says what a previous try got wrong."""
    n = len(m["floors"])
    storeys = "a single-storey" if n == 1 else f"a {n}-storey"
    if visible and "windows" in visible and "doors" in visible:
        seen = f"In THIS view exactly {visible['windows']} windows and {visible['doors']} doors can be seen: draw exactly those, in the places shown, and no others."
    else:
        windows = sum(1 for f in m["floors"] for o in f["openings"] if o["kind"] == "window")
        doors = sum(1 for f in m["floors"] for o in f["openings"] if o["kind"] == "door")
        seen = f"The whole building has {windows} windows and {doors} doors; show only the ones visible in the picture and add no others."
    return (f"Image-to-image: re-render this 3D massing model of {storeys} house as a photorealistic architectural photograph. Follow the picture exactly: it is the geometry. "
            f"Same camera angle and framing. The roof is {ROOF_WORDS.get(m['roof']['type'], 'a plain roof')} with the same eaves overhang. Keep the same footprint, the same number of storeys, "
            f"and the same openings in the same places: the teal openings are windows (render them as aluminium windows with glass), the brown ones are doors. {seen} "
            "Do not add a porch, extension, chimney, balcony or extra storey. Only add realism: render and paint on the walls, roof tiles in the same colour, ground, lawn, soft daylight and a plain sky. "
            + feedback)


SAM_COLOURS = {"window": (0, 150, 170), "door": (170, 0, 170)}  # teal windows and purple doors, as on the annotated plan
SAM_SIDE = 1280  # the picture is sent to SAM at most this many pixels on a side


def _spark_counts(picture: bytes) -> dict:
    """Muse Spark counts the windows and doors in a picture."""
    from plan2cost.kit.client import chat_json, image_part

    path = Path(tempfile.mkdtemp()) / "picture.webp"
    path.write_bytes(picture)
    r = chat_json([{"type": "text", "text": COUNT_PROMPT}, image_part(str(path))])
    return {"windows": int(r.get("windows", 0)), "doors": int(r.get("doors", 0))}


def draw_detections(img: Image.Image, boxes: dict) -> bytes:
    """The picture with a box round everything SAM found (teal windows, purple doors) and the counts written on it, as JPEG bytes."""
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    for kind, bs in boxes.items():
        for x1, y1, x2, y2 in bs:
            d.rectangle((x1, y1, x2, y2), outline=SAM_COLOURS[kind], width=max(2, img.width // 400))
    label = f"SAM 3.1 found {len(boxes.get('window', []))} windows and {len(boxes.get('door', []))} doors"
    d.rectangle((0, 0, 8 * len(label) + 16, 22), fill=(255, 255, 255))
    d.text((8, 5), label, fill=(30, 30, 30))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def _sam_counts(picture: bytes) -> dict:
    """SAM 3.1 finds every window and every door in the picture (one question for each) and outlines them. Returns the counts and the picture with the boxes drawn on it (`overlay`)."""
    from plan2cost.facts.sam import segment_concept

    img = Image.open(io.BytesIO(picture)).convert("RGB")
    img.thumbnail((SAM_SIDE, SAM_SIDE))
    path = str(Path(tempfile.mkdtemp()) / "picture.jpg")
    img.save(path, "JPEG", quality=90)
    with ThreadPoolExecutor(2) as ex:
        found = dict(zip(("window", "door"), ex.map(lambda phrase: segment_concept(path, phrase), ("window", "door"))))
    boxes = {k: [s.box for s in segs] for k, segs in found.items()}
    return {"windows": len(boxes["window"]), "doors": len(boxes["door"]), "overlay": draw_detections(img, boxes)}


def count_openings(picture: bytes) -> dict:
    """Both counters on one picture at the same time: {"sam": counts (with the overlay) or None, "spark": counts or None}. A counter that fails is None, never a guess."""
    out = {}
    with ThreadPoolExecutor(2) as ex:
        futures = {"sam": ex.submit(_sam_counts, picture), "spark": ex.submit(_spark_counts, picture)}
        for k, f in futures.items():
            try:
                out[k] = f.result()
            except Exception:  # the check failed, not the picture
                out[k] = None
    return out


def judge(counts: dict, visible: dict) -> tuple[bool | None, int | None]:
    """Does the picture show what the view shows? Matched when either counter gives exactly the view's windows and doors, or both give the view's total of openings (the split between
    a glass door and a window is what they get wrong, not the total). Returns (matched, how far the closer counter is off), or (None, None) when neither counter answered."""
    got = [c for c in (counts.get("sam"), counts.get("spark")) if c]
    if not got:
        return None, None
    want_w, want_d = visible["windows"], visible["doors"]
    gap = min(abs(c["windows"] - want_w) + abs(c["doors"] - want_d) for c in got)
    totals = [c["windows"] + c["doors"] for c in got]
    return gap == 0 or (len(got) == 2 and totals[0] == totals[1] == want_w + want_d), gap


def render_view(run: Run, png: bytes, visible: dict | None = None, client=None, count=count_openings, attempts: int = 2) -> dict:
    """Make the illustration of the view in `png`, check it against what the view shows with two counters, and save the best one under the run's renders folder (with SAM's overlay).
    Returns {"path": relative path, "overlay": path of the SAM overlay or None, "expected": visible counts or None, "counts": {"sam": ..., "spark": ...} or None,
    "matched": bool or None, "attempts": n}."""
    m = massing(run)
    best, feedback = None, ""
    for n in range(1, attempts + 1):
        picture = edit_image(png, render_prompt(m, visible, feedback), client)
        counts, ok, gap = None, None, None
        if visible and "windows" in visible:
            try:
                counts = count(picture)
            except Exception:  # the check failed, not the picture: keep it, say it was not checked
                counts = None
            if counts:
                ok, gap = judge(counts, visible)
        if best is None or (gap is not None and (best[0] is None or gap < best[0])):
            best = (gap, picture, counts, ok)
        if ok or counts is None or ok is None:
            break
        sam, spark = counts.get("sam"), counts.get("spark")
        said = " and ".join(f"{c['windows']} windows and {c['doors']} doors" for c in (sam, spark) if c)
        feedback = f"The last attempt showed {said} when counted; this view must show exactly {visible['windows']} windows and {visible['doors']} doors."
    _, picture, counts, ok = best
    folder = run.dir / "renders"
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"render_{len(list(folder.glob('render_*.webp'))) + 1:03d}"
    (folder / f"{stem}.webp").write_bytes(picture)
    overlay = None
    sam = (counts or {}).get("sam")
    if sam and sam.get("overlay"):
        (folder / f"{stem}_sam.jpg").write_bytes(sam["overlay"])
        overlay = f"renders/{stem}_sam.jpg"
    shown = {k: ({kk: vv for kk, vv in c.items() if kk != "overlay"} if c else None) for k, c in counts.items()} if counts else None
    return {"path": f"renders/{stem}.webp", "overlay": overlay, "expected": visible if visible and "windows" in visible else None, "counts": shown,
            "matched": ok if (counts and visible) else None, "attempts": n}
