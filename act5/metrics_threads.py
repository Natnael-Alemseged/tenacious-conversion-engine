from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ThreadOutcomeResult:
    inbound_n: int
    stalled_n: int
    stalled_rate: float
    booked_n: int
    population_ids: list[str]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compute_thread_outcomes(
    *, thread_outcomes_path: Path, reply_class_path: Path
) -> ThreadOutcomeResult:
    outcomes = _load_jsonl(thread_outcomes_path)
    replies = _load_jsonl(reply_class_path)

    inbound_auto = {}
    for row in replies:
        key = (row.get("hubspot_contact_id", ""), row.get("resend_thread_key", ""))
        inbound_auto[key] = bool(row.get("is_autoresponder"))

    eligible: list[dict] = []
    for row in outcomes:
        key = (row.get("hubspot_contact_id", ""), row.get("resend_thread_key", ""))
        if inbound_auto.get(key) is True:
            continue
        eligible.append(row)

    inbound_n = len(eligible)
    booked = [row for row in eligible if bool(row.get("booking_created"))]
    booked_n = len(booked)
    stalled_n = inbound_n - booked_n
    pop_ids = sorted(
        {
            str(row.get("hubspot_contact_id") or "")
            for row in eligible
            if row.get("hubspot_contact_id")
        }
    )
    return ThreadOutcomeResult(
        inbound_n=inbound_n,
        stalled_n=stalled_n,
        stalled_rate=(stalled_n / inbound_n) if inbound_n else 0.0,
        booked_n=booked_n,
        population_ids=pop_ids,
    )
