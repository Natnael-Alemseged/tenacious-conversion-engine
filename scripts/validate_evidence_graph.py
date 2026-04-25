from __future__ import annotations

import argparse
import json
from pathlib import Path

from act5.claims import build_claims


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-final", action="store_true")
    args = parser.parse_args()

    evidence_path = Path("act5/evidence_graph.json")
    if not evidence_path.exists():
        raise SystemExit("Missing act5/evidence_graph.json. Run scripts/generate_act5.py first.")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    want = {c.claim_id: c for c in build_claims(strict_final=args.strict_final)}
    have = {c["claim_id"]: c for c in evidence.get("claims", [])}

    missing = [cid for cid in want.keys() if cid not in have]
    if missing:
        raise SystemExit(f"Missing claims in evidence graph: {missing}")

    # Very strict equality for now; later we can add structured tolerances per claim.
    for cid, claim in want.items():
        if have[cid]["value"] != claim.value:
            raise SystemExit(
                f"Claim mismatch for {cid}: have={have[cid]['value']} want={claim.value}"
            )

    print("Evidence graph validated successfully.")


if __name__ == "__main__":
    main()
