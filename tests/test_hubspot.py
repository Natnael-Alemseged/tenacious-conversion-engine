"""Tests for HubSpotClient (MCP-backed).

Instead of mocking HTTP transports, these tests inject a mock MCP session
so we can verify the correct MCP tool names and argument shapes are used.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any
from unittest.mock import MagicMock

from agent.integrations.hubspot import HubSpotClient


def _make_client(responses: dict[str, Any]) -> tuple[HubSpotClient, list[tuple[str, dict]]]:
    """Return a client wired to a mock MCP session and a call log."""
    calls: list[tuple[str, dict]] = []

    async def mock_call_tool(tool: str, arguments: dict[str, Any]) -> Any:
        calls.append((tool, arguments))
        data = responses.get(tool, {})
        item = MagicMock()
        item.text = json.dumps(data)
        result = MagicMock()
        result.content = [item]
        return result

    mock_session = MagicMock()
    mock_session.call_tool = mock_call_tool

    client = HubSpotClient(access_token="test-token")
    # Wire up a real background event loop + mock session to bypass _ensure_started
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    client._loop = loop
    client._thread = thread
    client._session = mock_session

    return client, calls


# ── upsert by email ───────────────────────────────────────────────────────────


def test_upsert_contact_by_email_creates_when_not_found() -> None:
    client, calls = _make_client(
        {
            "search_crm_objects": {"results": []},
            "manage_crm_objects": {"results": [{"id": "123"}]},
        }
    )

    result = client.upsert_contact("lead@example.com", source="email")

    assert result["id"] == "123"
    assert calls[0][0] == "search_crm_objects"
    assert calls[0][1]["objectType"] == "contacts"
    assert calls[0][1]["filterGroups"][0]["filters"][0]["propertyName"] == "email"
    assert calls[0][1]["filterGroups"][0]["filters"][0]["value"] == "lead@example.com"
    assert calls[1][0] == "manage_crm_objects"
    assert "createRequest" in calls[1][1]
    create_obj = calls[1][1]["createRequest"]["objects"][0]
    assert create_obj["objectType"] == "contacts"
    assert create_obj["properties"]["email"] == "lead@example.com"
    assert create_obj["properties"]["lead_source"] == "email"


def test_upsert_contact_by_email_updates_when_found() -> None:
    client, calls = _make_client(
        {
            "search_crm_objects": {"results": [{"id": "456", "properties": {}}]},
            "manage_crm_objects": {"id": "456"},
        }
    )

    result = client.upsert_contact(
        "existing@example.com", source="email", properties={"company": "Acme"}
    )

    assert result["id"] == "456"
    assert calls[0][0] == "search_crm_objects"
    assert calls[1][0] == "manage_crm_objects"
    assert "updateRequest" in calls[1][1]
    update_obj = calls[1][1]["updateRequest"]["objects"][0]
    assert update_obj["objectId"] == 456
    assert update_obj["objectType"] == "contacts"
    assert update_obj["properties"]["company"] == "Acme"


# ── upsert by phone ───────────────────────────────────────────────────────────


def test_upsert_contact_by_phone_creates_when_not_found() -> None:
    client, calls = _make_client(
        {
            "search_crm_objects": {"results": []},
            "manage_crm_objects": {"results": [{"id": "789"}]},
        }
    )

    result = client.upsert_contact("+251911000000", source="sms")

    assert result["id"] == "789"
    assert calls[0][0] == "search_crm_objects"
    assert calls[0][1]["filterGroups"][0]["filters"][0]["propertyName"] == "phone"
    assert calls[0][1]["filterGroups"][0]["filters"][0]["value"] == "+251911000000"
    assert calls[1][0] == "manage_crm_objects"
    create_obj = calls[1][1]["createRequest"]["objects"][0]
    assert create_obj["properties"]["phone"] == "+251911000000"
    assert create_obj["properties"]["lead_source"] == "sms"


def test_upsert_contact_by_phone_updates_when_found() -> None:
    client, calls = _make_client(
        {
            "search_crm_objects": {"results": [{"id": "101", "properties": {}}]},
            "manage_crm_objects": {"id": "101"},
        }
    )

    result = client.upsert_contact("+251911000000", source="sms")

    assert result["id"] == "101"
    assert calls[1][0] == "manage_crm_objects"
    assert "updateRequest" in calls[1][1]
    assert calls[1][1]["updateRequest"]["objects"][0]["objectId"] == 101


# ── search_contact_by_phone ───────────────────────────────────────────────────


def test_search_contact_by_phone_returns_none_when_not_found() -> None:
    client, _ = _make_client({"search_crm_objects": {"results": []}})
    assert client.search_contact_by_phone("+251911000000") is None


def test_search_contact_by_phone_returns_first_result() -> None:
    contact = {"id": "55", "properties": {"phone": "+251911000000"}}
    client, _ = _make_client({"search_crm_objects": {"results": [contact]}})
    result = client.search_contact_by_phone("+251911000000")
    assert result is not None
    assert result["id"] == "55"


# ── update_contact ────────────────────────────────────────────────────────────


def test_update_contact_sends_update_request() -> None:
    client, calls = _make_client({"manage_crm_objects": {"id": "99"}})

    result = client.update_contact("99", {"firstname": "Jane"})

    assert result["id"] == "99"
    assert calls[0][0] == "manage_crm_objects"
    assert "updateRequest" in calls[0][1]
    obj = calls[0][1]["updateRequest"]["objects"][0]
    assert obj["objectId"] == 99
    assert obj["objectType"] == "contacts"
    assert obj["properties"]["firstname"] == "Jane"
