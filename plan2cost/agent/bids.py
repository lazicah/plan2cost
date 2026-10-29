"""Audit contractors' bids returned on the unpriced bill a run issued: python -m plan2cost.agent.bids --run <id> bid1.xlsx bid2.pdf ..."""
import argparse

from plan2cost.kit.progress import Run
from plan2cost.tools.audit import audit_bids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="the run that issued the bill")
    ap.add_argument("bids", nargs="+", help="returned bills: .xlsx (read directly), or PDF/image")
    args = ap.parse_args()
    out = audit_bids(Run.load(args.run), args.bids)
    for name, a in out["bids"].items():
        print(f"{name}: {a['total_at_issued_quantities']:,.2f} at issued quantities; {len(a['unpriced_items'])} unpriced; flags {a['counts']}")
    print(f"saved workspace/runs/{args.run}/tender_audit.json")


if __name__ == "__main__":
    main()
