import json

import pytest

from plan2cost.agent import loop, view
from plan2cost.agent.loop import resume, run_agent
from plan2cost.agent.verify import verify_boq
from plan2cost.kit import progress as state
from plan2cost.kit.progress import Run
from plan2cost.tools import TOOLS
from plan2cost.tools.records import seed_checklist, settle

FLOORS = [{"name": "ground", "file": "g.png", "page": 1}, {"name": "first", "file": "f.png", "page": 1}]
INPUTS = {"storey_height_m": 3.0, "roof_type": "hip", "pitch_deg": None, "overhang_m": None}


def floor_data(name, scale=1.0):
    return {"name": name, "ext_m": 62.0 * scale, "int_m": 55.0 * scale, "junctions": 18, "length_m": 11.2 * scale, "width_m": 15.8 * scale, "wall_plan_area_m2": 22.5 * scale,
            "openings": [{"label": "W1200", "width_m": 1.2, "height_m": 1.2, "count": 6, "kind": "window", "external": True, "assumed_height": True},
                         {"label": "D900", "width_m": 0.9, "height_m": 2.1, "count": 5, "kind": "door", "external": False, "assumed_height": True}],
            "rooms": ["Bedroom 1", "Bath/wc", "Kitchen", "Lounge"], "route": "vector", "confidence": "high", "markup": "", "page": 1}


def stub_read_floor(run, floor):
    """The real read_floor measures a drawing; here the measurement is canned so the loop and the gate can be tested."""
    run.data.setdefault("floors", {})[floor] = floor_data(floor, 1.0 if floor == "ground" else 0.8)
    run.data.setdefault("models", {})[floor] = {"markup": "", "walls": 20, "total_m": 117.0}
    settle(run, next(c["id"] for c in run.checklist if f"the {floor} floor" in c["question"]))
    return {"floor": floor, "ext_girth_m": 62.0}


STUBBED = {**TOOLS, "read_floor": (stub_read_floor, "stub")}


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(loop, "make_thumbs", lambda run: None)


def script(*actions):
    it = iter(actions)
    seen = []

    def llm(messages):
        seen.append(messages[-1]["content"])
        return json.dumps(next(it))
    llm.seen = seen
    return llm


def A(tool, **args):
    return {"tool": tool, "args": args, "reason": "test"}


def new_run():
    return Run.new([dict(f) for f in FLOORS], dict(INPUTS))


def test_the_checklist_is_made_by_code_from_the_floors():
    run = new_run()
    seed_checklist(run)
    assert [c["question"].split(":")[0] for c in run.checklist][:2] == ["Read the ground floor plan", "Read the first floor plan"] and len(run.checklist) == 3


def test_a_whole_run_reads_each_floor_computes_and_files_two_bills(tmp_path):
    llm = script(A("read_floor", floor="ground"), A("read_floor", floor="first"), A("compute_boq"), A("submit_boq", summary="done"))
    run = run_agent(new_run(), llm, max_turns=10, tools=STUBBED)
    assert run.status == "done" and run.turn == 4
    assert (run.dir / "bill_priced.xlsx").exists() and (run.dir / "bill_priced.pdf").exists()
    assert not (run.dir / "bill_unpriced.xlsx").exists()  # estimated quantities are not sent out for tender
    boq = run.data["boq"]
    assert boq["total_low"] <= boq["total"] <= boq["total_high"] and 0 < boq["estimated_share"] < 1
    assert "covers" in run.result["summary"]


def test_submit_is_refused_until_every_floor_is_read_and_the_estimate_computed():
    run = new_run()
    seed_checklist(run)
    out = TOOLS["submit_boq"][0](run)
    assert any("Floors not read" in p for p in out["refused"]) and any("not been computed" in p for p in out["refused"])
    stub_read_floor(run, "ground")
    stub_read_floor(run, "first")
    assert verify_boq(run) == ["The estimate has not been computed yet (compute_boq)."] or any("compute_boq" in p for p in verify_boq(run))
    assert "error" not in TOOLS["compute_boq"][0](run)
    assert verify_boq(run) == []


def test_compute_boq_refuses_without_the_inputs_or_with_a_floor_unread():
    run = Run.new([dict(f) for f in FLOORS], {"storey_height_m": None, "roof_type": "dome"})
    seed_checklist(run)
    out = TOOLS["compute_boq"][0](run)
    assert "storey height" in out["error"] and "roof type" in out["error"] and "Floors not read" in out["error"]


def test_an_unreadable_upper_floor_can_stand_in_for_the_ground_and_is_flagged():
    run = new_run()
    seed_checklist(run)
    assert "error" in TOOLS["assume_floor_like_ground"][0](run, "first")  # ground not read yet
    stub_read_floor(run, "ground")
    assert TOOLS["assume_floor_like_ground"][0](run, "first")["assumed_like_ground"]
    assert any(a["name"] == "floor_first_like_ground" for a in run.assumptions) and run.checklist[1]["status"] == "assumed"


def test_loop_pauses_for_the_user_and_resumes_with_their_answer():
    llm = script(A("ask_user", question="Is the ground floor plan the one with the garage?", item="C1"), A("read_floor", floor="ground"))
    run = run_agent(new_run(), llm, max_turns=10, tools=STUBBED)
    assert run.status == "needs_input" and run.turn == 1
    with pytest.raises(ValueError):
        resume(run, None, llm)
    run = Run.load(run.id)
    run = resume(run, "yes", llm, max_turns=1, tools=STUBBED)
    assert "The user answered: yes" in llm.seen[-1] and run.status == "paused"


def test_bad_reply_gets_feedback_not_a_crash():
    run = run_agent(new_run(), script({"tool": "no_such_tool"}), max_turns=1, tools=STUBBED)
    assert "Reply with one JSON object" in run.messages[-1]["content"]


def test_console_stages_follow_the_floors_read_then_the_estimate():
    llm = script(A("read_floor", floor="ground"), A("read_floor", floor="first"), A("compute_boq"))
    run = run_agent(new_run(), llm, max_turns=3, tools=STUBBED)
    st = view.stages(run, view.turns(run), None)
    assert [(s["label"], s["done"]) for s in st] == [("Read the floor plans", True), ("Estimate", True), ("Filed", False)]
    assert view.list_runs()[0]["floors"] == ["ground", "first"]


def test_a_dropped_connection_is_retried_and_then_pauses_the_run_instead_of_losing_it(monkeypatch):
    monkeypatch.setattr(loop.time, "sleep", lambda s: None)
    calls = []

    def flaky(messages):
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("dropped")
        return json.dumps(A("read_floor", floor="ground"))

    run = new_run()
    seed_checklist(run)
    loop.step(run, flaky, STUBBED)
    assert len(calls) == 3 and run.turn == 1

    def dead(messages):
        raise ConnectionError("down")

    run = loop.run_agent(run, dead, max_turns=2, tools=STUBBED)
    assert run.status == "paused" and "down" in run.data["error"]


def test_an_old_run_saved_by_the_earlier_layout_still_opens():
    (state.RUNS_DIR / "20260101-000000").mkdir()
    (state.RUNS_DIR / "20260101-000000" / "run.json").write_text(json.dumps({"id": "20260101-000000", "pdf": "old.pdf", "objective": "x", "status": "done", "pages": []}))
    assert Run.load("20260101-000000").floors == []


def test_all_floors_are_read_together_and_a_failed_one_is_reported(monkeypatch):
    from plan2cost.tools import drawings

    class Model:
        markup, route, confidence = "m.jpg", "vector", "high"
        calibrations = [type("C", (), {"basis": "x"})()]

        def walls(self):
            return []

    def measure(run, floor, on_walls):
        if floor == "first":
            return {"error": "no walls"}
        return {"data": floor_data(floor), "model": Model(), "issues": [], "note": "", "page": 1}

    monkeypatch.setattr(drawings, "_measure", measure)
    monkeypatch.setattr(Model, "summary", lambda self: {}, raising=False)
    run = new_run()
    seed_checklist(run)
    out = drawings.read_all_floors(run)
    assert out["failed"] == ["first"] and out["floors"]["ground"]["ext_girth_m"] == 62.0 and "ground" in run.data["floors"] and "first" not in run.data["floors"]
    assert run.checklist[0]["status"] == "proven" and run.checklist[1]["status"] == "open"


def test_measured_gaps_are_snapped_to_the_standard_sizes_so_the_bill_has_few_types():
    from plan2cost.tools.drawings import DOOR_WIDTHS_MM, WINDOW_WIDTHS_MM, snap

    assert snap(560, DOOR_WIDTHS_MM) == 750 and snap(1120, DOOR_WIDTHS_MM) == 1050 and snap(980, WINDOW_WIDTHS_MM) == 900 and snap(1640, WINDOW_WIDTHS_MM) == 1500
