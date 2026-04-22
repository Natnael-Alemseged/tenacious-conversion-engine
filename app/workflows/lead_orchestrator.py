from __future__ import annotations

from typing import Any

from app.integrations.africastalking_sms import AfricasTalkingSmsClient
from app.integrations.calcom import CalComClient
from app.integrations.hubspot import HubSpotClient
from app.integrations.langfuse import LangfuseClient
from app.integrations.resend_email import ResendClient
from app.models.webhooks import InboundEmailEvent, InboundSmsEvent


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
        with self.langfuse.trace_workflow("handle_email", event.model_dump()):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={"identifier": event.from_email, "source": "email"},
            ) as span:
                result = self.hubspot.upsert_contact(
                    identifier=event.from_email,
                    source="email",
                    properties={},
                )
                if span:
                    span.update(output=result)
                return result

    def handle_sms(self, event: InboundSmsEvent) -> dict[str, Any]:
        with self.langfuse.trace_workflow("handle_sms", event.model_dump()):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={"identifier": event.from_number, "source": "sms"},
            ) as span:
                result = self.hubspot.upsert_contact(
                    identifier=event.from_number,
                    source="sms",
                    properties={},
                )
                if span:
                    span.update(output=result)
                return result

    def send_follow_up_email(
        self,
        *,
        to_email: str,
        company_name: str,
        signal_summary: str,
    ) -> dict[str, Any]:
        subject = f"{company_name}: quick follow-up"
        html = (
            "<p>Hi there,</p>"
            f"<p>I took a quick look at {company_name} and found a relevant signal:</p>"
            f"<p>{signal_summary}</p>"
            "<p>If helpful, I can send over a short qualification brief "
            "and a few scheduling options.</p>"
        )
        with self.langfuse.trace_workflow(
            "send_follow_up_email",
            {"to_email": to_email, "company_name": company_name},
        ):
            with self.langfuse.span(
                "resend.send_email",
                input={"to_email": to_email, "subject": subject},
            ) as span:
                result = self.resend.send_email(
                    to_email=to_email,
                    subject=subject,
                    html=html,
                )
                if span:
                    span.update(output=result)
                return result

    def send_follow_up_sms(
        self,
        *,
        to_phone: str,
        company_name: str,
        scheduling_hint: str,
    ) -> dict[str, Any]:
        message = (
            f"{company_name}: quick follow-up. "
            f"{scheduling_hint} Reply if you'd like scheduling options."
        )
        with self.langfuse.trace_workflow(
            "send_follow_up_sms",
            {"to_phone": to_phone, "company_name": company_name},
        ):
            with self.langfuse.span(
                "africastalking.send_sms",
                input={"to_phone": to_phone, "message": message},
            ) as span:
                result = self.sms.send_sms(
                    to_phone=to_phone,
                    message=message,
                )
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
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "start": start,
            "timezone": timezone,
            "length_in_minutes": length_in_minutes,
        }
        with self.langfuse.trace_workflow("book_discovery_call", payload):
            with self.langfuse.span(
                "calcom.create_booking",
                input=payload,
            ) as span:
                result = self.calcom.create_booking(
                    name=attendee_name,
                    email=attendee_email,
                    start=start,
                    timezone=timezone,
                    length_in_minutes=length_in_minutes,
                    phone_number=attendee_phone,
                    metadata=metadata,
                )
                if span:
                    span.update(output=result)
                return result
