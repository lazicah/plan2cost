"""Scoring harness: compare extracted quantities with the author's surveyed ground truth.

Case layout:  eval/cases/<id>/plan.(png|jpg)  +  eval/cases/<id>/truth.json
truth.json:   {"floor_area_m2": 120.5, "wall_area_m2": 310.0}
"""
import argparse
import json
from pathlib import Path


def pct_error(pred: float, truth: float) -> float:
    return abs(pred - truth) / truth * 100 if truth else float("inf")


def score_case(pred: dict, truth: dict) -> dict:
    return {k: round(pct_error(pred.get(k, 0), v), 1) for k, v in truth.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="eval/cases")
    args = ap.parse_args()
    cases = sorted(p for p in Path(args.cases).iterdir() if p.is_dir())
    if not cases:
        print("No cases yet. Add eval/cases/<id>/plan.png and truth.json")
        return
    for c in cases:
        truth = json.loads((c / "truth.json").read_text())
        pred = {}  # TODO: run agent extraction on the plan image
        print(c.name, score_case(pred, truth))


if __name__ == "__main__":
    main()
