from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest

from agent.integrations.resend_email import ResendSendError
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent
from agent.workflows.lead_orchestrator import LeadOrchestrator


class FakeSpan:
    def __init__(self, recorder: list[tuple[str, dict]]) -> None:
        self.recorder = recorder

    def update(self, *, output):
        self.recorder.append(("span.update", output))


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    @contextmanager
    def trace_workflow(self, name: str, payload: dict):
        self.events.append(("trace.start", {"name": name, "payload": payload}))
        yield {"trace_id": "trace_123"}
        self.events.append(("trace.end", {"name": name}))

    @contextmanager
    def span(self, name: str, input: dict, output: dict | None = None):
        self.events.append(("span.start", {"name": name, "input": input, "output": output}))
        span = FakeSpan(self.events)
        yield span
        self.events.append(("span.end", {"name": name}))


class FakeHubSpotClient:
    def upsert_contact(self, identifier: str, source: str, properties: dict | None = None) -> dict:
        return {"identifier": identifier, "source": source, "properties": properties or {}}


class FakeResendClient:
    def send_email(self, **kwargs) -> dict:
        return {"id": "email_123", **kwargs}


class FakeSmsClient:
    def send_sms(self, **kwargs) -> dict:
        return {"SMSMessageData": {"Recipients": [{"status": "Success"}]}, **kwargs}


class FakeCalComClient:
    def create_booking(self, **kwargs) -> dict:
        return {"status": "success", "data": {"uid": "booking_uid_123"}, **kwargs}


class NoUidCalComClient:
    def create_booking(self, **kwargs) -> dict:
        return {"status": "success", "data": {}, **kwargs}


def test_handle_email_records_trace_and_span() -> None:
    langfuse = FakeLangfuseClient()
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=langfuse,
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    result = orchestrator.handle_email(
        InboundEmailEvent(
            from_email="lead@example.com",
            to="team@example.com",
            subject="Interested",
            body="Tell me more",
        )
    )

    assert result["identifier"] == "lead@example.com"
    assert ("trace.end", {"name": "handle_email"}) in langfuse.events
    assert (
        "span.start",
        {
            "name": "hubspot.upsert_contact",
            "input": {"identifier": "lead@example.com", "source": "email"},
            "output": None,
        },
    ) in langfuse.events


def test_send_follow_up_sms_records_trace_and_returns_sms_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_enabled",
        True,
    )
    langfuse = FakeLangfuseClient()
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=langfuse,
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    result = orchestrator.send_warm_lead_sms(
        to_phone="+251911000000",
        company_name="Acme",
        scheduling_hint="We found a relevant hiring signal.",
        prior_email_replied=True,
    )

    assert result["to_phone"] == "+251911000000"
    assert ("trace.end", {"name": "send_warm_lead_sms"}) in langfuse.events
    assert any(event[0] == "span.update" for event in langfuse.events)


def test_send_follow_up_sms_logs_success(caplog, monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_enabled",
        True,
    )
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    with caplog.at_level(logging.INFO, logger="agent.workflows.lead_orchestrator"):
        orchestrator.send_warm_lead_sms(
            to_phone="+251911000000",
            company_name="Acme",
            scheduling_hint="We found a relevant hiring signal.",
            prior_email_replied=True,
        )

    records = [r for r in caplog.records if r.getMessage() == "send_warm_lead_sms"]
    assert records
    assert records[-1].wf_outcome == "success"
    assert records[-1].wf_channel == "sms"


def test_book_discovery_call_retries_transient_hubspot_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("agent.workflows.booking_crm_writeback.time.sleep", lambda _s: None)

    class FlakyHubSpotClient:
        def __init__(self) -> None:
            self.tries = 0

        def upsert_contact(
            self, identifier: str, source: str, properties: dict | None = None
        ) -> dict:
            self.tries += 1
            if self.tries < 2:
                raise TimeoutError("hubspot mcp")
            return {"identifier": identifier, "source": source, "properties": properties or {}}

    hubspot = FlakyHubSpotClient()
    orchestrator = LeadOrchestrator(
        hubspot=hubspot,
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    result = orchestrator.book_discovery_call(
        attendee_name="Jane Doe",
        attendee_email="jane@example.com",
        start="2026-04-25T09:00:00Z",
        timezone="Africa/Addis_Ababa",
    )

    assert result["data"]["uid"] == "booking_uid_123"
    assert hubspot.tries == 2
    assert any(
        e[0] == "span.update" and isinstance(e[1], dict) and e[1].get("crm_writeback_attempts") == 2
        for e in orchestrator.langfuse.events
    )


def test_book_discovery_call_records_trace_and_returns_booking() -> None:
    langfuse = FakeLangfuseClient()
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=langfuse,
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    result = orchestrator.book_discovery_call(
        attendee_name="Jane Doe",
        attendee_email="jane@example.com",
        start="2026-04-25T09:00:00Z",
        timezone="Africa/Addis_Ababa",
    )

    assert result["data"]["uid"] == "booking_uid_123"
    assert ("trace.end", {"name": "book_discovery_call"}) in langfuse.events
    assert (
        "span.start",
        {
            "name": "calcom.create_booking",
            "input": {
                "attendee_name": "Jane Doe",
                "attendee_email": "jane@example.com",
                "start": "2026-04-25T09:00:00Z",
                "timezone": "Africa/Addis_Ababa",
                "length_in_minutes": 30,
            },
            "output": None,
        },
    ) in langfuse.events


def test_book_discovery_call_logs_missing_booking_uid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=NoUidCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    with caplog.at_level(logging.ERROR, logger="agent.workflows.lead_orchestrator"):
        with pytest.raises(ValueError, match="missing a booking uid"):
            orchestrator.book_discovery_call(
                attendee_name="Jane Doe",
                attendee_email="jane@example.com",
                start="2026-04-25T09:00:00Z",
            )

    records = [r for r in caplog.records if r.getMessage() == "book_discovery_call"]
    assert records
    assert records[-1].wf_phase == "booking_response"
    assert records[-1].wf_outcome == "failure"


def test_inbound_reply_handlers_can_be_registered() -> None:
    recorded: list[tuple[str, str, str]] = []

    def reply_handler(
        channel: str,
        result: dict,
        event: InboundEmailEvent | InboundSmsEvent,
    ) -> None:
        identifier = event.from_email if hasattr(event, "from_email") else event.from_number
        recorded.append((channel, result["identifier"], identifier))

    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
        reply_handler=reply_handler,
    )

    orchestrator.handle_email(
        InboundEmailEvent(
            from_email="lead@example.com",
            subject="Interested",
        )
    )
    orchestrator.handle_sms(
        InboundSmsEvent(
            from_number="+251911000000",
            text="sounds good",
        )
    )

    assert recorded == [
        ("email", "lead@example.com", "lead@example.com"),
        ("sms", "+251911000000", "+251911000000"),
    ]


def _make_orchestrator(
    monkeypatch,
) -> tuple[LeadOrchestrator, FakeLangfuseClient, FakeHubSpotClient]:
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_enabled",
        True,
    )
    langfuse = FakeLangfuseClient()
    hubspot = FakeHubSpotClient()
    orch = LeadOrchestrator(
        hubspot=hubspot,
        calcom=FakeCalComClient(),
        langfuse=langfuse,
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )
    return orch, langfuse, hubspot


def test_send_outbound_email_segment1_direct_phrasing(monkeypatch) -> None:
    orch, _, _ = _make_orchestrator(monkeypatch)
    result = orch.send_outbound_email(
        to_email="lead@acme.com",
        company_name="Acme",
        signal_summary="Series B announced last month.",
        icp_segment=1,
        confidence=0.9,
    )
    assert result["subject"] == "Acme: scaling after your recent raise"
    assert "Based on" not in result["html"]
    assert "early indicators" not in result["html"]
    assert "Series B announced last month." in result["html"]


def test_send_outbound_email_segment2_hedged_phrasing(monkeypatch) -> None:
    orch, _, _ = _make_orchestrator(monkeypatch)
    result = orch.send_outbound_email(
        to_email="lead@corp.com",
        company_name="Corp",
        signal_summary="120 engineers laid off in Q4.",
        icp_segment=2,
        confidence=0.6,
    )
    assert result["subject"] == "Corp: doing more with your current team"
    assert "Based on the signals we've seen" in result["html"]


def test_send_outbound_email_exploratory_phrasing_low_confidence(monkeypatch) -> None:
    orch, _, _ = _make_orchestrator(monkeypatch)
    result = orch.send_outbound_email(
        to_email="lead@startup.io",
        company_name="Startup",
        signal_summary="Some AI hiring detected.",
        icp_segment=0,
        confidence=0.2,
    )
    assert result["subject"] == "Startup: quick thought"
    assert "early indicators" in result["html"]


def test_send_outbound_email_none_segment_falls_back_to_general(monkeypatch) -> None:
    orch, _, _ = _make_orchestrator(monkeypatch)
    result = orch.send_outbound_email(
        to_email="lead@co.com",
        company_name="Co",
        signal_summary="Signal here.",
        icp_segment=None,
    )
    assert result["subject"] == "Co: quick thought"


def test_outbound_email_routes_to_sink_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_enabled",
        False,
    )
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_sink_email",
        "sink@tenacious.example",
    )
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )
    result = orchestrator.send_outbound_email(
        to_email="real-prospect@example.com",
        company_name="Co",
        signal_summary="Signal here.",
        icp_segment=0,
        confidence=0.6,
    )
    assert result["to_email"] == "sink@tenacious.example"
    assert result["tags"]["outbound_mode"] == "sink"


def test_outbound_sms_routes_to_sink_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_enabled",
        False,
    )
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_sink_phone",
        "+15555550123",
    )
    langfuse = FakeLangfuseClient()
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=langfuse,
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )
    result = orchestrator.send_warm_lead_sms(
        to_phone="+251911000000",
        company_name="Acme",
        scheduling_hint="We found a relevant hiring signal.",
        prior_email_replied=True,
    )
    assert result["to_phone"] == "+15555550123"


def test_outbound_email_requires_sink_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_enabled",
        False,
    )
    monkeypatch.setattr(
        "agent.workflows.lead_orchestrator.settings.outbound_sink_email",
        "",
    )
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    with pytest.raises(ValueError, match="no sink is configured for channel=email"):
        orchestrator.send_outbound_email(
            to_email="real-prospect@example.com",
            company_name="Co",
            signal_summary="Signal here.",
            icp_segment=0,
            confidence=0.6,
        )


def test_outbound_email_requires_bench_gate(monkeypatch) -> None:
    orch, _, _ = _make_orchestrator(monkeypatch)

    with pytest.raises(ValueError, match="Bench-to-brief gate failed"):
        orch.send_outbound_email(
            to_email="lead@co.com",
            company_name="Co",
            signal_summary="Signal here.",
            icp_segment=1,
            bench_to_brief_gate_passed=False,
        )


def test_send_outbound_email_logs_structured_error_on_resend_failure(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orch, langfuse, _ = _make_orchestrator(monkeypatch)

    class FailResend:
        def send_email(self, **kwargs: object) -> dict:
            raise ResendSendError(400, '{"error":"bad"}', error_kind="upstream_http")

    orch.resend = FailResend()

    with caplog.at_level(logging.ERROR, logger="agent.workflows.lead_orchestrator"):
        with pytest.raises(ResendSendError):
            orch.send_outbound_email(
                to_email="lead@acme.com",
                company_name="Acme",
                signal_summary="Signal.",
                icp_segment=2,
                confidence=0.7,
            )

    err_records = [r for r in caplog.records if r.getMessage() == "outbound_email_send"]
    assert err_records, "expected structured outbound_email_send error log"
    rec = err_records[-1]
    assert rec.oe_component == "outbound_email"
    assert rec.oe_outcome == "failure"
    assert rec.oe_phase == "resend"
    assert rec.oe_http_status == "400"
    assert rec.oe_error_kind == "upstream_http"
    assert rec.oe_intended_email_domain == "acme.com"
    assert rec.oe_icp_segment == "2"

    span_updates = [e for e in langfuse.events if e[0] == "span.update"]
    assert any(
        isinstance(e[1], dict) and e[1].get("ok") is False and e[1].get("http_status") == 400
        for e in span_updates
    )


def test_send_outbound_email_logs_success_metric(caplog, monkeypatch) -> None:
    orch, _, _ = _make_orchestrator(monkeypatch)
    with caplog.at_level(logging.INFO, logger="agent.workflows.lead_orchestrator"):
        orch.send_outbound_email(
            to_email="lead@acme.com",
            company_name="Acme",
            signal_summary="Signal.",
            icp_segment=1,
            confidence=0.9,
        )
    info_records = [r for r in caplog.records if r.getMessage() == "outbound_email_send"]
    assert info_records
    assert info_records[-1].oe_outcome == "success"
    assert info_records[-1].oe_phase == "complete"
    assert info_records[-1].oe_metric == "outbound_email.send"


def test_booking_requires_bench_gate() -> None:
    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
    )

    with pytest.raises(ValueError, match="Bench-to-brief gate failed"):
        orchestrator.book_discovery_call(
            attendee_name="Jane Doe",
            attendee_email="jane@example.com",
            start="2026-04-25T09:00:00Z",
            bench_to_brief_gate_passed=False,
        )


def test_bounce_handler_can_be_registered() -> None:
    recorded: list[tuple[str, str, str]] = []

    def bounce_handler(
        channel: str,
        result: dict,
        event: InboundEmailEvent | InboundSmsEvent,
    ) -> None:
        assert isinstance(event, InboundEmailEvent)
        recorded.append((channel, result["identifier"], event.event_type))

    orchestrator = LeadOrchestrator(
        hubspot=FakeHubSpotClient(),
        calcom=FakeCalComClient(),
        langfuse=FakeLangfuseClient(),
        resend=FakeResendClient(),
        sms=FakeSmsClient(),
        bounce_handler=bounce_handler,
    )

    orchestrator.handle_email_bounce(
        InboundEmailEvent(
            event_type="email.bounced",
            from_email="lead@example.com",
            bounce_type="hard_bounce",
        )
    )

    assert recorded == [("email_bounce", "lead@example.com", "email.bounced")]
