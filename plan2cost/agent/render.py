"""A realistic illustration of the 3D massing: a screenshot of the 3D view goes to Muse Image with a prompt built from what was measured (roof type, storeys, the window and door
openings), and the picture is saved with the run. It is an artist's impression: the finishes, the proportions and the exact window positions are the model's interpretation, so it
is labelled illustrative everywhere and never feeds a quantity."""
from plan2cost.agent.massing import massing
from plan2cost.kit.imagegen import edit_image
from plan2cost.kit.progress import Run

ROOF_WORDS = {"hip": "a HIP roof (four sloping faces meeting at a ridge, with no vertical gable end)", "gable": "a GABLE roof (two sloping faces and two vertical gable ends)",
              "flat": "a FLAT roof (a flat slab roof with a low parapet, no slope)"}


def render_prompt(m: dict) -> str:
    n = len(m["floors"])
    windows = sum(1 for f in m["floors"] for o in f["openings"] if o["kind"] == "window")
    doors = sum(1 for f in m["floors"] for o in f["openings"] if o["kind"] == "door")
    storeys = "a single-storey" if n == 1 else f"a {n}-storey"
    return (f"Image-to-image: re-render this 3D massing model of {storeys} house as a photorealistic architectural photograph. Follow the picture exactly: it is the geometry. "
            f"Same camera angle and framing. The roof is {ROOF_WORDS.get(m['roof']['type'], 'a plain roof')} with the same eaves overhang. Keep the same footprint, the same number of storeys, "
            f"and the same openings in the same places: the teal openings are windows (render them as aluminium windows with glass), the brown ones are doors. The whole building has {windows} windows and {doors} doors; "
            "show only the ones visible in the picture and add no others. Do not add a porch, extension, chimney, balcony or extra storey. "
            "Only add realism: render and paint on the walls, roof tiles in the same colour, ground, lawn, soft daylight and a plain sky.")


def render_view(run: Run, png: bytes, client=None) -> str:
    """Make the illustration of the view in `png` and save it under the run's renders folder; returns its path relative to the run folder."""
    out = edit_image(png, render_prompt(massing(run)), client)
    folder = run.dir / "renders"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"render_{len(list(folder.glob('render_*.webp'))) + 1:03d}.webp"
    (folder / name).write_bytes(out)
    return f"renders/{name}"
