import json

import httpx

from agent.integrations.hubspot import HubSpotClient


def test_upsert_contact_by_email_uses_batch_upsert() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"results": [{"id": "123"}]})

    client = HubSpotClient(
        api_key="test-token",
        transport=httpx.MockTransport(handler),
    )

    response = client.upsert_contact("lead@example.com", source="email")

    assert response["results"][0]["id"] == "123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/crm/v3/objects/contacts/batch/upsert"
    assert captured["authorization"] == "Bearer test-token"
    assert captured["json"]["inputs"][0]["idProperty"] == "email"
    assert captured["json"]["inputs"][0]["properties"]["email"] == "lead@example.com"


def test_upsert_contact_by_phone_searches_then_creates() -> None:
    requests: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        requests.append((request.method, request.url.path, body))
        if request.url.path == "/crm/v3/objects/contacts/search":
            return httpx.Response(200, json={"results": []})
        if request.url.path == "/crm/v3/objects/contacts":
            return httpx.Response(201, json={"id": "phone-contact-1"})
        raise AssertionError(f"Unexpected request to {request.url.path}")

    client = HubSpotClient(
        api_key="test-token",
        transport=httpx.MockTransport(handler),
    )

    response = client.upsert_contact("+251911000000", source="sms")

    assert response["id"] == "phone-contact-1"
    assert requests[0][1] == "/crm/v3/objects/contacts/search"
    assert requests[0][2]["filterGroups"][0]["filters"][0]["propertyName"] == "phone"
    assert requests[1][1] == "/crm/v3/objects/contacts"
    assert requests[1][2]["properties"]["phone"] == "+251911000000"
