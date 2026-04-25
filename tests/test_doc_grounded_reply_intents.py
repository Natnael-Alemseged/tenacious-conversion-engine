from __future__ import annotations

from agent.enrichment.schemas import HiringSignalBrief
from agent.models.webhooks import InboundEmailEvent
from agent.workflows.doc_grounded_reply import build_doc_grounded_inbound_reply
from agent.workflows.reply_intent import ReplyIntentResult


def _minimal_brief(*, company_name: str = "Acme", icp_segment: int = 0) -> HiringSignalBrief:
    meta: dict = {"tier": "high", "factors": {}, "rationale_codes": []}
    return HiringSignalBrief.model_validate(
        {
            "company_name": company_name,
            "company_domain": "acme.com",
            "generated_at": "2026-04-25T00:00:00+00:00",
            "icp_segment": icp_segment,
            "segment_confidence": 0.4,
            "overall_confidence": 0.5,
            "overall_confidence_weighted": 0.5,
            "signals": {
                "crunchbase": {
                    "data": {"uuid": "x", "categories": []},
                    "confidence": 0.0,
                    "confidence_meta": meta,
                },
                "funding": {"data": [], "confidence": 0.0, "confidence_meta": meta},
                "layoffs": {"data": [], "confidence": 0.0, "confidence_meta": meta},
                "leadership_change": {"data": [], "confidence": 0.0, "confidence_meta": meta},
                "job_posts": {
                    "data": {"open_roles": 0},
                    "confidence": 0.0,
                    "confidence_meta": meta,
                },
                "ai_maturity": {
                    "score": 0,
                    "justification": "",
                    "confidence": 0.0,
                    "confidence_meta": meta,
                },
                "bench": {
                    "data": {
                        "bench_to_brief_gate_passed": False,
                        "required_stacks": [],
                        "gaps": [],
                        "available_counts": {},
                    },
                    "confidence": 0.0,
                    "confidence_meta": meta,
                },
            },
        }
    )


def _base_event(*, body: str, subject: str = "Hello") -> InboundEmailEvent:
    return InboundEmailEvent(
        from_email="prospect@acme.com",
        to="team@gettenacious.com",
        subject=subject,
        body=body,
    )


def test_pricing_intent_cites_pricing_sheet() -> None:
    out = build_doc_grounded_inbound_reply(
        event=_base_event(
            body="What is your monthly rate for a senior engineer? I need a rough budget."
        ),
        brief=_minimal_brief(),
        booking_requested=False,
        booking_result=None,
        requested_booking_start=None,
        intent=None,
    )
    assert any("pricing_sheet.md" in ref for ref in out.doc_sources_used)


def test_proof_intent_cites_case_studies() -> None:
    out = build_doc_grounded_inbound_reply(
        event=_base_event(
            body="Do you have case studies or customer references in AdTech? Looking for proof."
        ),
        brief=_minimal_brief(),
        booking_requested=False,
        booking_result=None,
        requested_booking_start=None,
        intent=ReplyIntentResult(intent="other", confidence=0.0, notes=""),
    )
    assert any("case_studies.md" in ref for ref in out.doc_sources_used)


def test_discovery_strong_match_includes_segment_transcript() -> None:
    out = build_doc_grounded_inbound_reply(
        event=_base_event(
            body="What happens next in your process? We need a timeline for onboarding."
        ),
        brief=_minimal_brief(icp_segment=2),
        booking_requested=False,
        booking_result=None,
        requested_booking_start=None,
        intent=ReplyIntentResult(intent="other", confidence=0.0, notes=""),
    )
    assert any("transcript_02_mid_market_restructure.md" in ref for ref in out.doc_sources_used)


def test_discovery_segment_zero_omits_transcript() -> None:
    out = build_doc_grounded_inbound_reply(
        event=_base_event(
            body="What does your process look like? How does this work for new clients?"
        ),
        brief=_minimal_brief(icp_segment=0),
        booking_requested=False,
        booking_result=None,
        requested_booking_start=None,
        intent=None,
    )
    assert not any("discovery_transcripts/" in ref for ref in out.doc_sources_used)


def test_pricing_objection_includes_objection_transcript() -> None:
    out = build_doc_grounded_inbound_reply(
        event=_base_event(
            body=(
                "This sounds too expensive compared to our last vendor. What is the pricing anyway?"
            )
        ),
        brief=_minimal_brief(),
        booking_requested=False,
        booking_result=None,
        requested_booking_start=None,
        intent=None,
    )
    assert any("transcript_05_objection_heavy.md" in ref for ref in out.doc_sources_used)
