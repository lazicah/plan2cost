"""The agent loop: plan, act, observe, one tool per turn, until the BoQ is filed or a person is needed."""
import json
from typing import Callable

from plan2cost.agent.state import Run
from plan2cost.agent.tools import TOOLS
from plan2cost.extract import parse_json

SYSTEM = """You are a quantity-surveying agent. You turn a set of building drawings into a Bill of Quantities (BoQ) with an approximate cost.
You work in turns. Each turn, reply with ONE JSON object and nothing else: {{"tool": name, "args": {{...}}, "reason": short why}}.

How to work:
1. Index the document (index_document) so you know what every page is. The WHOLE set matters: plans, sections, elevations and schedules.
2. Set a checklist (set_checklist): the questions that must be settled to cost this building, for example storey heights, wall girth
   per floor, door and window sizes and counts, finishes. Each item is a question the drawings can answer.
3. Read what the drawings say (read_levels, read_openings, read_notes for specifications such as roof sheet, ceiling and floor finish, read_wall_girth). The drawings are the guide: a value printed on the drawings always wins.
4. Record each value against a checklist item (record_fact). A value from the drawings needs its page and the exact printed text.
   Use "assumed" only when the set is silent, give the standard it comes from, and it will be flagged.
5. If an item cannot be settled from the drawings and no standard default is safe, ask the user (ask_user). Never guess a dimension.
6. compute_foundation (strip foundation from the ground floor walls), then compute_boq, then submit_boq. Submit is refused until every checklist item is settled.

Wall girth comes from read_wall_girth on each floor-plan page; record it as source "computed" (it is approximate). read_wall_girth also reports junction_ends: record it as junction_ends_ground for the ground floor. Wall girth per floor is recorded as facts named ext_girth_<floor>_m and int_girth_<floor>_m (floor: ground, first, ...).
Girth is your job, never the user's: the users are not technical and do not know the word. Read the wall lengths from the plan, grid line by
grid line. If a floor cannot be read reliably, use estimate_girth_from_footprint from the overall length and width, record it as assumed,
and carry on. Ask the user only plain questions that the drawings cannot answer (for example the soil, the quality level, the city),
in everyday words, never about girth, centre lines, blockwork area or other measurement terms. Use sum_lengths to add numbers; never add them yourself.
External and internal walls are measured separately. Never do arithmetic yourself: the numbers in the BoQ come from compute_boq.

Tools:
{tools}
"""


def _system() -> str:
    return SYSTEM.format(tools="\n".join(f"- {name}: {doc}" for name, (_, doc) in TOOLS.items()))


def default_llm(messages: list) -> str:
    from plan2cost.client import get_client, model_name

    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=messages)
    return resp.choices[0].message.content


def step(run: Run, llm: Callable[[list], str], tools: dict | None = None) -> None:
    tools = tools or TOOLS
    reply = llm(run.messages)
    run.messages.append({"role": "assistant", "content": reply})
    run.turn += 1
    try:
        action = parse_json(reply)
        name, args = action["tool"], action.get("args") or {}
        fn = tools[name][0]
    except (ValueError, KeyError, TypeError) as e:
        result = {"error": f"Reply with one JSON object naming a tool from the list ({e})."}
        name, action = "(invalid)", {}
    else:
        try:
            result = fn(run, **args)
        except TypeError as e:
            result = {"error": f"Bad arguments for {name}: {e}"}
    run.messages.append({"role": "user", "content": "Tool result: " + json.dumps(result, default=str)})
    run.trace(f"## Turn {run.turn}: {name}\n{action.get('reason', '')}\n```json\n{json.dumps(result, indent=1, default=str)[:1500]}\n```")
    run.save()


def run_agent(run: Run, llm: Callable[[list], str] = default_llm, max_turns: int = 30, tools: dict | None = None) -> Run:
    if not run.messages:
        run.messages = [{"role": "system", "content": _system()},
                        {"role": "user", "content": f"Objective: {run.objective}\nThe drawing set is the PDF at: {run.pdf}"}]
    start = run.turn
    while run.status == "running" and run.turn - start < max_turns:
        step(run, llm, tools)
    if run.status == "running":
        run.status = "paused"  # out of turns; resume continues
    run.save()
    return run


def resume(run: Run, answer: str | None = None, llm: Callable[[list], str] = default_llm, max_turns: int = 30,
           tools: dict | None = None) -> Run:
    """Continue from saved state. A run waiting on a person needs their answer; no model call is made without it."""
    if run.status == "needs_input":
        if not answer:
            raise ValueError(f"Run is waiting for the user: {run.pending['question']}")
        item = next((c for c in run.checklist if c["id"] == run.pending["item"]), None)
        if item:
            item["status"] = "open"
        run.messages.append({"role": "user", "content": f"The user answered: {answer}\nRecord it with record_fact (source \"user\") and continue."})
        run.trace(f"## User answered ({run.pending['item']}): {answer}")
        run.pending = None
    elif run.status in ("done", "failed"):
        raise ValueError(f"Run is {run.status}.")
    run.status = "running"
    return run_agent(run, llm, max_turns, tools)
