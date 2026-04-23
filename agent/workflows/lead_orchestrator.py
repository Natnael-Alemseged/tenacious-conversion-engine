from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.integrations.africastalking_sms import AfricasTalkingSmsClient
from agent.integrations.calcom import CalComClient
from agent.integrations.hubspot import HubSpotClient
from agent.integrations.langfuse import LangfuseClient
from agent.integrations.resend_email import ResendClient
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class LeadOrchestrator:
    def __init__(
        self,
        hubspot: HubSpotClient | None = None,
        calcom: CalComClient | None = None,
        langfuse: LangfuseClient | None = None,
        resend: ResendClient | None = None,
        sms: AfricasTalkingSmsClient | None = None,
    ) -> None:
        self.hubspot = hubspot or HubSpotClient()
        self.calcom = calcom or CalComClient()
        self.langfuse = langfuse or LangfuseClient()
        self.resend = resend or ResendClient()
        self.sms = sms or AfricasTalkingSmsClient()

    def handle_email(self, event: InboundEmailEvent) -> dict[str, Any]:
        enrichment_props = {
            "lead_source": "inbound_email_reply",
            "last_email_reply_at": event.received_at.isoformat(),
            "last_email_subject": event.subject,
            "email_replied": "true",
            "enrichment_timestamp": _now_iso(),
        }
        with self.langfuse.trace_workflow("handle_email", event.model_dump(mode="json")):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={"identifier": event.from_email, "source": "email"},
            ) as span:
                result = self.hubspot.upsert_contact(
                    identifier=event.from_email,
                    source="email",
                    properties=enrichment_props,
                )
                if span:
                    span.update(output=result)
                return result

    def handle_email_bounce(self, event: InboundEmailEvent) -> dict[str, Any]:
        props = {
            "email_bounce_type": event.bounce_type or event.event_type,
            "email_bounced_at": event.received_at.isoformat(),
            "enrichment_timestamp": _now_iso(),
        }
        with self.langfuse.trace_workflow("handle_email_bounce", event.model_dump(mode="json")):
            return self.hubspot.upsert_contact(
                identifier=event.from_email,
                source="email_bounce",
                properties=props,
            )

    def handle_sms(self, event: InboundSmsEvent) -> dict[str, Any]:
        enrichment_props = {
            "lead_source": "inbound_sms_reply",
            "last_sms_reply_text": event.text[:255],
            "sms_replied": "true",
            "enrichment_timestamp": _now_iso(),
        }
        with self.langfuse.trace_workflow("handle_sms", event.model_dump()):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={"identifier": event.from_number, "source": "sms"},
            ) as span:
                result = self.hubspot.upsert_contact(
                    identifier=event.from_number,
                    source="sms",
                    properties=enrichment_props,
                )
                if span:
                    span.update(output=result)
                return result

    def send_outbound_email(
        self,
        *,
        to_email: str,
        company_name: str,
        signal_summary: str,
        icp_segment: int | None = None,
        ai_maturity_score: int | None = None,
    ) -> dict[str, Any]:
        subject = f"{company_name}: quick note"
        html = (
            "<p>Hi there,</p>"
            f"<p>I took a quick look at {company_name} and found a relevant signal:</p>"
            f"<p>{signal_summary}</p>"
            "<p>If helpful, I can send over a short qualification brief "
            "and a few scheduling options.</p>"
        )
        enrichment_props: dict[str, Any] = {
            "lead_source": "outbound_email",
            "last_outbound_email_at": _now_iso(),
            "enrichment_timestamp": _now_iso(),
        }
        if icp_segment is not None:
            enrichment_props["icp_segment"] = str(icp_segment)
        if ai_maturity_score is not None:
            enrichment_props["ai_maturity_score"] = str(ai_maturity_score)

        with self.langfuse.trace_workflow(
            "send_outbound_email",
            {"to_email": to_email, "company_name": company_name},
        ):
            with self.langfuse.span("resend.send_email", input={"to_email": to_email}) as span:
                result = self.resend.send_email(to_email=to_email, subject=subject, html=html)
                if span:
                    span.update(output=result)
            self.hubspot.upsert_contact(
                identifier=to_email,
                source="outbound_email",
                properties=enrichment_props,
            )
            return result

    def send_warm_lead_sms(
        self,
        *,
        to_phone: str,
        company_name: str,
        scheduling_hint: str,
        prior_email_replied: bool,
    ) -> dict[str, Any]:
        """Send an SMS scheduling nudge. Only valid for warm leads who replied by email."""
        if not prior_email_replied:
            raise ValueError(
                "SMS is reserved for warm leads who have replied by email. "
                "Use send_outbound_email for first contact."
            )
        message = (
            f"{company_name}: following up on your email reply. "
            f"{scheduling_hint} Reply to confirm a time."
        )
        with self.langfuse.trace_workflow(
            "send_warm_lead_sms",
            {"to_phone": to_phone, "company_name": company_name},
        ):
            with self.langfuse.span(
                "africastalking.send_sms",
                input={"to_phone": to_phone, "message": message},
            ) as span:
                result = self.sms.send_sms(to_phone=to_phone, message=message)
                if span:
                    span.update(output=result)
                return result

    def book_discovery_call(
        self,
        *,
        attendee_name: str,
        attendee_email: str,
        start: str,
        timezone: str = "UTC",
        length_in_minutes: int = 30,
        attendee_phone: str | None = None,
        icp_segment: int | None = None,
        enrichment_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "start": start,
            "timezone": timezone,
            "length_in_minutes": length_in_minutes,
        }
        with self.langfuse.trace_workflow("book_discovery_call", payload):
            with self.langfuse.span("calcom.create_booking", input=payload) as span:
                booking = self.calcom.create_booking(
                    name=attendee_name,
                    email=attendee_email,
                    start=start,
                    timezone=timezone,
                    length_in_minutes=length_in_minutes,
                    phone_number=attendee_phone,
                    metadata=metadata,
                )
                if span:
                    span.update(output=booking)

            # Write booking confirmation back to HubSpot so the two integrations are linked.
            booking_data = booking.get("data", booking)
            hs_props: dict[str, Any] = {
                "discovery_call_booked": "true",
                "discovery_call_start": start,
                "discovery_call_booking_uid": str(booking_data.get("uid", "")),
                "discovery_call_booked_at": _now_iso(),
                "enrichment_timestamp": _now_iso(),
            }
            if icp_segment is not None:
                hs_props["icp_segment"] = str(icp_segment)
            if enrichment_summary:
                hs_props["enrichment_summary"] = enrichment_summary[:1000]

            with self.langfuse.span(
                "hubspot.upsert_contact_post_booking",
                input={"identifier": attendee_email},
            ) as span:
                hs_result = self.hubspot.upsert_contact(
                    identifier=attendee_email,
                    source="calcom_booking",
                    properties=hs_props,
                )
                if span:
                    span.update(output=hs_result)

            return booking
