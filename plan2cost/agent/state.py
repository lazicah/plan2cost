"""A run is a folder under workspace/runs/ holding its saved state, so it can pause for a person and resume."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

RUNS_DIR = Path("workspace/runs")
STATUSES = ("running", "needs_input", "paused", "done", "failed")


@dataclass
class Run:
    id: str
    pdf: str
    objective: str
    status: str = "running"
    turn: int = 0
    messages: list = field(default_factory=list)  # the model's whole conversation; the model itself is stateless
    checklist: list = field(default_factory=list)
    facts: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    data: dict = field(default_factory=dict)  # things tools read from the drawings: openings, levels, girth
    pending: dict | None = None  # the question a person must answer
    result: dict | None = None

    @property
    def dir(self) -> Path:
        return RUNS_DIR / self.id

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "run.json").write_text(json.dumps(self.__dict__, indent=2, default=str))

    def trace(self, line: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / "trace.md").open("a") as f:
            f.write(line.rstrip() + "\n")

    @classmethod
    def new(cls, pdf: str, objective: str) -> "Run":
        return cls(id=time.strftime("%Y%m%d-%H%M%S"), pdf=pdf, objective=objective)

    @classmethod
    def load(cls, run_id: str) -> "Run":
        return cls(**json.loads((RUNS_DIR / run_id / "run.json").read_text()))
