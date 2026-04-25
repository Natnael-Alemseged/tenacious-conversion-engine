from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent.enrichment.velocity_store import (
    VelocitySnapshot,
    append_snapshot,
    compute_60_day_velocity,
)


def test_compute_60_day_velocity_uses_near_60_day_snapshot(tmp_path) -> None:
    path = str(tmp_path / "snapshots.jsonl")
    domain = "example.com"

    now = datetime.now(UTC)
    snap_60ish = VelocitySnapshot(
        recorded_at=(now - timedelta(days=61)).isoformat(),
        domain=domain,
        open_roles=10,
        ai_adjacent_roles=2,
        source_url="https://careers.example.com",
    )
    append_snapshot(path, snap_60ish)

    out = compute_60_day_velocity(path=path, domain=domain, open_roles_today=18)
    assert out["open_roles_60_days_ago"] == 10
    assert out["velocity_delta_60_days"] == 8
    assert out["velocity_label"] == "accelerating"


def test_compute_60_day_velocity_insufficient_when_no_snapshot(tmp_path) -> None:
    path = str(tmp_path / "snapshots.jsonl")
    out = compute_60_day_velocity(path=path, domain="missing.com", open_roles_today=5)
    assert out["velocity_label"] == "insufficient_signal"
    assert out["open_roles_60_days_ago"] is None
