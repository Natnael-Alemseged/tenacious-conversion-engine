from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from agent.core.config import settings
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent
from agent.storage.suppression import SmsSuppressionStore
from agent.workflows.lead_orchestrator import LeadOrchestrator

router = APIRouter()
orchestrator = LeadOrchestrator()
STOP_KEYWORDS = {"STOP", "UNSUB", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
HELP_KEYWORDS = {"HELP"}

BOUNCE_EVENT_TYPES = {"email.bounced", "email.complained", "email.delivery_delayed"}


def _suppression_store() -> SmsSuppressionStore:
    return SmsSuppressionStore(settings.sms_suppression_path)


@router.post("/email")
def inbound_email(event: InboundEmailEvent) -> dict[str, str]:
    if event.event_type in BOUNCE_EVENT_TYPES:
        orchestrator.handle_email_bounce(event)
        return {"status": "bounce_recorded", "event_type": event.event_type}

    try:
        orchestrator.handle_email(event)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "accepted"}


@router.post("/sms")
async def inbound_sms(request: Request) -> dict[str, str]:
    # Africa's Talking sends application/x-www-form-urlencoded with "from" as a field name.
    form = await request.form()
    try:
        event = InboundSmsEvent(
            from_number=form.get("from", ""),
            to=form.get("to", ""),
            text=form.get("text", ""),
            date=form.get("date", ""),
            message_id=form.get("id", ""),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

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

    try:
        orchestrator.handle_sms(event)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "accepted"}
