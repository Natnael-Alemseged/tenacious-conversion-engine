from __future__ import annotations

from fastapi.testclient import TestClient

from agent.api.routes import outbound
from agent.main import app
from agent.storage.suppression import SmsSuppressionStore


class FakeConversationStore:
    def __init__(self, state: dict | None) -> None:
        self._state = state
        self.enabled = True

    def fetch_state(self, *, thread_id: str) -> dict | None:
        assert thread_id == "thread-1"
        return self._state


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_warm_lead_sms(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"status": "sent", "provider": "fake"}


def test_outbound_sms_sends_only_for_warm_leads(tmp_path, monkeypatch) -> None:
    fake_orc = FakeOrchestrator()
    monkeypatch.setattr(outbound, "orchestrator", fake_orc)
    monkeypatch.setattr(
        outbound.settings, "sms_suppression_path", str(tmp_path / "sms_suppression.json")
    )
    monkeypatch.setattr(outbound, "conversations", FakeConversationStore({"email_replied": True}))

    client = TestClient(app)
    resp = client.post(
        "/outbound/sms",
        json={
            "thread_id": "thread-1",
            "company_name": "Acme",
            "to_phone": "+251911000000",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    assert len(fake_orc.calls) == 1
    assert fake_orc.calls[0]["prior_email_replied"] is True


def test_outbound_sms_blocks_cold_leads(monkeypatch) -> None:
    fake_orc = FakeOrchestrator()
    monkeypatch.setattr(outbound, "orchestrator", fake_orc)
    monkeypatch.setattr(outbound, "conversations", FakeConversationStore({"email_replied": False}))

    client = TestClient(app)
    resp = client.post(
        "/outbound/sms",
        json={
            "thread_id": "thread-1",
            "company_name": "Acme",
            "to_phone": "+251911000000",
        },
    )
    assert resp.status_code == 400
    assert "warm-lead" in str(resp.json()["detail"]).lower()
    assert fake_orc.calls == []


def test_outbound_sms_blocks_sms_opted_out(monkeypatch) -> None:
    fake_orc = FakeOrchestrator()
    monkeypatch.setattr(outbound, "orchestrator", fake_orc)
    monkeypatch.setattr(
        outbound,
        "conversations",
        FakeConversationStore({"email_replied": True, "sms_opted_out": True}),
    )

    client = TestClient(app)
    resp = client.post(
        "/outbound/sms",
        json={
            "thread_id": "thread-1",
            "company_name": "Acme",
            "to_phone": "+251911000000",
        },
    )
    assert resp.status_code == 400
    assert "opt" in str(resp.json()["detail"]).lower()
    assert fake_orc.calls == []


def test_outbound_sms_blocks_suppressed_number(tmp_path, monkeypatch) -> None:
    fake_orc = FakeOrchestrator()
    monkeypatch.setattr(outbound, "orchestrator", fake_orc)
    monkeypatch.setattr(outbound, "conversations", FakeConversationStore({"email_replied": True}))
    path = str(tmp_path / "sms_suppression.json")
    monkeypatch.setattr(outbound.settings, "sms_suppression_path", path)
    SmsSuppressionStore(path).suppress("+251911000000")

    client = TestClient(app)
    resp = client.post(
        "/outbound/sms",
        json={
            "thread_id": "thread-1",
            "company_name": "Acme",
            "to_phone": "+251911000000",
        },
    )
    assert resp.status_code == 400
    assert "suppressed" in str(resp.json()["detail"]).lower()
    assert fake_orc.calls == []
