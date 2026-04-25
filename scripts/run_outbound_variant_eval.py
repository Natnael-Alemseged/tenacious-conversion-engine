from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from agent.integrations.resend_email import ResendClient
from agent.models.webhooks import InboundEmailEvent
from agent.workflows.lead_orchestrator import LeadOrchestrator


def _now() -> datetime:
    return datetime.now(UTC)


def _fake_outbound_email(
    orchestrator: LeadOrchestrator, *, to_email: str, company: str, variant: str
) -> str:
    result = orchestrator.send_outbound_email(
        to_email=to_email,
        company_name=company,
        signal_summary="Synthetic signal summary for outbound-variant eval.",
        icp_segment=2,
        ai_maturity_score=1,
        confidence=0.7,
        segment_confidence=0.7,
        bench_to_brief_gate_passed=True,
        idempotency_key=f"act5:{variant}:{to_email}",
        outbound_variant=variant,
    )
    return str(result.get("id") or "")


def _fake_inbound_reply(
    orchestrator: LeadOrchestrator, *, from_email: str, in_reply_to: str
) -> None:
    event = InboundEmailEvent(
        event_type="email.replied",
        from_email=from_email,
        to="outreach@tenacious.example",
        subject="Re: quick thought",
        body="Thanks — can you send a couple times to talk? Thursday works.",
        message_id=f"inbound-{from_email}",
        in_reply_to=in_reply_to,
        received_at=_now(),
    )
    orchestrator.handle_email(event)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-variant", type=int, default=25)
    args = parser.parse_args()

    def _mock_send(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": f"mock-{uuid.uuid4().hex[:12]}"})

    resend = ResendClient(transport=httpx.MockTransport(_mock_send))

    class _HubSpotStub:
        def upsert_contact(
            self,
            identifier: str,
            source: str,
            properties: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {"id": f"hs-{identifier}"}

    class _CalStub:
        def create_booking(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"data": {"uid": f"cal-{uuid.uuid4().hex[:8]}"}, "status": "success"}

    orchestrator = LeadOrchestrator(resend=resend, hubspot=_HubSpotStub(), calcom=_CalStub())

    # Generate two equal cohorts.
    for i in range(args.per_variant):
        email = f"prospect+cg{i}@example.com"
        msg_id = _fake_outbound_email(
            orchestrator,
            to_email=email,
            company="NovaCure Analytics",
            variant="competitive_gap",
        )
        _fake_inbound_reply(orchestrator, from_email=email, in_reply_to=msg_id)

    for i in range(args.per_variant):
        email = f"prospect+gen{i}@example.com"
        msg_id = _fake_outbound_email(
            orchestrator, to_email=email, company="NovaCure Analytics", variant="generic"
        )
        # Simulate no reply for half the cohort to create a measurable delta baseline.
        if i % 2 == 0:
            _fake_inbound_reply(orchestrator, from_email=email, in_reply_to=msg_id)

    # Backdate timestamps for deterministic “within 14 days” logic if needed later.
    # Currently, events are written with now() timestamps; the extractor uses that.

    print("Outbound variant eval run complete. See eval/runs/outbound/events.jsonl.")


if __name__ == "__main__":
    main()
