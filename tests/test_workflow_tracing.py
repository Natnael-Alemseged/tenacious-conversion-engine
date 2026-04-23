from __future__ import annotations

from contextlib import contextmanager

from agent.models.webhooks import InboundEmailEvent
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


def test_send_follow_up_sms_records_trace_and_returns_sms_response() -> None:
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
