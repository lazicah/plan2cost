"""Bookkeeping: facts with their source, the questions that pause the run for a person, and the stand-in for a floor that cannot be read. Tools record the facts they
measure themselves, so the model never retypes a number."""
from plan2cost.kit.progress import Run

SOURCES = ("drawing", "assumed", "user", "computed")


def seed_checklist(run: Run) -> None:
    """What must be settled before the estimate can be filed: each floor read, then the estimate itself. Made by code, not by the model."""
    run.checklist = [{"id": f"C{i}", "question": f"Read the {f['name']} floor plan: walls, openings and rooms", "evidence": f["file"].split("/")[-1], "status": "open"} for i, f in enumerate(run.floors, 1)]
    run.checklist.append({"id": f"C{len(run.floors) + 1}", "question": "Estimate computed from the floors and the storey height and roof type entered", "evidence": "", "status": "open"})


def settle(run: Run, item: str, status: str = "proven") -> None:
    """Mark a checklist item as settled (proven or assumed) unless it is already."""
    entry = next((c for c in run.checklist if c["id"] == item), None)
    if entry and entry["status"] in ("open", "escalated"):
        entry["status"] = status


def add_fact(run: Run, name: str, value, unit: str = "", source: str = "computed", basis: str = "", item: str | None = None) -> dict:
    """Record one value. The latest value for a name replaces the earlier one; an assumed value is also logged as an assumption."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    fact = {"item": item, "name": name, "value": value, "unit": unit, "source": source, "basis": basis,
            "confidence": "high" if source == "user" else "medium" if source == "drawing" else "low"}
    run.facts = [f for f in run.facts if f["name"] != name]
    run.facts.append(fact)
    if source == "assumed":
        run.assumptions.append({"name": name, "value": value, "basis": basis})
    return fact


def ask_user(run: Run, question: str, item: str = "") -> dict:
    """Pause the run for a person. Use it only for what the plans and the entered inputs cannot settle."""
    run.pending = {"item": item, "question": question}
    run.status = "needs_input"
    entry = next((c for c in run.checklist if c["id"] == item), None)
    if entry:
        entry["status"] = "escalated"
    return {"paused": True, "question": question}


def assume_floor_like_ground(run: Run, floor: str) -> dict:
    """Fallback when an upper floor cannot be read: assume it repeats the ground floor. Recorded as an assumption with the reason, so the estimate says so."""
    ground = (run.data.get("floors") or {}).get(run.floors[0]["name"])
    if not ground:
        return {"error": "The ground floor must be read first."}
    if floor not in {f["name"] for f in run.floors}:
        return {"error": f"No floor named {floor}."}
    run.data.setdefault("floors", {})[floor] = {**ground, "name": floor, "assumed_like_ground": True}
    add_fact(run, f"floor_{floor}_like_ground", True, source="assumed", basis=f"the {floor} floor could not be read from its plan; assumed to repeat the ground floor")
    settle(run, next((c["id"] for c in run.checklist if f"the {floor} floor" in c["question"]), ""), "assumed")
    return {"floor": floor, "assumed_like_ground": True}


TOOLS = {
    "ask_user": (ask_user, 'question: str: pause for a person, only for what the plans and entered inputs cannot settle'),
    "assume_floor_like_ground": (assume_floor_like_ground, "floor: str: fallback for an upper floor that cannot be read: assume it repeats the ground floor (flagged)"),
}
