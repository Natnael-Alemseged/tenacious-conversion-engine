import json

import httpx

from agent.integrations.calcom import BOOKINGS_API_VERSION, SLOTS_API_VERSION, CalComClient


def test_create_booking_uses_calcom_v2_api() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["api_version"] = request.headers.get("cal-api-version")
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(201, json={"status": "success", "data": {"uid": "booking_uid_123"}})

    client = CalComClient(
        api_key="cal_test",
        event_type_id=42,
        transport=httpx.MockTransport(handler),
    )

    response = client.create_booking(
        name="Jane Doe",
        email="jane@example.com",
        start="2026-04-25T09:00:00Z",
        timezone="Africa/Addis_Ababa",
        length_in_minutes=30,
        phone_number="+251911000000",
        metadata={"source": "conversion-engine"},
    )

    assert response["data"]["uid"] == "booking_uid_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/v2/bookings"
    assert captured["authorization"] == "Bearer cal_test"
    assert captured["api_version"] == BOOKINGS_API_VERSION
    assert captured["json"]["eventTypeId"] == 42
    assert captured["json"]["attendee"]["email"] == "jane@example.com"
    assert captured["json"]["metadata"]["source"] == "conversion-engine"


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
            json={"status": "success", "data": {"2026-04-25": [{"start": "2026-04-25T09:00:00Z"}]}},
        )

    client = CalComClient(
        api_key="cal_test",
        event_type_id=42,
        transport=httpx.MockTransport(handler),
    )

    response = client.get_available_slots(
        start="2026-04-25",
        end="2026-04-26",
        timezone="Africa/Addis_Ababa",
    )

    assert "2026-04-25" in response["data"]
    assert captured["method"] == "GET"
    assert captured["path"] == "/v2/slots"
    assert captured["authorization"] == "Bearer cal_test"
    assert captured["api_version"] == SLOTS_API_VERSION
    assert captured["params"]["eventTypeId"] == "42"
    assert captured["params"]["timeZone"] == "Africa/Addis_Ababa"
