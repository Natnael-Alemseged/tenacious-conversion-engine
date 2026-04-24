import logging

import httpx
import pytest

from agent.integrations.africastalking_sms import AfricasTalkingSendError, AfricasTalkingSmsClient

SMS_LOGGER = "agent.integrations.africastalking_sms"


def _make_client(handler: httpx.MockTransport | None = None) -> AfricasTalkingSmsClient:
    return AfricasTalkingSmsClient(
        username="sandbox",
        api_key="at_test",
        short_code="12345",
        transport=httpx.MockTransport(handler) if handler else None,
    )


def test_send_sms_uses_africas_talking_api() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "SMSMessageData": {"Recipients": [{"status": "Success", "messageId": "ATXid_123"}]}
            },
        )

    client = _make_client(handler)
    response = client.send_sms(to_phone="+251911000000", message="hello world")

    assert response["SMSMessageData"]["Recipients"][0]["messageId"] == "ATXid_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/version1/messaging"
    assert captured["headers"]["apikey"] == "at_test"
    assert "username=sandbox" in captured["body"]
    assert "to=%2B251911000000" in captured["body"]
    assert "from=12345" in captured["body"]


def test_send_sms_raises_typed_error_on_provider_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="gateway error")

    client = _make_client(handler)

    with pytest.raises(AfricasTalkingSendError) as exc:
        client.send_sms(to_phone="+251911000000", message="hello world")

    assert exc.value.status_code == 500
    assert exc.value.error_kind == "upstream_http"


def test_send_sms_raises_typed_error_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = _make_client(handler)

    with pytest.raises(AfricasTalkingSendError) as exc:
        client.send_sms(to_phone="+251911000000", message="hello world")

    assert exc.value.error_kind == "malformed_response"


def test_send_sms_logs_attempt_before_request(caplog: pytest.LogCaptureFixture) -> None:
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append("hit")
        return httpx.Response(
            200,
            json={"SMSMessageData": {"Recipients": [{"status": "Success", "messageId": "x"}]}},
        )

    client = _make_client(handler)

    with caplog.at_level(logging.DEBUG, logger=SMS_LOGGER):
        client.send_sms(to_phone="+251911000000", message="ping")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug_records, "expected a DEBUG attempt log before the request"
    r = debug_records[0]
    assert r.getMessage() == "africastalking.send_sms"
    assert r.sms_outcome == "attempt"
    assert r.sms_to == "+251911000000"
    assert r.sms_username == "sandbox"


def test_send_sms_logs_success(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "SMSMessageData": {"Recipients": [{"status": "Success", "messageId": "ATXid_1"}]}
            },
        )

    client = _make_client(handler)

    with caplog.at_level(logging.INFO, logger=SMS_LOGGER):
        client.send_sms(to_phone="+251911000001", message="hello")

    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage() == "africastalking.send_sms"
    ]
    assert info_records, "expected an INFO success log after a 200 response"
    r = info_records[-1]
    assert r.sms_outcome == "success"
    assert r.sms_to == "+251911000001"
    assert r.sms_status_code == 200


def test_send_sms_logs_error_on_upstream_http_failure(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="gateway error")

    client = _make_client(handler)

    with caplog.at_level(logging.ERROR, logger=SMS_LOGGER):
        with pytest.raises(AfricasTalkingSendError):
            client.send_sms(to_phone="+251911000002", message="fail me")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "africastalking.send_sms"
    ]
    assert error_records, "expected an ERROR log on 5xx response"
    r = error_records[-1]
    assert r.sms_outcome == "error"
    assert r.sms_error_kind == "upstream_http"
    assert r.sms_status_code == 500
    assert r.sms_to == "+251911000002"


def test_send_sms_logs_error_on_malformed_response(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = _make_client(handler)

    with caplog.at_level(logging.ERROR, logger=SMS_LOGGER):
        with pytest.raises(AfricasTalkingSendError):
            client.send_sms(to_phone="+251911000003", message="bad json")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "africastalking.send_sms"
    ]
    assert error_records, "expected an ERROR log on malformed JSON response"
    r = error_records[-1]
    assert r.sms_outcome == "error"
    assert r.sms_error_kind == "malformed_response"
    assert r.sms_to == "+251911000003"


def test_send_sms_logs_error_on_transport_failure(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _make_client(handler)

    with caplog.at_level(logging.ERROR, logger=SMS_LOGGER):
        with pytest.raises(AfricasTalkingSendError):
            client.send_sms(to_phone="+251911000004", message="unreachable")

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and r.getMessage() == "africastalking.send_sms"
    ]
    assert error_records, "expected an ERROR log on network transport failure"
    r = error_records[-1]
    assert r.sms_outcome == "error"
    assert r.sms_error_kind == "request_transport"
    assert r.sms_to == "+251911000004"
