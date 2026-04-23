from __future__ import annotations

import asyncio
import json
import os
import threading
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent.core.config import settings


class HubSpotClient:
    """HubSpot CRM client backed by the @hubspot/mcp-server MCP process.

    Calls search_crm_objects and manage_crm_objects via the MCP protocol.
    The async MCP session runs in a dedicated background thread so the public
    interface remains fully synchronous — no changes needed in callers.
    """

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token if access_token is not None else settings.hubspot_api_key
        self._session: ClientSession | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _ensure_started(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, daemon=True, name="hubspot-mcp")
            thread.start()
            self._loop = loop
            self._thread = thread
            future = asyncio.run_coroutine_threadsafe(self._async_start(), loop)
            future.result(timeout=30)

    async def _async_start(self) -> None:
        self._exit_stack = AsyncExitStack()
        env = {**os.environ, "HUBSPOT_ACCESS_TOKEN": self._access_token}
        server_params = StdioServerParameters(
            command="npx",
            args=["@hubspot/mcp-server"],
            env=env,
        )
        read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    def close(self) -> None:
        if self._loop is not None and self._session is not None:
            future = asyncio.run_coroutine_threadsafe(self._async_close(), self._loop)
            future.result(timeout=10)
            self._loop.call_soon_threadsafe(self._loop.stop)

    async def _async_close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._session = None

    # ── MCP transport ─────────────────────────────────────────────────────────

    def _run(self, coro: Any) -> Any:
        self._ensure_started()
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30)

    async def _call_tool(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self._session is not None
        result = await self._session.call_tool(tool, arguments)
        for item in result.content:
            text = getattr(item, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}
        return {}

    def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._run(self._call_tool(tool, arguments))

    # ── public API (same interface as the former REST client) ─────────────────

    def upsert_contact(
        self,
        identifier: str,
        source: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        props = dict(properties or {})
        props.setdefault("lead_source", source)

        if "@" in identifier:
            props["email"] = identifier
            existing = self._search_contact(property_name="email", value=identifier)
            if existing:
                return self.update_contact(existing["id"], props)
            return self._create_contact(props)

        props["phone"] = identifier
        existing = self.search_contact_by_phone(identifier)
        if existing:
            return self.update_contact(existing["id"], props)
        return self._create_contact(props)

    def _search_contact(self, *, property_name: str, value: str) -> dict[str, Any] | None:
        result = self._call(
            "search_crm_objects",
            {
                "objectType": "contacts",
                "filterGroups": [
                    {"filters": [{"propertyName": property_name, "operator": "EQ", "value": value}]}
                ],
                "limit": 1,
                "properties": ["email", "phone", "firstname", "lastname"],
            },
        )
        results = result.get("results", [])
        return results[0] if results else None

    def search_contact_by_phone(self, phone_number: str) -> dict[str, Any] | None:
        return self._search_contact(property_name="phone", value=phone_number)

    def _create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        result = self._call(
            "manage_crm_objects",
            {"createRequest": {"objects": [{"objectType": "contacts", "properties": properties}]}},
        )
        results = result.get("results", [result])
        return results[0] if results else result

    def update_contact(self, contact_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._call(
            "manage_crm_objects",
            {
                "updateRequest": {
                    "objects": [
                        {
                            "objectId": int(contact_id),
                            "objectType": "contacts",
                            "properties": properties,
                        }
                    ]
                }
            },
        )
