from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection

from agent.storage.postgres import ensure_schema, get_conn, postgres_enabled


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _norm_phone(phone: str) -> str:
    return re.sub(r"[^\d+]", "", (phone or "").strip())


def _company_domain_from_email(email: str) -> str:
    email = _norm_email(email)
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1][:255]


def _norm_subject(subject: str) -> str:
    cleaned = (subject or "").strip().lower()
    cleaned = re.sub(r"^(re|fwd)\s*:\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:255]


def _hash_key(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:24]


@dataclass(frozen=True)
class ResolvedThread:
    thread_id: str
    thread_key: str


class ConversationStore:
    """Postgres-backed conversation memory with thread resolution + persistence helpers."""

    def __init__(self) -> None:
        self.enabled = postgres_enabled()

    def _conn(self) -> Connection:
        if not self.enabled:
            raise RuntimeError("ConversationStore is disabled.")
        return get_conn().__enter__()  # noqa: SIM115 (managed explicitly below)

    def resolve_thread_for_email(
        self,
        *,
        from_email: str,
        subject: str,
        provider: str,
        provider_message_id: str,
        in_reply_to: str,
        provider_thread_key: str,
        hubspot_contact_id: str = "",
    ) -> ResolvedThread | None:
        if not self.enabled:
            return None
        from_email_n = _norm_email(from_email)
        domain = _company_domain_from_email(from_email_n)

        candidate_keys: list[str] = []
        if in_reply_to:
            candidate_keys.append(f"email:{provider}:{in_reply_to}")
        if provider_thread_key:
            candidate_keys.append(f"email:{provider}:{provider_thread_key}")
        if provider_message_id:
            candidate_keys.append(f"email:{provider}:{provider_message_id}")

        # Fallback: normalized (from_email, subject, company_domain)
        fallback = f"email_fallback:{_hash_key(from_email_n, _norm_subject(subject), domain)}"
        candidate_keys.append(fallback)

        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                # Prefer hubspot-contact-linked thread if present.
                if hubspot_contact_id:
                    cur.execute(
                        """
                        select id, thread_key
                        from conversation_threads
                        where hubspot_contact_id = %s
                        order by updated_at desc
                        limit 1
                        """,
                        (hubspot_contact_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return ResolvedThread(
                            thread_id=str(row["id"]), thread_key=str(row["thread_key"])
                        )

                # Try by explicit keys.
                cur.execute(
                    """
                    select id, thread_key
                    from conversation_threads
                    where thread_key = any(%s)
                    order by updated_at desc
                    limit 1
                    """,
                    (candidate_keys,),
                )
                row = cur.fetchone()
                if row:
                    return ResolvedThread(
                        thread_id=str(row["id"]), thread_key=str(row["thread_key"])
                    )

                # Create new thread using the strongest key available (first).
                primary_key = candidate_keys[0]
                cur.execute(
                    """
                    insert into conversation_threads (
                      thread_key,
                      hubspot_contact_id,
                      lead_email,
                      company_domain,
                      primary_channel,
                      status,
                      created_at,
                      updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, now(), now())
                    returning id
                    """,
                    (
                        primary_key,
                        hubspot_contact_id or None,
                        from_email_n or None,
                        domain or None,
                        "email",
                        "active",
                    ),
                )
                created = cur.fetchone()
                conn.commit()
                return ResolvedThread(thread_id=str(created["id"]), thread_key=primary_key)

    def resolve_thread_for_sms(
        self,
        *,
        from_phone: str,
        hubspot_contact_id: str = "",
    ) -> ResolvedThread | None:
        if not self.enabled:
            return None
        phone = _norm_phone(from_phone)
        if not phone:
            return None
        key = f"sms:{phone}"
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                if hubspot_contact_id:
                    cur.execute(
                        """
                        select id, thread_key
                        from conversation_threads
                        where hubspot_contact_id = %s
                        order by updated_at desc
                        limit 1
                        """,
                        (hubspot_contact_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        # Attach phone if missing.
                        cur.execute(
                            """
                            update conversation_threads
                            set lead_phone = coalesce(lead_phone, %s),
                                updated_at = now()
                            where id = %s
                            """,
                            (phone, row["id"]),
                        )
                        conn.commit()
                        return ResolvedThread(
                            thread_id=str(row["id"]), thread_key=str(row["thread_key"])
                        )

                cur.execute(
                    "select id, thread_key from conversation_threads where thread_key = %s limit 1",
                    (key,),
                )
                row = cur.fetchone()
                if row:
                    return ResolvedThread(
                        thread_id=str(row["id"]), thread_key=str(row["thread_key"])
                    )

                cur.execute(
                    """
                    insert into conversation_threads (
                      thread_key,
                      hubspot_contact_id,
                      lead_phone,
                      primary_channel,
                      status,
                      created_at,
                      updated_at
                    )
                    values (%s, %s, %s, %s, %s, now(), now())
                    returning id
                    """,
                    (key, hubspot_contact_id or None, phone, "sms", "active"),
                )
                created = cur.fetchone()
                conn.commit()
                return ResolvedThread(thread_id=str(created["id"]), thread_key=key)

    def attach_hubspot_contact(
        self,
        *,
        thread_id: str,
        hubspot_contact_id: str,
        lead_email: str = "",
        lead_phone: str = "",
        company_name: str = "",
        company_domain: str = "",
    ) -> None:
        if not self.enabled or not hubspot_contact_id:
            return
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                # If another thread already has this hubspot_contact_id, merge into it.
                cur.execute(
                    """
                    select id
                    from conversation_threads
                    where hubspot_contact_id = %s and id <> %s
                    order by updated_at desc
                    limit 1
                    """,
                    (hubspot_contact_id, thread_id),
                )
                other = cur.fetchone()
                target_id = str(other["id"]) if other else thread_id
                source_id = thread_id if other else ""

                if source_id:
                    cur.execute(
                        "update conversation_messages set thread_id = %s where thread_id = %s",
                        (target_id, source_id),
                    )
                    cur.execute(
                        "update conversation_events set thread_id = %s where thread_id = %s",
                        (target_id, source_id),
                    )
                    # Merge state rows (keep the newer updated_at if both exist).
                    cur.execute(
                        """
                        insert into conversation_state (thread_id)
                        values (%s)
                        on conflict (thread_id) do nothing
                        """,
                        (target_id,),
                    )
                    cur.execute(
                        """
                        delete from conversation_state
                        where thread_id = %s and exists (
                          select 1 from conversation_state cs2 where cs2.thread_id = %s
                        )
                        """,
                        (source_id, target_id),
                    )
                    cur.execute("delete from conversation_threads where id = %s", (source_id,))

                cur.execute(
                    """
                    update conversation_threads
                    set hubspot_contact_id = %s,
                        lead_email = coalesce(lead_email, %s),
                        lead_phone = coalesce(lead_phone, %s),
                        company_name = coalesce(company_name, %s),
                        company_domain = coalesce(company_domain, %s),
                        updated_at = now()
                    where id = %s
                    """,
                    (
                        hubspot_contact_id,
                        _norm_email(lead_email) or None,
                        _norm_phone(lead_phone) or None,
                        (company_name or "")[:255] or None,
                        (company_domain or "")[:255] or None,
                        target_id,
                    ),
                )
            conn.commit()

    def insert_message(
        self,
        *,
        thread_id: str,
        channel: str,
        direction: str,
        provider: str,
        provider_message_id: str = "",
        provider_thread_key: str = "",
        in_reply_to: str = "",
        subject: str = "",
        body_text: str = "",
        from_address: str = "",
        to_address: str = "",
        sent_at: datetime | None = None,
        is_autoresponder: bool | None = None,
        outbound_variant: str | None = None,
        draft: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        sent_at = sent_at or _utc_now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into conversation_messages (
                      thread_id, channel, direction, provider,
                      provider_message_id, provider_thread_key, in_reply_to,
                      subject, body_text, from_address, to_address,
                      sent_at, is_autoresponder, outbound_variant, draft, metadata_json,
                      created_at
                    )
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now())
                    returning id
                    """,
                    (
                        thread_id,
                        channel,
                        direction,
                        provider,
                        provider_message_id or None,
                        provider_thread_key or None,
                        in_reply_to or None,
                        subject or None,
                        body_text or None,
                        from_address or None,
                        to_address or None,
                        sent_at,
                        is_autoresponder,
                        outbound_variant,
                        draft,
                        metadata_json,
                    ),
                )
                msg_id = str(cur.fetchone()["id"])
                cur.execute(
                    "update conversation_threads set updated_at = now() where id = %s", (thread_id,)
                )
            conn.commit()
        return msg_id

    def insert_event(
        self,
        *,
        thread_id: str,
        event_type: str,
        event_at: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        event_at = event_at or _utc_now()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into conversation_events (thread_id, event_type, event_at, payload_json)
                    values (%s, %s, %s, %s::jsonb)
                    returning id
                    """,
                    (thread_id, event_type, event_at, payload_json),
                )
                event_id = str(cur.fetchone()["id"])
                cur.execute(
                    "update conversation_threads set updated_at = now() where id = %s", (thread_id,)
                )
            conn.commit()
        return event_id

    def fetch_recent_messages(self, *, thread_id: str, limit: int = 10) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select *
                    from conversation_messages
                    where thread_id = %s
                    order by sent_at desc, created_at desc
                    limit %s
                    """,
                    (thread_id, limit),
                )
                return list(cur.fetchall())

    def fetch_events(self, *, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select *
                    from conversation_events
                    where thread_id = %s
                    order by event_at desc
                    limit %s
                    """,
                    (thread_id, limit),
                )
                return list(cur.fetchall())

    def upsert_state(self, *, thread_id: str, state: dict[str, Any]) -> None:
        if not self.enabled:
            return
        # state must include updated_at
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into conversation_state (
                      thread_id,
                      last_channel,
                      last_inbound_at,
                      last_outbound_at,
                      email_replied,
                      sms_replied,
                      sms_opted_out,
                      booking_requested,
                      booking_created,
                      booking_uid,
                      bench_gate_passed,
                      icp_segment,
                      segment_confidence,
                      ai_maturity_score,
                      outbound_variant,
                      last_unanswered_question,
                      qualification_json,
                      memory_json,
                      updated_at
                    )
                    values (
                      %(thread_id)s,
                      %(last_channel)s,
                      %(last_inbound_at)s,
                      %(last_outbound_at)s,
                      %(email_replied)s,
                      %(sms_replied)s,
                      %(sms_opted_out)s,
                      %(booking_requested)s,
                      %(booking_created)s,
                      %(booking_uid)s,
                      %(bench_gate_passed)s,
                      %(icp_segment)s,
                      %(segment_confidence)s,
                      %(ai_maturity_score)s,
                      %(outbound_variant)s,
                      %(last_unanswered_question)s,
                      %(qualification_json)s::jsonb,
                      %(memory_json)s::jsonb,
                      %(updated_at)s
                    )
                    on conflict (thread_id) do update set
                      last_channel = excluded.last_channel,
                      last_inbound_at = excluded.last_inbound_at,
                      last_outbound_at = excluded.last_outbound_at,
                      email_replied = excluded.email_replied,
                      sms_replied = excluded.sms_replied,
                      sms_opted_out = excluded.sms_opted_out,
                      booking_requested = excluded.booking_requested,
                      booking_created = excluded.booking_created,
                      booking_uid = excluded.booking_uid,
                      bench_gate_passed = excluded.bench_gate_passed,
                      icp_segment = excluded.icp_segment,
                      segment_confidence = excluded.segment_confidence,
                      ai_maturity_score = excluded.ai_maturity_score,
                      outbound_variant = excluded.outbound_variant,
                      last_unanswered_question = excluded.last_unanswered_question,
                      qualification_json = excluded.qualification_json,
                      memory_json = excluded.memory_json,
                      updated_at = excluded.updated_at
                    """,
                    {
                        **state,
                        "thread_id": thread_id,
                        "qualification_json": json.dumps(
                            state.get("qualification_json") or {}, ensure_ascii=False
                        ),
                        "memory_json": json.dumps(
                            state.get("memory_json") or {}, ensure_ascii=False
                        ),
                    },
                )
            conn.commit()

    def fetch_state(self, *, thread_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with get_conn() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("select * from conversation_state where thread_id = %s", (thread_id,))
                return cur.fetchone()
