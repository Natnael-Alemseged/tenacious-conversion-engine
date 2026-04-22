from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class ResendClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.resend.com",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.resend_api_key
        self.from_email = settings.resend_from_email
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=self._headers(),
            timeout=timeout,
            transport=transport,
        )

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        reply_to: str | None = None,
        from_email: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_email or self.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        response = self.client.post("/emails", json=payload)
        response.raise_for_status()
        return response.json()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
