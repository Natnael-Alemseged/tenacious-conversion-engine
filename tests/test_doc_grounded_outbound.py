from __future__ import annotations

from agent.enrichment.schemas import (
    AiMaturitySignal,
    BenchSignal,
    BenchSignalData,
    ConfidenceMeta,
    CrunchbaseBriefData,
    CrunchbaseSignal,
    EnrichmentSignals,
    FundingSignal,
    HiringSignalBrief,
    JobPostsSignal,
    LayoffsSignal,
    LeadershipSignal,
)
from agent.workflows.doc_grounded_outbound import build_doc_grounded_cold_outbound


def _meta() -> ConfidenceMeta:
    return ConfidenceMeta(tier="high", factors={}, rationale_codes=())


def sample_brief_for_cold() -> HiringSignalBrief:
    """Valid brief with nested Pydantic models (open roles + funding for grounded facts)."""
    m = _meta()
    return HiringSignalBrief(
        company_name="Acme Labs",
        company_domain="acme.example",
        generated_at="2026-04-25T00:00:00+00:00",
        icp_segment=1,
        segment_confidence=0.82,
        overall_confidence=0.81,
        overall_confidence_weighted=0.83,
        signals=EnrichmentSignals(
            crunchbase=CrunchbaseSignal(
                data=CrunchbaseBriefData(uuid="cb_1", categories=["software"]),
                confidence=0.8,
                confidence_meta=m,
            ),
            funding=FundingSignal(
                data=[{"investment_type": "series_b", "announced_on": "2026-02-01"}],
                confidence=0.85,
                confidence_meta=m,
            ),
            layoffs=LayoffsSignal(data=[], confidence=0.0, confidence_meta=m),
            leadership_change=LeadershipSignal(data=[], confidence=0.0, confidence_meta=m),
            job_posts=JobPostsSignal(
                data={"open_roles": 6},
                confidence=0.72,
                confidence_meta=m,
            ),
            ai_maturity=AiMaturitySignal(
                score=2,
                justification="Public AI hiring mix.",
                confidence=0.7,
                confidence_meta=m,
            ),
            bench=BenchSignal(
                data=BenchSignalData(
                    bench_to_brief_gate_passed=True,
                    required_stacks=["python"],
                    available_counts={"python": 2},
                ),
                confidence=0.75,
                confidence_meta=m,
            ),
        ),
        honesty_flags=[],
    )


def test_cold_outbound_uses_cold_md_refs() -> None:
    brief = sample_brief_for_cold()
    cal = "https://cal.com/example/15min"
    draft = build_doc_grounded_cold_outbound(brief=brief, first_name="Elena", cal_link=cal, step=1)
    assert cal in draft.text
    cold_refs = [
        r
        for r in draft.doc_sources_used
        if "tenacious_sales_data/seed/email_sequences/cold.md#" in r.replace("\\", "/")
    ]
    assert cold_refs, f"expected cold.md ref, got {draft.doc_sources_used}"


def test_cold_outbound_word_count_constraint() -> None:
    brief = sample_brief_for_cold()
    cal = "https://cal.com/example/15min"
    draft = build_doc_grounded_cold_outbound(brief=brief, first_name="Elena", cal_link=cal, step=1)
    assert draft.word_count <= 140
    assert "circling back" not in draft.text.lower()


def test_cold_outbound_step3_includes_grounding_fact() -> None:
    brief = sample_brief_for_cold()
    cal = "https://cal.com/example/15min"
    draft = build_doc_grounded_cold_outbound(brief=brief, first_name="Elena", cal_link=cal, step=3)
    assert "6 open roles" in draft.text
    assert not draft.fallback_used
