from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

EventType = Literal["outbound_email", "outbound_sms", "inbound_email", "policy_decision"]


def _default_outbound_dir() -> Path:
    # Canonical location pinned by the Act V Measurement Contract.
    return Path("eval/runs/outbound")


def append_outbound_event(event: dict[str, Any], *, path: Path | None = None) -> None:
    out_dir = path if path is not None else _default_outbound_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "events.jsonl"
    out_path.open("a", encoding="utf-8").write(json.dumps(event, sort_keys=True) + "\n")


def append_policy_event(event: dict[str, Any], *, path: Path | None = None) -> None:
    """Append a policy decision (suppression, gate failure, cadence exhaustion) to the audit log."""
    out_dir = path if path is not None else _default_outbound_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "policy_events.jsonl"
    out_path.open("a", encoding="utf-8").write(json.dumps(event, sort_keys=True) + "\n")


def append_reply_classification(record: dict[str, Any], *, path: Path | None = None) -> None:
    out_dir = path if path is not None else _default_outbound_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reply_classification.jsonl"
    out_path.open("a", encoding="utf-8").write(json.dumps(record, sort_keys=True) + "\n")


def append_thread_outcome(record: dict[str, Any], *, path: Path | None = None) -> None:
    out_dir = path if path is not None else _default_outbound_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "thread_outcomes.jsonl"
    out_path.open("a", encoding="utf-8").write(json.dumps(record, sort_keys=True) + "\n")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
