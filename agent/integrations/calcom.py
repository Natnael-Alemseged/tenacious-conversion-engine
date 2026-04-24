from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from agent.core.config import settings

SLOTS_API_VERSION = "2024-09-04"


class CalComClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        event_type_id: int | None = None,
        username: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.calcom_api_key
        self.base_url = (base_url if base_url is not None else settings.calcom_base_url).rstrip("/")
        self.event_type_id = (
            event_type_id if event_type_id is not None else settings.calcom_event_type_id
        )
        self.username = username if username is not None else settings.calcom_username
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=timeout,
            transport=transport,
        )

    def create_booking(
        self,
        *,
        name: str,
        email: str,
        start: str,
        timezone: str = "UTC",
        length_in_minutes: int = 30,
        event_type_id: int | None = None,
        phone_number: str | None = None,
        language: str = "en",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(UTC)
        end_dt = start_dt + timedelta(minutes=length_in_minutes)
        payload: dict[str, Any] = {
            "eventTypeId": event_type_id or self.event_type_id,
            "responses": {"name": name, "email": email},
            "start": start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "timeZone": timezone,
            "language": language,
            "metadata": metadata or {},
        }
        if self.username:
            payload["user"] = self.username
        response = self.client.post("/book/event", json=payload)
        response.raise_for_status()
        return response.json()

    def get_available_slots(
        self,
        *,
        start: str,
        end: str,
        timezone: str = "UTC",
        event_type_id: int | None = None,
    ) -> dict[str, Any]:
        response = self.client.get(
            "/v2/slots",
            headers={"cal-api-version": SLOTS_API_VERSION},
            params={
                "eventTypeId": event_type_id or self.event_type_id,
                "start": start,
                "end": end,
                "timeZone": timezone,
            },
        )
        response.raise_for_status()
        return response.json()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
