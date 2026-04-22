import json

import httpx

from agent.integrations.resend_email import ResendClient


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
