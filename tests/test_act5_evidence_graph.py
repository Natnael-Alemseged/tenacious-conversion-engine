import json
import subprocess
from pathlib import Path


def _regen_act5(*, final: bool = False) -> None:
    cmd = ["uv", "run", "python", "scripts/generate_act5.py"]
    if final:
        cmd.append("--final")
    subprocess.check_call(cmd)


def test_evidence_graph_includes_memo_and_citations():
    _regen_act5()
    evidence = json.loads(Path("act5/evidence_graph.json").read_text(encoding="utf-8"))
    assert "claims" in evidence and isinstance(evidence["claims"], list)
    # This will fail until generate_act5.py emits the new structure.
    assert "memo" in evidence and isinstance(evidence["memo"], dict)
    assert "citations" in evidence and isinstance(evidence["citations"], dict)


def test_required_act5_claim_ids_present():
    _regen_act5()
    evidence = json.loads(Path("act5/evidence_graph.json").read_text(encoding="utf-8"))
    claim_ids = {c["claim_id"] for c in evidence["claims"]}

    required = {
        "tau2_sealed_pass_at_1",
        "day1_sealed_baseline_pass_at_1",
        "tau2_auto_opt_sealed_pass_at_1",
        "tau2_published_reference_pass_at_1",
        "stalled_thread_rate",
        "tenacious_manual_stalled_thread_baseline",
        "competitive_gap_reply_rate",
        "generic_reply_rate",
        "competitive_gap_reply_rate_delta",
        "top_quartile_signal_grounded_reply_rate_range",
        "annualized_revenue_impact_one_segment",
        "annualized_revenue_impact_two_segments",
        "annualized_revenue_impact_all_four_segments",
        "pilot_recommendation",
        "tau2_task_duration_p50_seconds",
    }
    missing = required - claim_ids
    assert not missing, f"Missing claims: {sorted(missing)}"


def test_generate_act5_final_sets_draft_false():
    _regen_act5(final=True)
    evidence = json.loads(Path("act5/evidence_graph.json").read_text(encoding="utf-8"))
    assert evidence["draft"] is False
