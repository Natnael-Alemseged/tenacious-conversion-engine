from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VelocitySnapshot:
    recorded_at: str
    domain: str
    open_roles: int
    ai_adjacent_roles: int
    source_url: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(dt: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def append_snapshot(path: str, snapshot: VelocitySnapshot) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "recorded_at": snapshot.recorded_at,
        "domain": snapshot.domain,
        "open_roles": int(snapshot.open_roles),
        "ai_adjacent_roles": int(snapshot.ai_adjacent_roles),
        "source_url": snapshot.source_url,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _iter_snapshots(path: str, *, domain: str) -> list[VelocitySnapshot]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[VelocitySnapshot] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(raw.get("domain") or "") != domain:
            continue
        out.append(
            VelocitySnapshot(
                recorded_at=str(raw.get("recorded_at") or ""),
                domain=domain,
                open_roles=int(raw.get("open_roles") or 0),
                ai_adjacent_roles=int(raw.get("ai_adjacent_roles") or 0),
                source_url=str(raw.get("source_url") or ""),
            )
        )
    return out


def compute_60_day_velocity(
    *,
    path: str,
    domain: str,
    open_roles_today: int,
) -> dict[str, Any]:
    """
    Return fields for the public brief:
    - open_roles_60_days_ago
    - velocity_delta_60_days
    - velocity_label
    - velocity_snapshot_at
    """
    snapshots = _iter_snapshots(path, domain=domain)
    if not snapshots:
        return {
            "open_roles_60_days_ago": None,
            "velocity_delta_60_days": None,
            "velocity_label": "insufficient_signal",
            "velocity_snapshot_at": "",
        }

    target = datetime.now(UTC) - timedelta(days=60)
    # Allow some tolerance for “closest to 60d” history, without using a fresh snapshot.
    lower = target - timedelta(days=10)
    upper = target + timedelta(days=10)

    candidates: list[tuple[datetime, VelocitySnapshot]] = []
    for snap in snapshots:
        dt = _parse_iso(snap.recorded_at)
        if dt is None:
            continue
        if lower <= dt <= upper:
            candidates.append((dt, snap))
    if not candidates:
        return {
            "open_roles_60_days_ago": None,
            "velocity_delta_60_days": None,
            "velocity_label": "insufficient_signal",
            "velocity_snapshot_at": "",
        }

    # Choose the snapshot closest to the target.
    candidates.sort(key=lambda pair: abs((pair[0] - target).total_seconds()))
    _, chosen = candidates[0]
    past = int(chosen.open_roles)
    delta = int(open_roles_today) - past

    if delta >= 5:
        label = "accelerating"
    elif delta <= -5:
        label = "declining"
    else:
        label = "stable"

    return {
        "open_roles_60_days_ago": past,
        "velocity_delta_60_days": delta,
        "velocity_label": label,
        "velocity_snapshot_at": chosen.recorded_at,
    }
