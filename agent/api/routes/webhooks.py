from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from agent.core.config import settings
from agent.integrations.africastalking_sms import AfricasTalkingSendError
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


def _route_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        detail = (
            f"Upstream integration returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:300]}"
        )
        return HTTPException(status_code=502, detail=detail)
    if isinstance(exc, httpx.RequestError):
        return HTTPException(
            status_code=503,
            detail=f"Upstream integration is unreachable: {exc}",
        )
    return HTTPException(status_code=500, detail=str(exc))


def _sms_error_payload(
    *,
    code: str,
    message: str,
    field_errors: list[dict[str, Any]] | None = None,
    provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if field_errors is not None:
        body["error"]["field_errors"] = field_errors
    if provider is not None:
        body["error"]["provider"] = provider
    return body


def _sms_route_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=400,
            detail=_sms_error_payload(code="invalid_request", message=str(exc)),
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=502,
            detail=_sms_error_payload(
                code="upstream_http_error",
                message="A downstream HTTP provider returned an error status.",
                provider={
                    "kind": "http",
                    "status_code": exc.response.status_code,
                    "body_preview": exc.response.text[:300],
                },
            ),
        )
    if isinstance(exc, httpx.RequestError):
        return HTTPException(
            status_code=503,
            detail=_sms_error_payload(
                code="upstream_unreachable",
                message="A downstream provider could not be reached.",
                provider={"kind": "http", "detail": str(exc)},
            ),
        )
    if isinstance(exc, AfricasTalkingSendError):
        if exc.status_code == 0:
            return HTTPException(
                status_code=503,
                detail=_sms_error_payload(
                    code="sms_provider_unreachable",
                    message="Africa's Talking could not be reached.",
                    provider={"name": "africastalking", "detail": str(exc)},
                ),
            )
        return HTTPException(
            status_code=502,
            detail=_sms_error_payload(
                code="sms_provider_error",
                message="Africa's Talking returned an error response.",
                provider={
                    "name": "africastalking",
                    "status_code": exc.status_code,
                    "body_preview": str(exc)[:500],
                },
            ),
        )
    return HTTPException(
        status_code=500,
        detail=_sms_error_payload(code="internal_error", message="Unexpected error handling SMS."),
    )


def _sms_form_string(raw: Any, *, field: str) -> str:
    if raw is None:
        return ""
    if isinstance(raw, UploadFile):
        raise HTTPException(
            status_code=422,
            detail=_sms_error_payload(
                code="invalid_form_field",
                message=f"Field {field!r} must be a plain string, not a file upload.",
                field_errors=[
                    {
                        "field": field,
                        "code": "unexpected_file",
                        "message": "File uploads are not allowed.",
                    }
                ],
            ),
        )
    return str(raw).strip()


def _sms_validation_http_exception(exc: ValidationError) -> HTTPException:
    field_errors: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        field = ".".join(str(x) for x in loc) if loc else "payload"
        field_errors.append(
            {
                "field": field,
                "code": err.get("type", "validation_error"),
                "message": err.get("msg", "Invalid value."),
            }
        )
    return HTTPException(
        status_code=422,
        detail=_sms_error_payload(
            code="validation_error",
            message="Inbound SMS payload failed validation.",
            field_errors=field_errors,
        ),
    )


@router.post("/email")
def inbound_email(event: InboundEmailEvent) -> dict[str, str]:
    if event.event_type in BOUNCE_EVENT_TYPES:
        orchestrator.handle_email_bounce(event)
        return {"status": "bounce_recorded", "event_type": event.event_type}

    try:
        orchestrator.handle_email(event)
    except Exception as exc:
        raise _route_error(exc) from exc
    return {"status": "accepted"}


@router.post("/sms")
async def inbound_sms(request: Request) -> dict[str, str]:
    # Africa's Talking sends application/x-www-form-urlencoded with "from" as a field name.
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type == "application/json":
        raise HTTPException(
            status_code=415,
            detail=_sms_error_payload(
                code="unsupported_media_type",
                message=(
                    "SMS webhook expects application/x-www-form-urlencoded or multipart/form-data."
                ),
            ),
        )

    form = await request.form()
    try:
        event = InboundSmsEvent(
            from_number=_sms_form_string(form.get("from"), field="from"),
            to=_sms_form_string(form.get("to"), field="to"),
            text=_sms_form_string(form.get("text"), field="text"),
            date=_sms_form_string(form.get("date"), field="date"),
            message_id=_sms_form_string(form.get("id"), field="id"),
        )
    except ValidationError as exc:
        raise _sms_validation_http_exception(exc) from exc

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
        raise _sms_route_error(exc) from exc
    return {"status": "accepted"}
