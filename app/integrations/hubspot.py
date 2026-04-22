from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class HubSpotClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.hubspot_api_key
        self.base_url = (base_url if base_url is not None else settings.hubspot_base_url).rstrip(
            "/"
        )
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=timeout,
            transport=transport,
        )

    def upsert_contact(
        self,
        identifier: str,
        source: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        props = dict(properties or {})
        if "@" in identifier:
            props["email"] = identifier
            response = self.client.post(
                "/crm/v3/objects/contacts/batch/upsert",
                json={
                    "inputs": [
                        {
                            "id": identifier,
                            "idProperty": "email",
                            "properties": props,
                        }
                    ]
                },
            )
            response.raise_for_status()
            return response.json()

        props["phone"] = identifier

        existing_contact = self.search_contact_by_phone(identifier)
        if existing_contact is not None:
            return self.update_contact(existing_contact["id"], props)

        response = self.client.post(
            "/crm/v3/objects/contacts",
            json={"properties": props},
        )
        response.raise_for_status()
        return response.json()

    def search_contact_by_phone(self, phone_number: str) -> dict[str, Any] | None:
        response = self.client.post(
            "/crm/v3/objects/contacts/search",
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "phone",
                                "operator": "EQ",
                                "value": phone_number,
                            }
                        ]
                    }
                ],
                "limit": 1,
                "properties": ["email", "phone", "firstname", "lastname"],
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return results[0] if results else None

    def update_contact(self, contact_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        response = self.client.patch(
            f"/crm/v3/objects/contacts/{contact_id}",
            json={"properties": properties},
        )
        response.raise_for_status()
        return response.json()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
