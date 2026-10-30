"""A realistic illustration of the 3D massing: a screenshot of the 3D view goes to Muse Image with a prompt built from what was measured (roof type, storeys, and the windows and doors
visible from this camera), and the picture is saved with the run. Muse Spark then counts the windows and doors in the picture; if they differ from the view it came from, it is made
once more with that said, and the result says whether it matched. It is an artist's impression: the finishes, the proportions and the exact window positions are the model's
interpretation, so it is labelled illustrative everywhere and never feeds a quantity."""
import tempfile
from pathlib import Path

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


def count_openings(picture: bytes) -> dict:
    """Muse Spark counts the windows and doors in a picture."""
    from plan2cost.kit.client import chat_json, image_part

    path = Path(tempfile.mkdtemp()) / "picture.webp"
    path.write_bytes(picture)
    r = chat_json([{"type": "text", "text": COUNT_PROMPT}, image_part(str(path))])
    return {"windows": int(r.get("windows", 0)), "doors": int(r.get("doors", 0))}


def render_view(run: Run, png: bytes, visible: dict | None = None, client=None, count=count_openings, attempts: int = 2) -> dict:
    """Make the illustration of the view in `png`, check it against what the view shows, and save the best one under the run's renders folder. Returns
    {"path": relative path, "expected": visible counts or None, "counted": counts in the picture or None, "matched": bool or None, "attempts": n}."""
    m = massing(run)
    best, feedback = None, ""
    for n in range(1, attempts + 1):
        picture = edit_image(png, render_prompt(m, visible, feedback), client)
        counted = None
        if visible and "windows" in visible:
            try:
                counted = count(picture)
            except Exception:  # the check failed, not the picture: keep it, say it was not checked
                counted = None
        ok = counted is not None and counted["windows"] == visible["windows"] and counted["doors"] == visible["doors"]
        gap = 99 if counted is None else abs(counted["windows"] - visible["windows"]) + abs(counted["doors"] - visible["doors"])
        if best is None or gap < best[0]:
            best = (gap, picture, counted, ok)
        if ok or counted is None:
            break
        feedback = f"The last attempt showed {counted['windows']} windows and {counted['doors']} doors; this view must show exactly {visible['windows']} windows and {visible['doors']} doors."
    _, picture, counted, ok = best
    folder = run.dir / "renders"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"render_{len(list(folder.glob('render_*.webp'))) + 1:03d}.webp"
    (folder / name).write_bytes(picture)
    return {"path": f"renders/{name}", "expected": visible if visible and "windows" in visible else None, "counted": counted, "matched": ok if (counted is not None and visible) else None, "attempts": n}
