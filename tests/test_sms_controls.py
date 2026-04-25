from fastapi.testclient import TestClient

from agent.api.routes import webhooks
from agent.main import app

client = TestClient(app)


def _suppression_path(tmp_path) -> str:
    return str(tmp_path / "suppression.json")


def test_stop_adds_number_to_suppression_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )

    response = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "STOP", "id": "1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "suppressed"


def test_help_returns_guidance(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )

    response = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "HELP", "id": "2"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "help"


def test_suppressed_number_is_ignored_until_start(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )

    client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "STOP", "id": "3"},
    )
    ignored = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "hello", "id": "4"},
    )
    resumed = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "START", "id": "5"},
    )

    assert ignored.json()["status"] == "ignored"
    assert resumed.json()["status"] == "resubscribed"


def test_malformed_sms_payload_returns_422(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )

    response = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "id": "6"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "validation_error"
    assert "field_errors" in detail["error"]


def test_sms_from_number_must_be_e164(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )

    response = client.post(
        "/webhooks/sms",
        data={"from": "251911000000", "to": "12345", "text": "hi", "id": "7"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "validation_error"


def test_sms_json_body_returns_415(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )

    response = client.post(
        "/webhooks/sms",
        json={"from": "+251911000000", "text": "hi"},
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["error"]["code"] == "unsupported_media_type"


def test_duplicate_sms_message_id_is_ignored(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        webhooks.settings,
        "sms_suppression_path",
        _suppression_path(tmp_path),
    )
    monkeypatch.setattr(
        webhooks.settings,
        "outbound_enabled",
        False,
    )
    monkeypatch.setattr(
        webhooks.settings,
        "outbound_sink_phone",
        "+15555550123",
    )
    webhooks._recent_sms_events.clear()
    webhooks._recent_sms_events_order.clear()

    first = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "hello", "id": "sms-dup-1"},
    )
    second = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "hello", "id": "sms-dup-1"},
    )

    assert first.status_code == 200
    assert first.json()["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
