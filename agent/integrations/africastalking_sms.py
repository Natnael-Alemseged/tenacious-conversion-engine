from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.core.config import settings

_log = logging.getLogger(__name__)


class AfricasTalkingSendError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error_kind: str = "unknown",
    ) -> None:
        super().__init__(f"Africa's Talking send failed ({status_code}): {message}")
        self.status_code = status_code
        self.error_kind = error_kind
        self.detail = message


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
        self.username = username if username is not None else settings.africastalking_username
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

        _log.debug(
            "africastalking.send_sms",
            extra={
                "sms_component": "africastalking",
                "sms_metric": "send_sms",
                "sms_outcome": "attempt",
                "sms_to": to_phone,
                "sms_username": self.username,
            },
        )
        try:
            response = self.client.post("/version1/messaging", data=data)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise AfricasTalkingSendError(
                    response.status_code,
                    "Expected Africa's Talking JSON object response.",
                    error_kind="malformed_response",
                )
            _log.info(
                "africastalking.send_sms",
                extra={
                    "sms_component": "africastalking",
                    "sms_metric": "send_sms",
                    "sms_outcome": "success",
                    "sms_to": to_phone,
                    "sms_username": self.username,
                    "sms_status_code": response.status_code,
                },
            )
            return body
        except httpx.HTTPStatusError as exc:
            _log.error(
                "africastalking.send_sms",
                extra={
                    "sms_component": "africastalking",
                    "sms_metric": "send_sms",
                    "sms_outcome": "error",
                    "sms_error_kind": "upstream_http",
                    "sms_to": to_phone,
                    "sms_status_code": exc.response.status_code,
                },
                exc_info=exc,
            )
            raise AfricasTalkingSendError(
                exc.response.status_code,
                exc.response.text,
                error_kind="upstream_http",
            ) from exc
        except ValueError as exc:
            _log.error(
                "africastalking.send_sms",
                extra={
                    "sms_component": "africastalking",
                    "sms_metric": "send_sms",
                    "sms_outcome": "error",
                    "sms_error_kind": "malformed_response",
                    "sms_to": to_phone,
                    "sms_status_code": 0,
                },
                exc_info=exc,
            )
            raise AfricasTalkingSendError(
                0,
                f"Invalid JSON from Africa's Talking: {exc}",
                error_kind="malformed_response",
            ) from exc
        except httpx.RequestError as exc:
            _log.error(
                "africastalking.send_sms",
                extra={
                    "sms_component": "africastalking",
                    "sms_metric": "send_sms",
                    "sms_outcome": "error",
                    "sms_error_kind": "request_transport",
                    "sms_to": to_phone,
                    "sms_status_code": 0,
                },
                exc_info=exc,
            )
            raise AfricasTalkingSendError(
                0,
                str(exc),
                error_kind="request_transport",
            ) from exc

    def _default_base_url(self, username: str) -> str:
        if username == "sandbox":
            return "https://api.sandbox.africastalking.com"
        return "https://api.africastalking.com"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["apiKey"] = self.api_key
        return headers
