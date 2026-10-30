import base64
from types import SimpleNamespace

from plan2cost.agent.render import render_prompt
from plan2cost.kit.imagegen import edit_image


def massing(roof="hip", floors=1):
    op = lambda k: {"kind": k, "parent": "W-001", "x0": 0, "y0": 0, "x1": 1, "y1": 0}
    return {"roof": {"type": roof}, "floors": [{"openings": [op("window"), op("window"), op("door")]} for _ in range(floors)]}


def test_the_prompt_says_what_was_measured_and_forbids_inventing_more():
    p = render_prompt(massing("hip"))
    assert "HIP roof" in p and "single-storey" in p and "2 windows and 1 doors" in p and "add no others" in p
    q = render_prompt(massing("gable", 2))
    assert "GABLE roof" in q and "2-storey" in q and "4 windows" in q


def test_an_image_edit_sends_the_screenshot_to_the_image_model_and_returns_the_picture():
    calls = []

    class Images:
        def edit(self, **kw):
            calls.append(kw)
            return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"RIFFpicture").decode())])

    out = edit_image(b"\x89PNG...", "make it real", client=SimpleNamespace(images=Images()))
    assert out == b"RIFFpicture" and calls[0]["model"] == "muse-image-1.0" and calls[0]["image"][2] == "image/png" and calls[0]["n"] == 1
