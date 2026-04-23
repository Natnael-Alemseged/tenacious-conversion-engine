from __future__ import annotations

from contextlib import contextmanager

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
