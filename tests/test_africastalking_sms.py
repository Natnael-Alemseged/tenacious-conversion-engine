import httpx
import pytest

from agent.integrations.africastalking_sms import AfricasTalkingSendError, AfricasTalkingSmsClient


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

    client = AfricasTalkingSmsClient(
        username="sandbox",
        api_key="at_test",
        short_code="12345",
        transport=httpx.MockTransport(handler),
    )

    response = client.send_sms(
        to_phone="+251911000000",
        message="hello world",
    )

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

    client = AfricasTalkingSmsClient(
        username="sandbox",
        api_key="at_test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AfricasTalkingSendError) as exc:
        client.send_sms(to_phone="+251911000000", message="hello world")

    assert exc.value.status_code == 500
