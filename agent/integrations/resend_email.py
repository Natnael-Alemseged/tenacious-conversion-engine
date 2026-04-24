from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.core.config import settings

_log = logging.getLogger(__name__)


class ResendSendError(Exception):
    """Raised when Resend returns an error response or the request cannot complete."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error_kind: str = "unknown",
    ) -> None:
        super().__init__(f"Resend send failed ({status_code}): {message}")
        self.status_code = status_code
        self.error_kind = error_kind
        self.detail = message


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
        self.reply_to_email = settings.resend_reply_to_email
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
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_email or self.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
        effective_reply_to = reply_to or self.reply_to_email
        if effective_reply_to:
            payload["reply_to"] = effective_reply_to
        if tags:
            payload["tags"] = [{"name": k, "value": v} for k, v in tags.items()]

        _log.debug(
            "resend.send_email",
            extra={
                "email_component": "resend",
                "email_metric": "send_email",
                "email_outcome": "attempt",
                "email_to": to_email,
                "email_subject": subject,
            },
        )
        try:
            response = self.client.post("/emails", json=payload)
            response.raise_for_status()
            body = response.json()
            _log.info(
                "resend.send_email",
                extra={
                    "email_component": "resend",
                    "email_metric": "send_email",
                    "email_outcome": "success",
                    "email_to": to_email,
                    "email_subject": subject,
                    "email_status_code": response.status_code,
                },
            )
            return body
        except httpx.HTTPStatusError as exc:
            _log.error(
                "resend.send_email",
                extra={
                    "email_component": "resend",
                    "email_metric": "send_email",
                    "email_outcome": "error",
                    "email_error_kind": "upstream_http",
                    "email_to": to_email,
                    "email_status_code": exc.response.status_code,
                },
                exc_info=exc,
            )
            raise ResendSendError(
                exc.response.status_code,
                exc.response.text,
                error_kind="upstream_http",
            ) from exc
        except httpx.RequestError as exc:
            _log.error(
                "resend.send_email",
                extra={
                    "email_component": "resend",
                    "email_metric": "send_email",
                    "email_outcome": "error",
                    "email_error_kind": "request_transport",
                    "email_to": to_email,
                    "email_status_code": 0,
                },
                exc_info=exc,
            )
            raise ResendSendError(0, str(exc), error_kind="request_transport") from exc

    def get_received_email(self, email_id: str) -> dict[str, Any]:
        _log.debug(
            "resend.get_received_email",
            extra={
                "email_component": "resend",
                "email_metric": "get_received_email",
                "email_outcome": "attempt",
                "email_id": email_id,
            },
        )
        try:
            response = self.client.get(f"/emails/receiving/{email_id}")
            response.raise_for_status()
            body = response.json()
            _log.info(
                "resend.get_received_email",
                extra={
                    "email_component": "resend",
                    "email_metric": "get_received_email",
                    "email_outcome": "success",
                    "email_id": email_id,
                    "email_status_code": response.status_code,
                },
            )
            return body
        except httpx.HTTPStatusError as exc:
            _log.error(
                "resend.get_received_email",
                extra={
                    "email_component": "resend",
                    "email_metric": "get_received_email",
                    "email_outcome": "error",
                    "email_error_kind": "upstream_http",
                    "email_id": email_id,
                    "email_status_code": exc.response.status_code,
                },
                exc_info=exc,
            )
            raise ResendSendError(
                exc.response.status_code,
                exc.response.text,
                error_kind="upstream_http",
            ) from exc
        except httpx.RequestError as exc:
            _log.error(
                "resend.get_received_email",
                extra={
                    "email_component": "resend",
                    "email_metric": "get_received_email",
                    "email_outcome": "error",
                    "email_error_kind": "request_transport",
                    "email_id": email_id,
                    "email_status_code": 0,
                },
                exc_info=exc,
            )
            raise ResendSendError(0, str(exc), error_kind="request_transport") from exc

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
