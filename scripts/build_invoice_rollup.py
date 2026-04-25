from __future__ import annotations

import argparse
from pathlib import Path

from eval.cost_ledger import write_rollup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="eval/runs/invoice_summary.json",
        help="Output rollup invoice path.",
    )
    parser.add_argument(
        "--include-auto-opt",
        action="store_true",
        help="Include latest eval/runs/auto_opt/*/invoice_summary.json in rollup.",
    )
    args = parser.parse_args()

    invoices: list[Path] = []
    if args.include_auto_opt:
        auto_opt_dir = Path("eval/runs/auto_opt")
        if auto_opt_dir.exists():
            candidates = sorted(auto_opt_dir.glob("*/invoice_summary.json"))
            if candidates:
                invoices.append(candidates[-1])

    if not invoices:
        raise SystemExit("No invoices found to roll up.")

    out_path = Path(args.out)
    write_rollup(invoices=invoices, out_path=out_path)
    print(f"Wrote invoice rollup to {out_path}")


if __name__ == "__main__":
    main()
