from __future__ import annotations

import json
from datetime import UTC, datetime

from agent.storage.conversations import ConversationStore
from agent.storage.postgres import postgres_enabled, run_migrations
from agent.workflows.thread_state import recompute_state


def main() -> None:
    if not postgres_enabled():
        raise SystemExit(
            "Conversation DB disabled. Set CONVERSATION_DB_ENABLED=true and POSTGRES_DSN."
        )

    run_migrations()
    store = ConversationStore()

    # Synthetic lead
    email = "lead@example.com"
    phone = "+15555550123"
    subject = "Re: quick question"

    resolved = store.resolve_thread_for_email(
        from_email=email,
        subject=subject,
        provider="resend",
        provider_message_id="inbound_1",
        in_reply_to="outbound_0",
        provider_thread_key="outbound_0",
    )
    assert resolved is not None
    thread_id = resolved.thread_id

    # Outbound email -> inbound reply -> SMS -> booking created
    store.insert_message(
        thread_id=thread_id,
        channel="email",
        direction="outbound",
        provider="resend",
        provider_message_id="outbound_0",
        provider_thread_key="outbound_0",
        subject="Acme: quick thought",
        body_text="Hi there...",
        from_address="team@example.com",
        to_address=email,
        sent_at=datetime.now(UTC),
        outbound_variant="generic",
        draft=True,
        metadata={"outbound_mode": "sink"},
    )
    store.insert_message(
        thread_id=thread_id,
        channel="email",
        direction="inbound",
        provider="resend",
        provider_message_id="inbound_1",
        provider_thread_key="outbound_0",
        in_reply_to="outbound_0",
        subject=subject,
        body_text="Can we schedule next week?",
        from_address=email,
        to_address="team@example.com",
        sent_at=datetime.now(UTC),
        metadata={"event_type": "email.replied"},
    )
    store.attach_hubspot_contact(
        thread_id=thread_id,
        hubspot_contact_id="hs_123",
        lead_email=email,
        lead_phone=phone,
        company_name="ExampleCo",
        company_domain="example.com",
    )
    store.insert_message(
        thread_id=thread_id,
        channel="sms",
        direction="inbound",
        provider="africastalking",
        provider_message_id="sms_1",
        provider_thread_key=phone,
        body_text="Schedule please",
        from_address=phone,
        to_address="12345",
        sent_at=datetime.now(UTC),
    )
    store.insert_event(
        thread_id=thread_id,
        event_type="booking_created",
        payload={"booking_uid": "bk_123", "start": "2026-04-25T09:00:00Z"},
    )

    prior = store.fetch_state(thread_id=thread_id)
    messages = store.fetch_recent_messages(thread_id=thread_id, limit=200)
    events = store.fetch_events(thread_id=thread_id, limit=200)
    derived = recompute_state(
        messages=messages,
        events=events,
        prior_state=prior,
        enrichment={"icp_segment": 0, "segment_confidence": 0.4, "ai_maturity_score": 1},
    )
    store.upsert_state(thread_id=thread_id, state=derived)

    summary = {
        "thread_id": thread_id,
        "thread_key": resolved.thread_key,
        "state": store.fetch_state(thread_id=thread_id),
        "recent_messages": list(
            reversed(store.fetch_recent_messages(thread_id=thread_id, limit=10))
        ),
        "events": list(reversed(store.fetch_events(thread_id=thread_id, limit=10))),
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
