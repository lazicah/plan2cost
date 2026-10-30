"""The agent loop: plan, act, observe, one tool per turn, until the BoQ is filed or a person is needed."""
import json
import time
from pathlib import Path
from typing import Callable

from plan2cost.kit.client import parse_json
from plan2cost.kit.progress import Run
from plan2cost.tools import TOOLS
from plan2cost.tools.records import seed_checklist

SYSTEM = (Path(__file__).parent / "system_instructions.md").read_text()


def make_thumbs(run: Run) -> None:
    """A small picture of each floor plan for the console, made before the first model call so the drawings show while they are read."""
    import cv2

    from plan2cost.kit.pdf import render_pages

    out = run.dir / "pages"
    out.mkdir(parents=True, exist_ok=True)
    for n, f in enumerate(run.floors, 1):
        try:
            src = render_pages(f["file"], [int(f.get("page") or 1)], str(out / "tmp"), dpi=60)[0] if f["file"].lower().endswith(".pdf") else f["file"]
            img = cv2.imread(src)
            k = 900 / max(img.shape[:2])
            cv2.imwrite(str(out / f"p{n:02d}.jpg"), cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img)
        except Exception:  # a missing thumbnail must never stop a run
            pass


def _system() -> str:
    return SYSTEM.format(tools="\n".join(f"- {name}: {doc}" for name, (_, doc) in TOOLS.items()))


def default_llm(messages: list) -> str:
    """One chat call to the model the active profile names (the Meta Model API or Muse Spark Open); returns the reply text."""
    from plan2cost.kit.client import get_client, model_name

    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=messages)
    return resp.choices[0].message.content


def _ask(llm: Callable[[list], str], messages: list, tries: int = 3) -> str:
    """A dropped connection to the model should not end a run: retry a few times with a pause, then let the error through."""
    for n in range(tries):
        try:
            return llm(messages)
        except (ConnectionError, TimeoutError) as e:
            err = e
        except Exception as e:  # the openai client's own connection and rate-limit errors
            if type(e).__name__ not in ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"):
                raise
            err = e
        time.sleep(3 * (n + 1))
    raise err


def step(run: Run, llm: Callable[[list], str], tools: dict | None = None) -> None:
    """One turn: ask the model for its next action, run the tool it names, add the result to the conversation, then save the run and write the trace. A reply that is not a valid tool call gets an error back so the model can correct itself."""
    tools = tools or TOOLS
    reply = _ask(llm, run.messages)
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
    """Drive the agent on a run until it is done, needs the user, or runs out of turns. The first call seeds the checklist and the opening message; a failure pauses the run with everything so far saved, so it can be resumed."""
    if not run.messages:
        seed_checklist(run)
        make_thumbs(run)
        floors = "\n".join(f"- {f['name']}: {f['file'].split('/')[-1]}" + (f" (page {f['page']})" if f.get("page") else "") for f in run.floors)
        inp = run.inputs
        run.messages = [{"role": "system", "content": _system()},
                        {"role": "user", "content": f"Objective: {run.objective}\nFloor plans given (lowest first):\n{floors}\nEntered by the user: storey height {inp.get('storey_height_m')} m (floor to floor), "
                                                    f"roof type {inp.get('roof_type')}" + (f", pitch {inp['pitch_deg']} degrees" if inp.get("pitch_deg") else "") + (f", overhang {inp['overhang_m']} m" if inp.get("overhang_m") else "")
                                                    + ("\nA contractor quote is also given: after compute_boq call audit_quote, then report its flags in plain words in your summary." if run.quote else "")}]
    start = run.turn
    try:
        while run.status == "running" and run.turn - start < max_turns:
            step(run, llm, tools)
    except Exception as e:  # the run is paused, not lost: everything so far is saved and resume continues
        run.data["error"] = f"{type(e).__name__}: {e}"[:300]
        run.status = "paused"
        run.trace(f"## Stopped: {run.data['error']}")
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
    if run.messages and run.messages[-1]["role"] == "assistant":  # stopped while a tool was running: tell the model so it can ask again
        run.messages.append({"role": "user", "content": "Tool result: " + json.dumps({"error": "The run was interrupted before this tool finished. Call it again if you still need it."})})
    run.data.pop("error", None)
    run.status = "running"
    return run_agent(run, llm, max_turns, tools)
