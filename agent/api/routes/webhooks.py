from fastapi import APIRouter, Request

from agent.core.config import settings
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent
from agent.storage.suppression import SmsSuppressionStore
from agent.workflows.lead_orchestrator import LeadOrchestrator

router = APIRouter()
orchestrator = LeadOrchestrator()
STOP_KEYWORDS = {"STOP", "UNSUB", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
HELP_KEYWORDS = {"HELP"}


def _suppression_store() -> SmsSuppressionStore:
    return SmsSuppressionStore(settings.sms_suppression_path)


@router.post("/email")
def inbound_email(event: InboundEmailEvent) -> dict[str, str]:
    orchestrator.handle_email(event)
    return {"status": "accepted"}


@router.post("/sms")
async def inbound_sms(request: Request) -> dict[str, str]:
    # Africa's Talking sends application/x-www-form-urlencoded with "from" as a field name.
    form = await request.form()
    event = InboundSmsEvent(
        from_number=form.get("from", ""),
        to=form.get("to", ""),
        text=form.get("text", ""),
        date=form.get("date", ""),
        message_id=form.get("id", ""),
    )

    message = event.text.strip().upper()
    store = _suppression_store()

    if message in STOP_KEYWORDS:
        store.suppress(event.from_number)
        return {
            "status": "suppressed",
            "message": "You have been unsubscribed. Reply START to opt back in.",
        }

    if message == "START":
        store.unsuppress(event.from_number)
        return {
            "status": "resubscribed",
            "message": "You are opted back in and can receive scheduling messages again.",
        }

    if message in HELP_KEYWORDS:
        return {
            "status": "help",
            "message": "Reply STOP to unsubscribe or START to opt back in.",
        }

    if store.is_suppressed(event.from_number):
        return {
            "status": "ignored",
            "message": "Number is currently unsubscribed.",
        }

    orchestrator.handle_sms(event)
    return {"status": "accepted"}
