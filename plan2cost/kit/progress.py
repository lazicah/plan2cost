"""A run is a folder under workspace/runs/ holding its saved state, so it can pause for a person and resume."""
import json
import threading
import time
from dataclasses import dataclass, field, fields
from pathlib import Path

RUNS_DIR = Path("workspace/runs")
_SAVE = threading.Lock()
STATUSES = ("running", "needs_input", "paused", "done", "failed")
ROOF_TYPES = ("gable", "hip", "flat")  # the roof types we hold coefficients for
FINISH_LEVELS = ("standard", "premium")  # which rates apply to tiles, sanitary ware, doors, luminaires and roof covering
FLOOR_NAMES = ("ground", "first", "second", "third", "fourth")


@dataclass
class Run:
    id: str
    objective: str = ""
    floors: list = field(default_factory=list)  # [{"name": "ground", "file": "plan.pdf", "page": 1}], lowest floor first
    inputs: dict = field(default_factory=dict)  # what the user enters: storey_height_m, roof_type, pitch_deg, overhang_m
    quote: str | None = None  # a contractor's quote (PDF or image) to audit against the BoQ, when there is one
    status: str = "running"
    turn: int = 0
    messages: list = field(default_factory=list)  # the model's whole conversation; the model itself is stateless
    checklist: list = field(default_factory=list)
    facts: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    data: dict = field(default_factory=dict)  # what the tools measured: floors, boq, models
    pending: dict | None = None  # the question a person must answer
    result: dict | None = None

    @property
    def dir(self) -> Path:
        return RUNS_DIR / self.id

    def floor(self, name: str) -> dict:
        return next(f for f in self.floors if f["name"] == name)

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with _SAVE:
            (self.dir / "run.json").write_text(json.dumps(self.__dict__, indent=2, default=str))

    def trace(self, line: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / "trace.md").open("a") as f:
            f.write(line.rstrip() + "\n")

    @classmethod
    def new(cls, floors: list, inputs: dict, objective: str = "Estimate the cost of this building from its floor plans.", quote: str | None = None) -> "Run":
        stamp = time.time()
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        while True:  # claim the folder at once, so two runs started in the same second do not share it
            name = time.strftime("%Y%m%d-%H%M%S", time.localtime(stamp))
            try:
                (RUNS_DIR / name).mkdir()
                break
            except FileExistsError:
                stamp += 1
        return cls(id=name, objective=objective, floors=floors, inputs=inputs, quote=quote)

    @classmethod
    def load(cls, run_id: str) -> "Run":
        d = json.loads((RUNS_DIR / run_id / "run.json").read_text())
        return cls(**{k: v for k, v in d.items() if k in {f.name for f in fields(cls)}})  # runs saved by an older layout still open
