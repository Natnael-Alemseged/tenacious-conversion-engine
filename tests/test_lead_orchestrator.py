from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.workflows.lead_orchestrator import LeadOrchestrator, _build_subject, _require_bench_gate


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
    orc.sms.send_sms.return_value = {"SMSMessageData": {"Message": "ok", "Recipients": []}}
    orc.email_suppression = MagicMock()
    orc.sms_suppression = MagicMock()
    orc.conversations = MagicMock()
    orc.conversations.enabled = False
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


def test_require_bench_gate_raises_when_false() -> None:
    with pytest.raises(ValueError, match="bench"):
        _require_bench_gate(bench_to_brief_gate_passed=False, operation="test_op")


def test_require_bench_gate_passes_when_true() -> None:
    _require_bench_gate(bench_to_brief_gate_passed=True, operation="test_op")


def test_send_outbound_email_raises_when_bench_gate_false() -> None:
    """High-confidence non-exploratory leads must not send when bench gate is failed."""
    orc = _make_orchestrator()
    with patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True):
        with pytest.raises(ValueError, match="[Bb]ench"):
            orc.send_outbound_email(
                to_email="test@example.com",
                company_name="Acme",
                signal_summary="signals",
                icp_segment=1,
                confidence=0.9,
                bench_to_brief_gate_passed=False,
            )
    orc.resend.send_email.assert_not_called()


def test_send_outbound_email_allows_exploratory_without_bench_gate() -> None:
    """Exploratory leads (segment 0 / low confidence) bypass bench gate with hedged copy."""
    orc = _make_orchestrator()
    with patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True):
        result = orc.send_outbound_email(
            to_email="test@example.com",
            company_name="Acme",
            signal_summary="signals",
            icp_segment=0,
            confidence=0.3,
            bench_to_brief_gate_passed=True,
        )
    assert result.get("id") or orc.resend.send_email.called


def test_send_warm_lead_sms_suppresses_after_three_unanswered_attempts(tmp_path) -> None:
    from datetime import UTC, datetime

    orc = _make_orchestrator()
    # Simulate conversations returning 3 prior outbound SMS with no inbound reply.
    t0 = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    t2 = datetime(2026, 4, 22, 9, 0, tzinfo=UTC)
    orc.conversations.enabled = True
    orc.conversations.fetch_recent_messages.return_value = [
        {"direction": "outbound", "channel": "sms", "sent_at": t0},
        {"direction": "outbound", "channel": "sms", "sent_at": t1},
        {"direction": "outbound", "channel": "sms", "sent_at": t2},
    ]
    orc.conversations.fetch_events.return_value = []
    orc.conversations.fetch_state.return_value = None

    with (
        patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True),
        patch("agent.workflows.lead_orchestrator.append_outbound_event"),
        patch("agent.workflows.lead_orchestrator.append_policy_event"),
    ):
        orc.send_warm_lead_sms(
            to_phone="+254700000001",
            company_name="Acme",
            scheduling_hint="Thursday works",
            prior_email_replied=True,
            thread_id="thread-abc",
        )

    orc.sms_suppression.suppress.assert_called_once_with(
        "+254700000001", reason="cadence_exhausted"
    )
    orc.conversations.insert_event.assert_called_once()
    call_kwargs = orc.conversations.insert_event.call_args.kwargs
    assert call_kwargs["event_type"] == "sms_cadence_exhausted"
