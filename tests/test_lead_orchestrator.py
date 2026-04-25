from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.workflows.lead_orchestrator import LeadOrchestrator, _build_subject


def test_subject_under_60_chars_unchanged() -> None:
    subj = _build_subject("Acme", 1)
    assert len(subj) <= 60
    assert "Acme" in subj


def test_subject_long_company_name_truncated_p015() -> None:
    long_name = "NovaCure Machine Learning Infrastructure"
    for seg in range(5):
        subj = _build_subject(long_name, seg)
        assert len(subj) <= 60, f"seg={seg} subject too long ({len(subj)}): {subj!r}"


def test_subject_medium_company_name_truncated() -> None:
    medium_name = "DataBridge Analytics Corporation"
    for seg in range(5):
        subj = _build_subject(medium_name, seg)
        assert len(subj) <= 60, f"seg={seg} subject too long ({len(subj)}): {subj!r}"


def test_subject_unknown_segment_uses_fallback() -> None:
    subj = _build_subject("Acme", 99)
    assert len(subj) <= 60
    assert "Acme" in subj


def _make_orchestrator():
    orc = LeadOrchestrator.__new__(LeadOrchestrator)
    orc.hubspot = MagicMock()
    orc.calcom = MagicMock()
    orc.langfuse = MagicMock()
    orc.langfuse.trace_workflow.return_value.__enter__ = lambda s, *a: s
    orc.langfuse.trace_workflow.return_value.__exit__ = MagicMock(return_value=False)
    orc.langfuse.span.return_value.__enter__ = lambda s, *a: None
    orc.langfuse.span.return_value.__exit__ = MagicMock(return_value=False)
    orc.resend = MagicMock()
    orc.resend.send_email.return_value = {"id": "test-id"}
    orc.sms = MagicMock()
    orc.reply_handler = None
    orc.bounce_handler = None
    return orc


def test_segment_confidence_produces_direct_phrasing() -> None:
    orc = _make_orchestrator()
    captured = {}

    def capture(**kwargs):
        captured["html"] = kwargs.get("html", "")
        return {"id": "x"}

    orc.resend.send_email.side_effect = capture
    with patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True):
        orc.send_outbound_email(
            to_email="test@example.com",
            company_name="Acme",
            signal_summary="12 open Python roles",
            icp_segment=1,
            segment_confidence=0.9,
            bench_to_brief_gate_passed=True,
        )
    assert "Based on the signals" not in captured["html"]


def test_overall_confidence_used_when_segment_confidence_absent() -> None:
    orc = _make_orchestrator()
    captured = {}

    def capture(**kwargs):
        captured["html"] = kwargs.get("html", "")
        return {"id": "x"}

    orc.resend.send_email.side_effect = capture
    with patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True):
        orc.send_outbound_email(
            to_email="test@example.com",
            company_name="Acme",
            signal_summary="some signals",
            icp_segment=1,
            confidence=0.6,
            bench_to_brief_gate_passed=True,
        )
    assert "Based on the signals" in captured["html"]
