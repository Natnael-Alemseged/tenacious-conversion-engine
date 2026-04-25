import json
import logging

import httpx
import pytest

from agent.integrations.resend_email import ResendClient, ResendSendError

EMAIL_LOGGER = "agent.integrations.resend_email"


def test_send_email_uses_resend_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["idempotency_key"] = request.headers.get("Idempotency-Key")
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
        text="Hi",
        headers={"In-Reply-To": "<msg-123>", "References": "<msg-122> <msg-123>"},
        idempotency_key="reply-msg-123",
    )

    assert response["id"] == "email_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/emails"
    assert captured["authorization"] == "Bearer re_test"
    assert captured["json"]["from"] == "team@example.com"
    assert captured["json"]["reply_to"] == "owner@example.com"
    assert captured["json"]["text"] == "Hi"
    assert captured["json"]["headers"]["In-Reply-To"] == "<msg-123>"
    assert captured["json"]["headers"]["References"] == "<msg-122> <msg-123>"
    assert captured["idempotency_key"] == "reply-msg-123"


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


def test_send_email_uses_default_reply_to_from_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"id": "email_456"})

    monkeypatch.setattr(
        "agent.integrations.resend_email.settings.resend_from_email",
        "team@example.com",
    )
    monkeypatch.setattr(
        "agent.integrations.resend_email.settings.resend_reply_to_email",
        "anything@talauminai.resend.app",
    )

    client = ResendClient(
        api_key="re_test",
        transport=httpx.MockTransport(handler),
    )

    response = client.send_email(
        to_email="lead@example.com",
        subject="Hello",
        html="<p>Hi</p>",
    )

    assert response["id"] == "email_456"
    assert captured["json"]["reply_to"] == "anything@talauminai.resend.app"


# ── send_email logging ────────────────────────────────────────────────────────


def test_send_email_logs_attempt(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "email_1"})

    monkeypatch.setattr("agent.integrations.resend_email.settings.resend_from_email", "t@e.com")
    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.DEBUG, logger=EMAIL_LOGGER):
        client.send_email(to_email="lead@example.com", subject="Hi", html="<p>x</p>")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug_records, "expected DEBUG attempt log before sending"
    r = debug_records[0]
    assert r.getMessage() == "resend.send_email"
    assert r.email_outcome == "attempt"
    assert r.email_to == "lead@example.com"
    assert r.email_subject == "Hi"


def test_send_email_logs_success(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "email_2"})

    monkeypatch.setattr("agent.integrations.resend_email.settings.resend_from_email", "t@e.com")
    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.INFO, logger=EMAIL_LOGGER):
        client.send_email(to_email="lead@example.com", subject="Hi", html="<p>x</p>")

    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage() == "resend.send_email"
    ]
    assert info_records, "expected INFO success log"
    r = info_records[-1]
    assert r.email_outcome == "success"
    assert r.email_to == "lead@example.com"
    assert r.email_status_code == 200


def test_send_email_logs_error_on_http_failure(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Invalid"})

    monkeypatch.setattr("agent.integrations.resend_email.settings.resend_from_email", "t@e.com")
    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.ERROR, logger=EMAIL_LOGGER):
        with pytest.raises(ResendSendError):
            client.send_email(to_email="lead@example.com", subject="Hi", html="<p>x</p>")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "resend.send_email"
    ]
    assert error_records, "expected ERROR log on 4xx response"
    r = error_records[-1]
    assert r.email_outcome == "error"
    assert r.email_error_kind == "upstream_http"
    assert r.email_status_code == 422


def test_send_email_logs_error_on_transport_failure(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr("agent.integrations.resend_email.settings.resend_from_email", "t@e.com")
    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.ERROR, logger=EMAIL_LOGGER):
        with pytest.raises(ResendSendError):
            client.send_email(to_email="lead@example.com", subject="Hi", html="<p>x</p>")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "resend.send_email"
    ]
    assert error_records, "expected ERROR log on transport failure"
    r = error_records[-1]
    assert r.email_outcome == "error"
    assert r.email_error_kind == "request_transport"
    assert r.email_status_code == 0


# ── get_received_email logging ────────────────────────────────────────────────


def test_get_received_email_logs_attempt(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"email_id": "abc", "subject": "Re: hi"})

    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.DEBUG, logger=EMAIL_LOGGER):
        client.get_received_email("abc")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug_records, "expected DEBUG attempt log"
    r = debug_records[0]
    assert r.getMessage() == "resend.get_received_email"
    assert r.email_outcome == "attempt"
    assert r.email_id == "abc"


def test_get_received_email_logs_success(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"email_id": "abc", "subject": "Re: hi"})

    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.INFO, logger=EMAIL_LOGGER):
        client.get_received_email("abc")

    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage() == "resend.get_received_email"
    ]
    assert info_records, "expected INFO success log"
    r = info_records[-1]
    assert r.email_outcome == "success"
    assert r.email_id == "abc"
    assert r.email_status_code == 200


def test_get_received_email_logs_error_on_http_failure(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.ERROR, logger=EMAIL_LOGGER):
        with pytest.raises(ResendSendError):
            client.get_received_email("missing-id")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "resend.get_received_email"
    ]
    assert error_records, "expected ERROR log on 404"
    r = error_records[-1]
    assert r.email_outcome == "error"
    assert r.email_error_kind == "upstream_http"
    assert r.email_status_code == 404
    assert r.email_id == "missing-id"


def test_get_received_email_logs_error_on_transport_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = ResendClient(api_key="re_test", transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.ERROR, logger=EMAIL_LOGGER):
        with pytest.raises(ResendSendError):
            client.get_received_email("xyz")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "resend.get_received_email"
    ]
    assert error_records, "expected ERROR log on transport failure"
    r = error_records[-1]
    assert r.email_outcome == "error"
    assert r.email_error_kind == "request_transport"
    assert r.email_id == "xyz"
