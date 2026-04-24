from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent.core.config import settings


class HubSpotMcpError(RuntimeError):
    def __init__(self, message: str, *, error_kind: str = "mcp_error") -> None:
        super().__init__(message)
        self.error_kind = error_kind
        self.detail = message


class HubSpotClient:
    """HubSpot CRM client backed by the @hubspot/mcp-server MCP process.

    The MCP session runs in a dedicated background thread. Shutdown is
    coordinated via an asyncio.Event so anyio cancel scopes are always
    exited from the task that entered them.
    """

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token if access_token is not None else settings.hubspot_api_key
        self._session: ClientSession | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event: asyncio.Event | None = None
        self._lock = threading.Lock()
        self._http: httpx.Client | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
            if self._thread is not None:
                self._thread.join(timeout=10)

    # ── MCP transport ─────────────────────────────────────────────────────────

    def _run(self, coro: Any) -> Any:
        if self._loop is not None:
            return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30)
        return asyncio.run(coro)

    async def _call_tool(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is not None:
            result = await self._session.call_tool(tool, arguments)
            return self._decode_result(result)

        # Render deployments frequently lack Node/npm toolchains; fall back to direct
        # HubSpot HTTP calls in that case so webhooks don't 500.
        if shutil.which("npx") is None:
            return self._call_tool_http(tool, arguments)

        env = {**os.environ, "PRIVATE_APP_ACCESS_TOKEN": self._access_token}
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@hubspot/mcp-server"],
            env=env,
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
                return self._decode_result(result)

    def _http_client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                base_url=settings.hubspot_base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=20.0,
            )
        return self._http

    def _call_tool_http(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Minimal direct-HTTP implementation for the MCP tools we use.
        This keeps the rest of the app working when MCP stdio transport isn't available.
        """
        client = self._http_client()

        if tool == "hubspot-search-objects":
            object_type = arguments.get("objectType")
            if object_type != "contacts":
                raise HubSpotMcpError(
                    f"HTTP fallback only supports contacts search (got {object_type})."
                )
            r = client.post("/crm/v3/objects/contacts/search", json=arguments)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HubSpotMcpError(str(exc), error_kind="http_status") from exc
            return r.json()

        if tool == "hubspot-batch-create-objects":
            object_type = arguments.get("objectType")
            if object_type != "contacts":
                raise HubSpotMcpError(
                    f"HTTP fallback only supports contacts create (got {object_type})."
                )
            r = client.post("/crm/v3/objects/contacts/batch/create", json=arguments)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HubSpotMcpError(str(exc), error_kind="http_status") from exc
            return r.json()

        if tool == "hubspot-batch-update-objects":
            object_type = arguments.get("objectType")
            if object_type != "contacts":
                raise HubSpotMcpError(
                    f"HTTP fallback only supports contacts update (got {object_type})."
                )
            r = client.post("/crm/v3/objects/contacts/batch/update", json=arguments)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HubSpotMcpError(str(exc), error_kind="http_status") from exc
            return r.json()

        raise HubSpotMcpError(
            f"HTTP fallback does not implement tool={tool}.", error_kind="unsupported_tool"
        )

    def _decode_result(self, result: Any) -> dict[str, Any]:
        texts: list[str] = []
        for item in result.content:
            text = getattr(item, "text", None)
            if text:
                texts.append(text)
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        if getattr(result, "isError", False):
            message = "\n".join(texts) if texts else "Unknown HubSpot MCP error"
            raise HubSpotMcpError(message)
        if texts:
            return {"raw": "\n".join(texts)}
        return {}

    def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._run(self._call_tool(tool, arguments))

    # ── public API ────────────────────────────────────────────────────────────

    def _stringify_properties(self, properties: dict[str, Any]) -> dict[str, str]:
        return {key: str(value) for key, value in properties.items() if value is not None}

    def upsert_contact(
        self,
        identifier: str,
        source: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        props = self._stringify_properties(dict(properties or {}))
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
            "hubspot-search-objects",
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
            "hubspot-batch-create-objects",
            {"objectType": "contacts", "inputs": [{"properties": properties}]},
        )
        results = result.get("results", [])
        if results:
            return results[0]
        raise HubSpotMcpError(
            "HubSpot MCP create contact returned no results.",
            error_kind="empty_results",
        )

    def update_contact(self, contact_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        result = self._call(
            "hubspot-batch-update-objects",
            {
                "objectType": "contacts",
                "inputs": [
                    {"id": str(contact_id), "properties": self._stringify_properties(properties)}
                ],
            },
        )
        results = result.get("results", [])
        if results:
            return results[0]
        raise HubSpotMcpError(
            "HubSpot MCP update contact returned no results.",
            error_kind="empty_results",
        )
