import json

import pytest

from plan2cost.agent import state
from plan2cost.agent.loop import resume, run_agent
from plan2cost.agent.state import Run
from plan2cost.agent.tools import TOOLS, quote_on_page


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "RUNS_DIR", tmp_path)


def script(*actions):
    """A model that plays back fixed actions, and records what it was shown."""
    it = iter(actions)
    seen = []

    def llm(messages):
        seen.append(messages[-1]["content"])
        return json.dumps(next(it))
    llm.seen = seen
    return llm


def A(tool, **args):
    return {"tool": tool, "args": args, "reason": "test"}


ITEMS = [{"question": "Storey height?"}, {"question": "External girth, ground?"}, {"question": "Doors?"}]


def test_quote_matching_ignores_case_and_spacing():
    assert quote_on_page("FIRST  FLR. LEVEL", "first flr. level 3600")
    assert not quote_on_page("ROOF LEVEL", "first flr. level 3600")


def test_fact_needs_checklist_and_basis():
    run = Run.new("x.pdf", "obj")
    assert "error" in TOOLS["record_fact"][0](run, item="C1", name="h", value=3.0)          # no checklist yet
    TOOLS["set_checklist"][0](run, ITEMS)
    assert "error" in TOOLS["record_fact"][0](run, item="C1", name="h", value=3.0, source="assumed")  # no basis
    out = TOOLS["record_fact"][0](run, item="C1", name="h", value=3.0, source="assumed", basis="standard storey")
    assert out["open_items"] == ["C2", "C3"] and run.assumptions[0]["basis"] == "standard storey"


def test_drawing_fact_refused_when_quote_not_on_page(monkeypatch):
    monkeypatch.setattr("plan2cost.pdf.page_text", lambda pdf, p: "FIRST FLR. LEVEL 3600")
    run = Run.new("x.pdf", "obj")
    TOOLS["set_checklist"][0](run, ITEMS)
    bad = TOOLS["record_fact"][0](run, item="C1", name="h", value=3000, page=9, quote="ROOF BASE 6600")
    assert "not on page 9" in bad["error"] and not run.facts
    ok = TOOLS["record_fact"][0](run, item="C1", name="h", value=3600, page=9, quote="first flr. level 3600")
    assert ok["recorded"]["verified"] == "quote found on the page"


def test_submit_is_refused_until_settled_then_accepted():
    run = Run.new("x.pdf", "obj")
    TOOLS["set_checklist"][0](run, ITEMS)
    assert "Items not settled" in TOOLS["submit_boq"][0](run)["refused"][0]
    for i in ("C1", "C2", "C3"):
        TOOLS["record_fact"][0](run, item=i, name=f"n{i}", value=1, source="user")
    assert any("No BoQ" in p for p in TOOLS["submit_boq"][0](run)["refused"])
    run.data["boq"] = {"items": [], "total": 0}
    assert TOOLS["submit_boq"][0](run) == {"filed": True} and run.status == "done"


def test_loop_pauses_for_the_user_and_resumes_with_their_answer():
    llm = script(A("set_checklist", items=ITEMS), A("ask_user", item="C1", question="What is the storey height?"),
                 A("record_fact", item="C1", name="storey_height_m", value=3.0, source="user"))
    run = run_agent(Run.new("x.pdf", "obj"), llm, max_turns=10)
    assert run.status == "needs_input" and run.pending["question"] == "What is the storey height?" and run.turn == 2
    with pytest.raises(ValueError):                       # no model call without an answer
        resume(run, None, llm)
    run = Run.load(run.id)                                 # state survives on disk
    run = resume(run, "3.0 metres", llm, max_turns=1)
    assert "The user answered: 3.0 metres" in llm.seen[-1] and run.checklist[0]["status"] == "proven"
    assert run.status == "paused"                          # out of turns, not done


def test_bad_reply_gets_feedback_not_a_crash():
    llm = script({"tool": "no_such_tool"})
    run = run_agent(Run.new("x.pdf", "obj"), llm, max_turns=1)
    assert "Reply with one JSON object" in run.messages[-1]["content"]
