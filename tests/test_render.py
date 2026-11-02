import base64
from types import SimpleNamespace

from plan2cost.agent import render
from plan2cost.agent.render import judge, render_prompt, render_view
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


def counts(sam=None, spark=None):
    return {"sam": None if sam is None else {"windows": sam[0], "doors": sam[1], "overlay": b"jpeg"}, "spark": None if spark is None else {"windows": spark[0], "doors": spark[1]}}


def test_a_picture_matches_when_either_counter_gives_the_views_counts_or_both_give_its_total():
    view = {"windows": 11, "doors": 11}
    assert judge(counts(sam=(13, 9), spark=(11, 11)), view) == (True, 0)  # SAM took two glass doors for windows; Muse Spark is exact
    assert judge(counts(sam=(16, 1), spark=(14, 2)), {"windows": 16, "doors": 1})[0] is True  # the other way round
    assert judge(counts(sam=(13, 9), spark=(12, 10)), view)[0] is True  # both give the right total of 22 whatever the split
    assert judge(counts(sam=(14, 11), spark=(10, 12)), view) == (False, 2)  # neither: the closer counter (Muse Spark) is 2 off
    assert judge(counts(sam=(11, 11)), view) == (True, 0) and judge(counts(sam=(12, 11)), view) == (False, 1)  # one counter answered
    assert judge({"sam": None, "spark": None}, view) == (None, None)  # neither answered: not checked


def test_sam_counts_and_outlines_the_windows_and_doors_in_a_picture(monkeypatch):
    import io
    from types import SimpleNamespace

    from PIL import Image

    import plan2cost.facts.sam as sam_module

    seg = lambda box: SimpleNamespace(box=box)
    monkeypatch.setattr(sam_module, "segment_concept", lambda path, phrase: [seg((10, 10, 40, 60)), seg((60, 10, 90, 60))] if phrase == "window" else [seg((100, 40, 130, 120))])
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (240, 240, 240)).save(buf, "PNG")
    out = render._sam_counts(buf.getvalue())
    assert (out["windows"], out["doors"]) == (2, 1)
    overlay = Image.open(io.BytesIO(out["overlay"]))
    assert overlay.size == (200, 150)
    assert all(abs(a - b) < 45 for a, b in zip(overlay.getpixel((10, 30)), render.SAM_COLOURS["window"]))  # the edge of the first window box, drawn in teal (JPEG blurs it a little)


def test_a_picture_that_neither_counter_matches_is_made_again_once_and_the_closer_one_is_kept(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "massing", lambda run: massing())
    made = iter([b"first", b"second"])
    monkeypatch.setattr(render, "edit_image", lambda png, prompt, client=None: next(made))
    answers = {b"first": counts(sam=(6, 1), spark=(7, 1)), b"second": counts(sam=(3, 2), spark=(4, 2))}
    r = render_view(fake_run(tmp_path), b"png", {"windows": 3, "doors": 1}, count=lambda pic: answers[pic])
    assert r["attempts"] == 2 and r["matched"] is False and (tmp_path / r["path"]).read_bytes() == b"second"  # 1 off beats 3 off
    assert r["counts"]["sam"] == {"windows": 3, "doors": 2} and "overlay" not in r["counts"]["sam"]  # the overlay is saved, not returned in the counts
    assert (tmp_path / r["overlay"]).read_bytes() == b"jpeg"


def test_a_picture_that_matches_is_made_once_and_one_that_could_not_be_checked_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "massing", lambda run: massing())
    monkeypatch.setattr(render, "edit_image", lambda png, prompt, client=None: b"pic")
    ok = render_view(fake_run(tmp_path), b"png", {"windows": 3, "doors": 1}, count=lambda pic: counts(sam=(3, 1), spark=(3, 2)))
    assert ok["attempts"] == 1 and ok["matched"] is True and ok["overlay"]

    def broken(pic):
        raise RuntimeError("no connection")
    unchecked = render_view(fake_run(tmp_path), b"png", {"windows": 3, "doors": 1}, count=broken)
    assert unchecked["attempts"] == 1 and unchecked["matched"] is None and unchecked["counts"] is None and unchecked["overlay"] is None
    assert render_view(fake_run(tmp_path), b"png", None)["matched"] is None  # no counts from the view: nothing to hold it to
