from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.models.webhooks import InboundSmsEvent
from agent.workflows.doc_grounded_outbound import OutboundDraft
from agent.workflows.lead_orchestrator import (
    LeadOrchestrator,
    _build_subject,
    _require_bench_gate,
)


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
    thread = MagicMock()
    thread.thread_id = "thread-123"
    orc.conversations.resolve_thread_for_sms.return_value = thread
    orc.conversations.fetch_state.return_value = None
    orc.conversations.fetch_recent_messages.return_value = []
    orc.conversations.fetch_events.return_value = []
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


def test_inbound_sms_booking_intent_includes_calcom_link_when_configured() -> None:
    orc = _make_orchestrator()
    orc.sms.send_sms.return_value = {"ok": True}
    orc.hubspot.upsert_contact.return_value = {"id": "hs-1"}

    event = InboundSmsEvent(
        from_number="+251911000000",
        to="12345",
        text="Can we schedule a call?",
        date="2026-01-01 00:00:00",
        message_id="sms-1",
    )

    with patch("agent.workflows.lead_orchestrator.settings.calcom_username", "tenacious-demo"):
        with patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", False):
            with patch(
                "agent.workflows.lead_orchestrator.settings.outbound_sink_phone",
                "+15555550123",
            ):
                result = orc.handle_sms(event)

    assert result["reply"] != {"status": "skipped", "reason": "outbound_disabled_without_sink"}
    assert orc.sms.send_sms.call_count == 1
    sent_message = orc.sms.send_sms.call_args.kwargs.get("message", "")
    assert "https://cal.com/tenacious-demo" in sent_message


def test_send_outbound_email_cold_doc_grounded_variant_calls_builder(
    monkeypatch,
) -> None:
    orc = _make_orchestrator()
    captured: dict = {}

    def fake_builder(*, brief, first_name, cal_link, step):
        captured["brief"] = brief
        captured["first_name"] = first_name
        captured["cal_link"] = cal_link
        captured["step"] = step
        return OutboundDraft(
            subject="Doc-grounded subject line",
            html="<p>doc html</p>",
            text="doc text",
            doc_sources_used=["urn:ref:a"],
            fallback_used=True,
            constraint_violations=["banned_phrase:x"],
            word_count=3,
        )

    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.build_doc_grounded_cold_outbound",
        fake_builder,
    )
    with (
        patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True),
        patch("agent.workflows.lead_orchestrator.settings.calcom_username", "fixtureuser"),
    ):
        orc.send_outbound_email(
            to_email="jane.doe@example.com",
            company_name="Acme Corp",
            signal_summary="12 open Python roles",
            icp_segment=1,
            bench_to_brief_gate_passed=True,
            outbound_variant="cold_doc_grounded_email_1",
        )
    assert captured["step"] == 1
    assert captured["first_name"] == "Jane"
    assert captured["brief"].company_name == "Acme Corp"
    assert captured["brief"].icp_segment == 1
    assert captured["cal_link"] == "https://cal.com/fixtureuser."
    orc.resend.send_email.assert_called_once()
    send_kw = orc.resend.send_email.call_args[1]
    assert send_kw["subject"] == "Doc-grounded subject line"
    assert send_kw["html"] == "<p>doc html</p>"
    assert send_kw["text"] == "doc text"


def test_send_outbound_email_cold_doc_grounded_merges_telemetry_metadata(
    monkeypatch,
) -> None:
    orc = _make_orchestrator()
    step_seen: list[int] = []

    def fake_builder(*, brief, first_name, cal_link, step):
        step_seen.append(step)
        return OutboundDraft(
            subject="S",
            html="<p>x</p>",
            text="x",
            doc_sources_used=["src/a.md#h1"],
            fallback_used=False,
            constraint_violations=[],
            word_count=1,
        )

    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.build_doc_grounded_cold_outbound",
        fake_builder,
    )
    with (
        patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True),
        patch("agent.workflows.lead_orchestrator.settings.calcom_username", "u"),
    ):
        result = orc.send_outbound_email(
            to_email="a@b.com",
            company_name="Co",
            signal_summary="sig",
            bench_to_brief_gate_passed=True,
            outbound_variant="cold_doc_grounded_email_2",
            metadata={"thread_id": "t1"},
        )
    assert step_seen == [2]
    assert result["metadata"]["thread_id"] == "t1"
    assert result["metadata"]["doc_sources_used"] == ["src/a.md#h1"]
    assert result["metadata"]["fallback_used"] is False
    assert result["metadata"]["constraint_violations"] == []
    assert result["metadata"]["kb_variant"] == "cold"


def test_send_outbound_email_cold_doc_grounded_skips_builder_when_overrides(
    monkeypatch,
) -> None:
    orc = _make_orchestrator()
    called: list[str] = []

    def fake_builder(**kwargs):
        called.append("yes")
        raise AssertionError("should not be called when overrides present")

    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.build_doc_grounded_cold_outbound",
        fake_builder,
    )
    with patch("agent.workflows.lead_orchestrator.settings.outbound_enabled", True):
        orc.send_outbound_email(
            to_email="x@y.com",
            company_name="Acme",
            signal_summary="sig",
            bench_to_brief_gate_passed=True,
            outbound_variant="cold_doc_grounded_email_1",
            subject_override="Custom subject",
        )
    assert called == []
