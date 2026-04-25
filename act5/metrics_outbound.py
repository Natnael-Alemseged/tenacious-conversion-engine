from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReplyRateResult:
    variant: str
    outbound_n: int
    replied_n: int
    reply_rate: float
    population_ids: list[str]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compute_reply_rates(*, events_path: Path, reply_class_path: Path) -> dict[str, ReplyRateResult]:
    events = _load_jsonl(events_path)
    replies = _load_jsonl(reply_class_path)

    # Map inbound by (hubspot_contact_id, thread_key) -> is_autoresponder
    inbound_auto = {}
    for row in replies:
        key = (row.get("hubspot_contact_id", ""), row.get("resend_thread_key", ""))
        inbound_auto[key] = bool(row.get("is_autoresponder"))

    outbound_by_variant: dict[str, list[tuple[str, str]]] = {}
    inbound_seen: set[tuple[str, str]] = set()
    for row in events:
        et = row.get("event_type")
        cid = str(row.get("hubspot_contact_id") or "")
        th = str(row.get("resend_thread_key") or "")
        if et == "outbound_email":
            variant = str(row.get("outbound_variant") or "")
            outbound_by_variant.setdefault(variant, []).append((cid, th))
        if et == "inbound_email":
            inbound_seen.add((cid, th))

    results: dict[str, ReplyRateResult] = {}
    for variant, out_threads in outbound_by_variant.items():
        outbound_n = len(out_threads)
        replied_threads = []
        for key in out_threads:
            if key not in inbound_seen:
                continue
            if inbound_auto.get(key) is True:
                continue
            replied_threads.append(key)
        replied_n = len(replied_threads)
        pop_ids = sorted({cid for cid, _ in replied_threads})
        results[variant] = ReplyRateResult(
            variant=variant,
            outbound_n=outbound_n,
            replied_n=replied_n,
            reply_rate=(replied_n / outbound_n) if outbound_n else 0.0,
            population_ids=pop_ids,
        )
    return results
