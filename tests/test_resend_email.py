import json

import httpx
import pytest

from agent.integrations.resend_email import ResendClient, ResendSendError


def test_send_email_uses_resend_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"id": "email_123"})

    monkeypatch.setattr(
        "agent.integrations.resend_email.settings.resend_from_email",
        "team@example.com",
    )
    client = ResendClient(
        api_key="re_test",
        transport=httpx.MockTransport(handler),
    )

    response = client.send_email(
        to_email="lead@example.com",
        subject="Hello",
        html="<p>Hi</p>",
        reply_to="owner@example.com",
    )

    assert response["id"] == "email_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/emails"
    assert captured["authorization"] == "Bearer re_test"
    assert captured["json"]["from"] == "team@example.com"
    assert captured["json"]["reply_to"] == "owner@example.com"


def test_send_email_http_error_sets_error_kind(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Invalid"})

    monkeypatch.setattr(
        "agent.integrations.resend_email.settings.resend_from_email",
        "team@example.com",
    )
    client = ResendClient(
        api_key="re_test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ResendSendError) as excinfo:
        client.send_email(to_email="lead@example.com", subject="Hi", html="<p>x</p>")

    err = excinfo.value
    assert err.status_code == 422
    assert err.error_kind == "upstream_http"


def test_send_email_transport_error_sets_error_kind(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(
        "agent.integrations.resend_email.settings.resend_from_email",
        "team@example.com",
    )
    client = ResendClient(
        api_key="re_test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ResendSendError) as excinfo:
        client.send_email(to_email="lead@example.com", subject="Hi", html="<p>x</p>")

    assert excinfo.value.error_kind == "request_transport"
    assert excinfo.value.status_code == 0
