from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def recompute_state(
    *,
    messages: list[dict[str, Any]],
    events: list[dict[str, Any]],
    prior_state: dict[str, Any] | None = None,
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure derived state recompute from messages/events + optional enrichment fields."""
    prior_state = prior_state or {}
    enrichment = enrichment or {}

    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None
    last_channel: str | None = None
    email_replied = _as_bool(prior_state.get("email_replied"), False)
    sms_replied = _as_bool(prior_state.get("sms_replied"), False)
    sms_opted_out = _as_bool(prior_state.get("sms_opted_out"), False)
    outbound_sms_attempt_count = 0
    booking_requested = _as_bool(prior_state.get("booking_requested"), False)
    booking_created = _as_bool(prior_state.get("booking_created"), False)
    booking_uid = prior_state.get("booking_uid")
    outbound_variant = prior_state.get("outbound_variant")
    last_unanswered_question = prior_state.get("last_unanswered_question")

    # Carry forward memory blobs by default; workflows can write into these incrementally.
    qualification_json = prior_state.get("qualification_json") or {}
    memory_json = prior_state.get("memory_json") or {}
    if isinstance(qualification_json, str):
        try:
            qualification_json = json.loads(qualification_json)
        except Exception:
            qualification_json = {}
    if isinstance(memory_json, str):
        try:
            memory_json = json.loads(memory_json)
        except Exception:
            memory_json = {}

    for msg in messages:
        direction = str(msg.get("direction") or "")
        channel = str(msg.get("channel") or "")
        sent_at = _as_dt(msg.get("sent_at")) or _as_dt(msg.get("created_at"))
        if not sent_at:
            continue
        if direction == "inbound":
            if last_inbound_at is None or sent_at > last_inbound_at:
                last_inbound_at = sent_at
                last_channel = channel or last_channel
            if channel == "email":
                email_replied = True
            if channel == "sms":
                sms_replied = True
        elif direction == "outbound":
            if last_outbound_at is None or sent_at > last_outbound_at:
                last_outbound_at = sent_at
                last_channel = channel or last_channel
            if channel == "sms":
                outbound_sms_attempt_count += 1
            if msg.get("outbound_variant"):
                outbound_variant = str(msg.get("outbound_variant") or "") or outbound_variant

    for ev in events:
        event_type = str(ev.get("event_type") or "")
        payload = ev.get("payload_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        payload = payload or {}
        if event_type == "opt_out":
            sms_opted_out = True
        elif event_type == "opt_in":
            sms_opted_out = False
        elif event_type == "booking_created":
            booking_created = True
            uid = str(payload.get("booking_uid") or "")
            if uid:
                booking_uid = uid
        elif event_type == "booking_requested":
            booking_requested = True

    # Enrichment fields (mirrors existing pipeline outputs).
    bench_gate_passed = enrichment.get("bench_gate_passed", prior_state.get("bench_gate_passed"))
    icp_segment = enrichment.get("icp_segment", prior_state.get("icp_segment"))
    segment_confidence = enrichment.get("segment_confidence", prior_state.get("segment_confidence"))
    ai_maturity_score = enrichment.get("ai_maturity_score", prior_state.get("ai_maturity_score"))

    updated = {
        "last_channel": last_channel,
        "last_inbound_at": last_inbound_at,
        "last_outbound_at": last_outbound_at,
        "email_replied": email_replied,
        "sms_replied": sms_replied,
        "sms_opted_out": sms_opted_out,
        "booking_requested": booking_requested,
        "booking_created": booking_created,
        "booking_uid": booking_uid,
        "bench_gate_passed": bench_gate_passed if bench_gate_passed is not None else None,
        "icp_segment": _as_int(icp_segment),
        "segment_confidence": _as_float(segment_confidence),
        "ai_maturity_score": _as_int(ai_maturity_score),
        "outbound_variant": outbound_variant,
        "outbound_sms_attempt_count": outbound_sms_attempt_count,
        "last_unanswered_question": last_unanswered_question,
        "qualification_json": qualification_json,
        "memory_json": memory_json,
        "updated_at": _utc_now(),
    }
    return updated
