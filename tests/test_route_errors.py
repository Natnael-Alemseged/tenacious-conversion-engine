import httpx
from fastapi.testclient import TestClient

from agent.api.routes import bookings, webhooks
from agent.main import app
from agent.workflows.booking_crm_writeback import BookingCrmWritebackError


class FailingBookingOrchestrator:
    def book_discovery_call(self, **kwargs) -> dict:
        raise httpx.ConnectError("connection refused")


class BookingOkCrmWritebackFailsOrchestrator:
    def book_discovery_call(self, **kwargs) -> dict:
        raise BookingCrmWritebackError(
            booking={"status": "success", "data": {"uid": "cal_uid_9"}},
            contact_identifier="jane@example.com",
            attempts=3,
            failures=[TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")],
        )


class BookingMissingUidOrchestrator:
    def book_discovery_call(self, **kwargs) -> dict:
        raise ValueError("Cal.com booking response is missing a booking uid.")


class FailingWebhookOrchestrator:
    def handle_email(self, event) -> dict:
        raise httpx.ConnectError("connection refused")

    def handle_sms(self, event) -> dict:
        raise httpx.ConnectError("connection refused")


class CapturingWebhookOrchestrator:
    def __init__(self) -> None:
        self.email_events = []
        self.resend = object()

    def handle_email(self, event) -> dict:
        self.email_events.append(event)
        return {"identifier": event.from_email}

    def handle_email_bounce(self, event) -> dict:
        self.email_events.append(event)
        return {"identifier": event.from_email}


def test_bookings_route_returns_502_when_booking_ok_but_crm_writeback_fails(monkeypatch) -> None:
    monkeypatch.setattr(bookings, "orchestrator", BookingOkCrmWritebackFailsOrchestrator())
    client = TestClient(app)

    response = client.post(
        "/bookings/discovery-call",
        json={
            "attendee_name": "Jane Doe",
            "attendee_email": "jane@example.com",
            "start": "2026-04-25T09:00:00Z",
        },
    )

    assert response.status_code == 502
    body = response.json()["detail"]
    assert "calendar booking was created" in body["message"].lower()
    assert body["crm_writeback"]["attempts"] == 3
    assert body["crm_writeback"]["contact_identifier"] == "jane@example.com"
    assert body["booking"]["uid"] == "cal_uid_9"


def test_bookings_route_returns_503_on_unreachable_provider(monkeypatch) -> None:
    monkeypatch.setattr(bookings, "orchestrator", FailingBookingOrchestrator())
    client = TestClient(app)

    response = client.post(
        "/bookings/discovery-call",
        json={
            "attendee_name": "Jane Doe",
            "attendee_email": "jane@example.com",
            "start": "2026-04-25T09:00:00Z",
        },
    )

    assert response.status_code == 503
    assert "unreachable" in response.json()["detail"].lower()


def test_bookings_route_returns_400_on_missing_booking_uid(monkeypatch) -> None:
    monkeypatch.setattr(bookings, "orchestrator", BookingMissingUidOrchestrator())
    client = TestClient(app)

    response = client.post(
        "/bookings/discovery-call",
        json={
            "attendee_name": "Jane Doe",
            "attendee_email": "jane@example.com",
            "start": "2026-04-25T09:00:00Z",
        },
    )

    assert response.status_code == 400
    assert "missing a booking uid" in response.json()["detail"]


def test_email_webhook_returns_503_on_unreachable_upstream(monkeypatch) -> None:
    monkeypatch.setattr(webhooks, "orchestrator", FailingWebhookOrchestrator())
    monkeypatch.setattr(webhooks.settings, "resend_webhook_signing_secret", "")
    client = TestClient(app)

    response = client.post(
        "/webhooks/email",
        json={"event_type": "email.replied", "from_email": "lead@example.com"},
    )

    assert response.status_code == 503


def test_email_webhook_accepts_raw_resend_received_payload(monkeypatch) -> None:
    orchestrator = CapturingWebhookOrchestrator()
    monkeypatch.setattr(webhooks, "orchestrator", orchestrator)

    class FakeResendClient:
        def get_received_email(self, email_id: str) -> dict:
            assert email_id == "re_123"
            return {
                "id": email_id,
                "from": "Lead <lead@example.com>",
                "to": ["anything@talauminai.resend.app"],
                "subject": "Re: hello world",
                "text": "Interested",
                "message_id": "<msg-123>",
            }

    monkeypatch.setattr(orchestrator, "resend", FakeResendClient())
    monkeypatch.setattr(webhooks.settings, "resend_webhook_signing_secret", "")
    client = TestClient(app)

    response = client.post(
        "/webhooks/email",
        json={
            "type": "email.received",
            "created_at": "2026-04-24T12:00:00Z",
            "data": {
                "email_id": "re_123",
                "from": "Lead <lead@example.com>",
                "to": ["anything@talauminai.resend.app"],
                "subject": "Re: hello world",
                "message_id": "<msg-123>",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert orchestrator.email_events
    assert orchestrator.email_events[0].event_type == "email.replied"
    assert orchestrator.email_events[0].body == "Interested"


def test_email_webhook_ignores_non_actionable_resend_events(monkeypatch) -> None:
    monkeypatch.setattr(webhooks.settings, "resend_webhook_signing_secret", "")
    monkeypatch.setattr(webhooks, "orchestrator", CapturingWebhookOrchestrator())
    client = TestClient(app)

    response = client.post(
        "/webhooks/email",
        json={
            "type": "email.sent",
            "created_at": "2026-04-24T12:00:00Z",
            "data": {
                "email_id": "em_123",
                "from": "Acme <onboarding@resend.dev>",
                "to": ["natnaela@10academy.org"],
                "subject": "hello world",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "event_type": "email.sent"}


def test_sms_webhook_returns_503_on_unreachable_upstream(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(webhooks, "orchestrator", FailingWebhookOrchestrator())
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        str(tmp_path / "suppression.json"),
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "hello", "id": "1"},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "upstream_unreachable"
    assert detail["error"]["provider"]["kind"] == "http"
