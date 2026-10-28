import argparse

from plan2cost.agent.loop import resume, run_agent
from plan2cost.agent.state import Run


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Plan2Cost agent on a drawing set (PDF).")
    ap.add_argument("--pdf")
    ap.add_argument("--objective", default="Produce a BoQ with an approximate cost for this building.")
    ap.add_argument("--resume", help="run id to continue")
    ap.add_argument("--answer", help="your answer, when the run is waiting for you")
    ap.add_argument("--turns", type=int, default=30)
    args = ap.parse_args()
    if args.resume:
        run = resume(Run.load(args.resume), args.answer, max_turns=args.turns)
    else:
        run = run_agent(Run.new(args.pdf, args.objective), max_turns=args.turns)
    print(f"run {run.id}: {run.status} after {run.turn} turns  ({run.dir}/trace.md)")
    if run.pending:
        print("QUESTION:", run.pending["question"], f'\nAnswer with: --resume {run.id} --answer "..."')


if __name__ == "__main__":
    main()
