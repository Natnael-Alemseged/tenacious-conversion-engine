from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class AfricasTalkingSmsClient:
    def __init__(
        self,
        username: str | None = None,
        api_key: str | None = None,
        short_code: str | None = None,
        base_url: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.username = (
            username if username is not None else settings.africastalking_username
        )
        self.api_key = api_key if api_key is not None else settings.africastalking_api_key
        self.short_code = (
            short_code if short_code is not None else settings.africastalking_short_code
        )
        resolved_base_url = base_url or self._default_base_url(self.username)
        self.client = httpx.Client(
            base_url=resolved_base_url.rstrip("/"),
            headers=self._headers(),
            timeout=timeout,
            transport=transport,
        )

    def send_sms(
        self,
        *,
        to_phone: str,
        message: str,
        enqueue: bool = False,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "username": self.username,
            "to": to_phone,
            "message": message,
            "bulkSMSMode": 1,
        }
        if self.short_code:
            data["from"] = self.short_code
        if enqueue:
            data["enqueue"] = 1

        response = self.client.post("/version1/messaging", data=data)
        response.raise_for_status()
        return response.json()

    def _default_base_url(self, username: str) -> str:
        if username == "sandbox":
            return "https://api.sandbox.africastalking.com"
        return "https://api.africastalking.com"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["apiKey"] = self.api_key
        return headers
