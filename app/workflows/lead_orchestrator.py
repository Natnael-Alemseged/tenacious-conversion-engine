from app.integrations.calcom import CalComClient
from app.integrations.hubspot import HubSpotClient
from app.integrations.langfuse import LangfuseClient
from app.models.webhooks import InboundEmailEvent, InboundSmsEvent


class LeadOrchestrator:
    def __init__(self) -> None:
        self.hubspot = HubSpotClient()
        self.calcom = CalComClient()
        self.langfuse = LangfuseClient()

    def handle_email(self, event: InboundEmailEvent) -> None:
        # TODO: run enrichment pipeline → LLM agent → reply via Resend
        self.langfuse.trace("inbound_email", payload=event.model_dump())
        self.hubspot.upsert_contact(identifier=event.from_email, source="email")

    def handle_sms(self, event: InboundSmsEvent) -> None:
        # TODO: run enrichment pipeline → LLM agent → reply via Africa's Talking
        self.langfuse.trace("inbound_sms", payload=event.model_dump())
        self.hubspot.upsert_contact(identifier=event.from_number, source="sms")
