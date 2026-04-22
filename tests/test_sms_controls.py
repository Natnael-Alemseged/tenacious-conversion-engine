from fastapi.testclient import TestClient

from app.api.routes import webhooks
from app.main import app


client = TestClient(app)


def test_stop_adds_number_to_suppression_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(webhooks.settings, "sms_suppression_path", str(tmp_path / "suppression.json"))

    response = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "STOP", "id": "1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "suppressed"


def test_help_returns_guidance(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(webhooks.settings, "sms_suppression_path", str(tmp_path / "suppression.json"))

    response = client.post(
        "/webhooks/sms",
        data={"from": "+251911000000", "to": "12345", "text": "HELP", "id": "2"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "help"


def test_suppressed_number_is_ignored_until_start(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(webhooks.settings, "sms_suppression_path", str(tmp_path / "suppression.json"))

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
