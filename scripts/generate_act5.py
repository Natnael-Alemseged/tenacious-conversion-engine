from __future__ import annotations

import argparse
import json
from pathlib import Path

from act5.claims import build_claims
from act5.pdf import render_memo_pdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-final", action="store_true")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()

    claims = build_claims(strict_final=args.strict_final)
    draft = not args.final
    citations = {
        "tenacious_baseline_numbers": {
            "kind": "tenacious_internal",
            "path": "tenacious_sales_data/seed/baseline_numbers.md",
        },
        "tenacious_bench_summary": {
            "kind": "tenacious_internal",
            "path": "tenacious_sales_data/seed/bench_summary.json",
            "as_of": "2026-04-21",
        },
        "tau2_leaderboard_feb_2026": {
            "kind": "published",
            "label": "τ²-Bench retail leaderboard reference (Feb 2026)",
            "url": None,
        },
    }
    evidence = {
        "draft": draft,
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "citations": citations,
        "claims": [
            {
                "claim_id": c.claim_id,
                "label": c.label,
                "value": c.value,
                "unit": c.unit,
                "sources": c.sources,
                "derivation": c.derivation,
                "recompute": c.recompute,
            }
            for c in claims
        ],
        "memo": {
            "page_1": {
                "title": "The Decision",
                "sections": [
                    {
                        "id": "tau2_performance",
                        "claim_ids": [
                            "tau2_sealed_pass_at_1",
                            "day1_sealed_baseline_pass_at_1",
                            "tau2_auto_opt_sealed_pass_at_1",
                            "tau2_published_reference_pass_at_1",
                            "tau2_task_duration_p50_seconds",
                        ],
                    },
                    {"id": "cpl", "claim_ids": ["total_cost_usd", "cost_per_qualified_lead"]},
                    {
                        "id": "stalled_thread_delta",
                        "claim_ids": [
                            "stalled_thread_rate",
                            "tenacious_manual_stalled_thread_baseline",
                        ],
                    },
                    {
                        "id": "competitive_gap",
                        "claim_ids": [
                            "competitive_gap_reply_rate",
                            "generic_reply_rate",
                            "competitive_gap_reply_rate_delta",
                            "top_quartile_signal_grounded_reply_rate_range",
                        ],
                    },
                    {
                        "id": "annualized_impact",
                        "claim_ids": [
                            "annualized_revenue_impact_one_segment",
                            "annualized_revenue_impact_two_segments",
                            "annualized_revenue_impact_all_four_segments",
                        ],
                    },
                    {"id": "pilot", "claim_ids": ["pilot_recommendation"]},
                ],
            },
            "page_2": {
                "title": "The Skeptic’s Appendix",
                "sections": [
                    {"id": "failure_modes", "claim_ids": []},
                    {"id": "public_signal_lossiness", "claim_ids": []},
                    {"id": "gap_analysis_risks", "claim_ids": []},
                    {"id": "brand_reputation_unit_econ", "claim_ids": []},
                    {"id": "honest_failure", "claim_ids": []},
                    {"id": "kill_switch", "claim_ids": []},
                ],
            },
        },
    }
    Path("act5").mkdir(exist_ok=True)
    act5_graph = Path("act5/evidence_graph.json")
    act5_graph.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    # Root exports for grading compatibility.
    Path("evidence_graph.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    render_memo_pdf(evidence=evidence, out_path=Path("act5/memo.pdf"))
    Path("memo.pdf").write_bytes(Path("act5/memo.pdf").read_bytes())
    print("Wrote act5/memo.pdf + act5/evidence_graph.json (+ root exports).")


if __name__ == "__main__":
    main()
