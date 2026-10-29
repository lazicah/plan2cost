import argparse

from plan2cost.agent.loop import resume, run_agent
from plan2cost.kit.progress import ROOF_TYPES, Run


def parse_floor(arg: str) -> dict:
    """name=path or name=path.pdf:page, e.g. ground=plan.pdf:2 or first=first-floor.jpg"""
    name, _, rest = arg.partition("=")
    path, page = rest, 1
    head, sep, tail = rest.rpartition(":")
    if sep and tail.isdigit() and head.lower().endswith(".pdf"):
        path, page = head, int(tail)
    return {"name": name.strip().lower(), "file": path, "page": page}


def main() -> None:
    ap = argparse.ArgumentParser(description="Estimate a building from its floor plans.")
    ap.add_argument("--floor", action="append", help="a floor plan: name=file or name=file.pdf:page; repeat for each floor, lowest first", default=[])
    ap.add_argument("--storey-height", type=float, help="floor to floor, in metres")
    ap.add_argument("--roof", choices=ROOF_TYPES, help="the roof type")
    ap.add_argument("--pitch", type=float, help="roof pitch in degrees (optional)")
    ap.add_argument("--overhang", type=float, help="roof overhang in metres (optional)")
    ap.add_argument("--rates", help="rate set: owerri or asaba (see data/rates.json)")
    ap.add_argument("--quote", help="a contractor's quote (PDF or image) to audit against the BoQ")
    ap.add_argument("--resume", help="run id to continue")
    ap.add_argument("--answer", help="your answer, when the run is waiting for you")
    ap.add_argument("--turns", type=int, default=20)
    args = ap.parse_args()
    if args.resume:
        run = resume(Run.load(args.resume), args.answer, max_turns=args.turns)
    else:
        if not args.floor or not args.storey_height or not args.roof:
            ap.error("give at least one --floor, and --storey-height and --roof")
        run = run_agent(Run.new([parse_floor(f) for f in args.floor], {"storey_height_m": args.storey_height, "roof_type": args.roof, "pitch_deg": args.pitch, "overhang_m": args.overhang, "rate_set": args.rates},
                                quote=args.quote), max_turns=args.turns)
    print(f"run {run.id}: {run.status} after {run.turn} turns  ({run.dir}/trace.md)")
    if run.pending:
        print("QUESTION:", run.pending["question"], f'\nAnswer with: --resume {run.id} --answer "..."')


if __name__ == "__main__":
    main()
