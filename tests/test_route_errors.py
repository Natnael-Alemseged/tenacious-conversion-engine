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
    client = TestClient(app)

    response = client.post(
        "/webhooks/email",
        json={"from_email": "lead@example.com"},
    )

    assert response.status_code == 503


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
