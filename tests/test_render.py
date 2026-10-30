import base64
from types import SimpleNamespace

from plan2cost.agent import render
from plan2cost.agent.render import render_prompt, render_view
from plan2cost.kit.imagegen import edit_image


def massing(roof="hip", floors=1):
    op = lambda k: {"kind": k, "parent": "W-001", "x0": 0, "y0": 0, "x1": 1, "y1": 0}
    return {"roof": {"type": roof}, "floors": [{"openings": [op("window"), op("window"), op("door")]} for _ in range(floors)]}


def test_the_prompt_says_what_this_view_shows_and_forbids_inventing_more():
    p = render_prompt(massing("hip"), {"windows": 3, "doors": 1})
    assert "HIP roof" in p and "single-storey" in p and "exactly 3 windows and 1 doors" in p and "no others" in p
    q = render_prompt(massing("gable", 2))
    assert "GABLE roof" in q and "2-storey" in q and "4 windows" in q  # no view counts: the whole building
    assert "showed 5 windows" in render_prompt(massing(), {"windows": 2, "doors": 1}, "The last attempt showed 5 windows and 1 doors.")


def test_an_image_edit_sends_the_screenshot_to_the_image_model_and_returns_the_picture():
    calls = []

    class Images:
        def edit(self, **kw):
            calls.append(kw)
            return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"RIFFpicture").decode())])

    out = edit_image(b"\x89PNG...", "make it real", client=SimpleNamespace(images=Images()))
    assert out == b"RIFFpicture" and calls[0]["model"] == "muse-image-1.0" and calls[0]["image"][2] == "image/png" and calls[0]["n"] == 1


def fake_run(tmp_path):
    return SimpleNamespace(dir=tmp_path)


def test_a_picture_with_the_wrong_number_of_windows_is_made_again_once_and_the_closer_one_is_kept(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "massing", lambda run: massing())
    made = iter([b"first", b"second"])
    monkeypatch.setattr(render, "edit_image", lambda png, prompt, client=None: next(made))
    counts = {b"first": {"windows": 6, "doors": 1}, b"second": {"windows": 3, "doors": 2}}
    r = render_view(fake_run(tmp_path), b"png", {"windows": 3, "doors": 1}, count=lambda pic: counts[pic])
    assert r["attempts"] == 2 and r["matched"] is False and r["counted"] == {"windows": 3, "doors": 2} and (tmp_path / r["path"]).read_bytes() == b"second"  # 1 off beats 3 off


def test_a_picture_that_matches_is_made_once_and_one_that_could_not_be_checked_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "massing", lambda run: massing())
    monkeypatch.setattr(render, "edit_image", lambda png, prompt, client=None: b"pic")
    ok = render_view(fake_run(tmp_path), b"png", {"windows": 3, "doors": 1}, count=lambda pic: {"windows": 3, "doors": 1})
    assert ok["attempts"] == 1 and ok["matched"] is True

    def broken(pic):
        raise RuntimeError("no connection")
    unchecked = render_view(fake_run(tmp_path), b"png", {"windows": 3, "doors": 1}, count=broken)
    assert unchecked["attempts"] == 1 and unchecked["matched"] is None and unchecked["counted"] is None
    assert render_view(fake_run(tmp_path), b"png", None)["matched"] is None  # no counts from the view: nothing to hold it to
