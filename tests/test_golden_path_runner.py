from __future__ import annotations

from pathlib import Path

from scripts.run_golden_path import run_golden_path


def test_offline_golden_path_runner_emits_artifacts(tmp_path: Path) -> None:
    summary = run_golden_path(
        live=False,
        artifacts_dir=tmp_path,
        seed=7,
        company_name="Acme Data",
        lead_email="prospect@example.com",
        careers_url="https://acme.example/careers",
    )

    artifacts = summary["artifacts"]
    expected = [
        "hiring_signal_brief",
        "competitor_gap_brief",
        "outbound_send",
        "inbound_reply",
        "booking",
        "crm_snapshot",
        "thread_summary",
        "thread_state",
    ]
    for key in expected:
        assert key in artifacts, f"Missing artifact key {key}"
        assert Path(artifacts[key]).exists(), f"Missing artifact file {artifacts[key]}"

    booking = Path(artifacts["booking"]).read_text(encoding="utf-8")
    assert "fake_booking_" in booking, "Expected offline booking uid to be created"

    crm_snapshot_path = Path(artifacts["crm_snapshot"])
    assert crm_snapshot_path.exists()

    # Summary links the full flow and includes key ids.
    assert summary["thread_id"]
    assert summary["lead_id"]
    ids = summary["ids"]
    assert ids["outbound_message_id"]
    assert ids["inbound_message_id"]
    assert ids["booking_uid"]
    assert ids["hubspot_contact_id"]
