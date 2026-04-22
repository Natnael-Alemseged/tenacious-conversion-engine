from fastapi.testclient import TestClient

from agent.api.routes import bookings
from agent.main import app


class FakeOrchestrator:
    def __init__(self) -> None:
        self.last_payload: dict | None = None

    def book_discovery_call(self, **kwargs) -> dict:
        self.last_payload = kwargs
        return {"status": "success", "data": {"uid": "booking_uid_123"}}


def test_book_discovery_call_route_returns_booking(monkeypatch) -> None:
    fake = FakeOrchestrator()
    monkeypatch.setattr(bookings, "orchestrator", fake)

    client = TestClient(app)
    response = client.post(
        "/bookings/discovery-call",
        json={
            "attendee_name": "Jane Doe",
            "attendee_email": "jane@example.com",
            "start": "2026-04-25T09:00:00Z",
            "timezone": "Africa/Addis_Ababa",
            "length_in_minutes": 30,
            "attendee_phone": "+251911000000",
            "metadata": {"source": "api"},
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["uid"] == "booking_uid_123"
    assert fake.last_payload is not None
    assert fake.last_payload["attendee_email"] == "jane@example.com"
