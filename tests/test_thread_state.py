from datetime import UTC, datetime

from agent.workflows.thread_state import recompute_state


def test_recompute_state_sets_reply_flags_and_last_times() -> None:
    t0 = datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 9, 5, tzinfo=UTC)
    state = recompute_state(
        messages=[
            {
                "direction": "outbound",
                "channel": "email",
                "sent_at": t0,
                "outbound_variant": "generic",
            },
            {"direction": "inbound", "channel": "email", "sent_at": t1},
        ],
        events=[],
        prior_state=None,
        enrichment={"icp_segment": 2, "segment_confidence": 0.71, "ai_maturity_score": 1},
    )

    assert state["email_replied"] is True
    assert state["sms_replied"] is False
    assert state["last_outbound_at"] == t0
    assert state["last_inbound_at"] == t1
    assert state["last_channel"] == "email"
    assert state["outbound_variant"] == "generic"
    assert state["icp_segment"] == 2
    assert abs(state["segment_confidence"] - 0.71) < 1e-6
    assert state["ai_maturity_score"] == 1


def test_recompute_state_counts_outbound_sms_attempts() -> None:
    t0 = datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 9, 5, tzinfo=UTC)
    t2 = datetime(2026, 4, 25, 9, 10, tzinfo=UTC)
    state = recompute_state(
        messages=[
            {"direction": "outbound", "channel": "sms", "sent_at": t0},
            {"direction": "outbound", "channel": "sms", "sent_at": t1},
            {"direction": "outbound", "channel": "email", "sent_at": t2},
        ],
        events=[],
    )
    assert state["outbound_sms_attempt_count"] == 2
    assert state["sms_replied"] is False


def test_recompute_state_sms_reply_resets_not_counted() -> None:
    t0 = datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
    t1 = datetime(2026, 4, 25, 9, 5, tzinfo=UTC)
    state = recompute_state(
        messages=[
            {"direction": "outbound", "channel": "sms", "sent_at": t0},
            {"direction": "inbound", "channel": "sms", "sent_at": t1},
        ],
        events=[],
    )
    assert state["outbound_sms_attempt_count"] == 1
    assert state["sms_replied"] is True


def test_recompute_state_opt_out_and_booking_events() -> None:
    state = recompute_state(
        messages=[],
        events=[
            {"event_type": "opt_out", "payload_json": {"source": "webhooks.sms"}},
            {"event_type": "booking_requested", "payload_json": {"channel": "email"}},
            {"event_type": "booking_created", "payload_json": {"booking_uid": "bk_123"}},
        ],
        prior_state={"sms_opted_out": False},
    )

    assert state["sms_opted_out"] is True
    assert state["booking_requested"] is True
    assert state["booking_created"] is True
    assert state["booking_uid"] == "bk_123"
