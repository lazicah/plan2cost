"""The agent loop: plan, act, observe, one tool per turn, until the BoQ is filed or a person is needed."""
import json
from pathlib import Path
from typing import Callable

from plan2cost.kit.client import parse_json
from plan2cost.kit.progress import Run
from plan2cost.tools import TOOLS

SYSTEM = (Path(__file__).parent / "system_instructions.md").read_text()


def _system() -> str:
    return SYSTEM.format(tools="\n".join(f"- {name}: {doc}" for name, (_, doc) in TOOLS.items()))


def default_llm(messages: list) -> str:
    from plan2cost.kit.client import get_client, model_name

    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=messages)
    return resp.choices[0].message.content


def step(run: Run, llm: Callable[[list], str], tools: dict | None = None) -> None:
    tools = tools or TOOLS
    reply = llm(run.messages)
    run.messages.append({"role": "assistant", "content": reply})
    run.turn += 1
    run.save()  # so the console shows which tool is running while a slow one (a plan read) works
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
                        {"role": "user", "content": f"Objective: {run.objective}\nThe drawing set is the PDF at: {run.pdf}" + ("\nA structural drawing set is also given: read_foundation_section, read_pad_bases and read_strip_layout must be called before compute_foundation." if run.structural_pdf else "")
                        + ("\nA contractor quote is also given: after compute_boq call audit_quote, then report its flags in plain words in your summary." if run.quote else "")}]
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
