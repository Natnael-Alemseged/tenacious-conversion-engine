import json

import httpx

from agent.integrations.calcom import SLOTS_API_VERSION, CalComClient


def test_create_booking_posts_to_internal_book_event() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"uid": "booking_uid_123", "status": "ACCEPTED"})

    client = CalComClient(
        api_key="cal_test",
        event_type_id=42,
        username="testuser",
        transport=httpx.MockTransport(handler),
    )

    response = client.create_booking(
        name="Jane Doe",
        email="jane@example.com",
        start="2026-04-27T09:00:00Z",
        timezone="Africa/Addis_Ababa",
        length_in_minutes=30,
        metadata={"source": "conversion-engine"},
    )

    assert response["uid"] == "booking_uid_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/book/event"
    assert captured["authorization"] == "Bearer cal_test"
    assert captured["json"]["eventTypeId"] == 42
    assert captured["json"]["responses"]["email"] == "jane@example.com"
    assert captured["json"]["user"] == "testuser"
    assert captured["json"]["metadata"]["source"] == "conversion-engine"
    assert captured["json"]["end"] == "2026-04-27T09:30:00.000Z"


def test_get_available_slots_uses_calcom_v2_slots_api() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["api_version"] = request.headers.get("cal-api-version")
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"status": "success", "data": {"2026-04-27": [{"start": "2026-04-27T09:00:00Z"}]}},
        )

    client = CalComClient(
        api_key="cal_test",
        event_type_id=42,
        transport=httpx.MockTransport(handler),
    )

    response = client.get_available_slots(
        start="2026-04-27",
        end="2026-04-28",
        timezone="Africa/Addis_Ababa",
    )

    assert "2026-04-27" in response["data"]
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v2/slots"
    assert captured["authorization"] == "Bearer cal_test"
    assert captured["api_version"] == SLOTS_API_VERSION
    assert captured["params"]["eventTypeId"] == "42"
    assert captured["params"]["timeZone"] == "Africa/Addis_Ababa"
