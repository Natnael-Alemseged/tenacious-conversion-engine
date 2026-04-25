import logging
import threading
from email.utils import parseaddr
from typing import Any

import httpx
import resend
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from agent.core.config import settings
from agent.integrations.africastalking_sms import AfricasTalkingSendError
from agent.integrations.hubspot import HubSpotMcpError
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent
from agent.storage.conversations import ConversationStore
from agent.storage.suppression import SmsSuppressionStore
from agent.workflows.lead_orchestrator import LeadOrchestrator
from agent.workflows.thread_state import recompute_state

router = APIRouter()
orchestrator = LeadOrchestrator()
conversations = ConversationStore()
_log = logging.getLogger(__name__)
STOP_KEYWORDS = {"STOP", "UNSUB", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
HELP_KEYWORDS = {"HELP"}
_RECENT_EMAIL_EVENTS_MAX = 512
_recent_email_events: dict[str, None] = {}
_recent_email_events_order: list[str] = []
_recent_email_events_lock = threading.Lock()
_RECENT_SMS_EVENTS_MAX = 512
_recent_sms_events: dict[str, None] = {}
_recent_sms_events_order: list[str] = []

BOUNCE_EVENT_TYPES = {"email.bounced", "email.complained", "email.delivery_delayed"}
IGNORED_EMAIL_EVENT_TYPES = {"email.sent", "email.delivered", "email.opened", "email.clicked"}


def _suppression_store() -> SmsSuppressionStore:
    return SmsSuppressionStore(settings.sms_suppression_path)


def _route_log_extra(
    *,
    route: str,
    outcome: str,
    status_code: int,
    error_type: str = "",
    provider_kind: str = "",
) -> dict[str, str]:
    return {
        "api_component": "webhooks",
        "api_metric": f"{route}.request",
        "api_route": route,
        "api_outcome": outcome,
        "api_status_code": str(status_code),
        "api_error_type": error_type,
        "api_provider_kind": provider_kind,
    }


def _route_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, HubSpotMcpError):
        # HubSpot transport flakes should look retriable (503) rather than
        # "our server crashed" (500).
        # Keep 502 for real upstream HTTP statuses; keep 503 for MCP/transport flakiness.
        status = 502 if exc.error_kind == "http_status" else 503
        headers = {"Retry-After": "5"} if status == 503 else None
        return HTTPException(
            status_code=status,
            detail=f"HubSpot integration error ({exc.error_kind}): {exc.detail[:500]}",
            headers=headers,
        )
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


def _verify_resend_webhook(payload: str, request: Request) -> None:
    if not settings.resend_webhook_verify:
        return
    if not settings.resend_webhook_signing_secret:
        return
    try:
        resend.Webhooks.verify(
            {
                "payload": payload,
                "webhook_secret": settings.resend_webhook_signing_secret,
                "headers": {
                    "id": request.headers.get("svix-id", ""),
                    "timestamp": request.headers.get("svix-timestamp", ""),
                    "signature": request.headers.get("svix-signature", ""),
                },
            }
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Resend webhook signature: {exc}",
        ) from exc


def _parse_email_address(raw: str) -> str:
    _, email = parseaddr(raw)
    return email or raw


def _normalize_resend_event(raw: dict[str, Any]) -> InboundEmailEvent:
    event_type = str(raw.get("type") or "")
    data = raw.get("data")
    if not event_type or not isinstance(data, dict):
        raise ValueError("Unsupported Resend webhook payload: expected top-level type and data.")

    from_email = _parse_email_address(str(data.get("from") or ""))
    to_field = data.get("to") or []
    to_value = (
        ",".join(str(item) for item in to_field) if isinstance(to_field, list) else str(to_field)
    )
    subject = str(data.get("subject") or "")
    message_id = str(data.get("message_id") or data.get("email_id") or "")
    received_at = data.get("created_at") or raw.get("created_at")
    body = ""

    if event_type == "email.received":
        email_id = str(data.get("email_id") or "")
        if not email_id:
            raise ValueError("Resend email.received event is missing data.email_id.")
        received = orchestrator.resend.get_received_email(email_id)
        body = str(received.get("text") or received.get("html") or "")
        message_id = str(received.get("message_id") or message_id)
        subject = str(received.get("subject") or subject)
        to_received = received.get("to")
        if isinstance(to_received, list):
            to_value = ",".join(str(item) for item in to_received)
        elif to_received:
            to_value = str(to_received)
        from_email = _parse_email_address(str(received.get("from") or from_email))

    return InboundEmailEvent(
        event_type="email.replied" if event_type == "email.received" else event_type,
        from_email=from_email,
        to=to_value,
        subject=subject,
        body=body,
        message_id=message_id,
        in_reply_to=str(data.get("in_reply_to") or ""),
        bounce_type=str(data.get("bounce_type") or ""),
        received_at=received_at,
    )


def _email_event_dedupe_key(event: InboundEmailEvent) -> str:
    if not event.message_id:
        return ""
    return f"{event.event_type}:{event.message_id}"


def _remember_email_event(key: str) -> bool:
    if not key:
        return False
    with _recent_email_events_lock:
        if key in _recent_email_events:
            return True
        _recent_email_events[key] = None
        _recent_email_events_order.append(key)
        if len(_recent_email_events_order) > _RECENT_EMAIL_EVENTS_MAX:
            oldest = _recent_email_events_order.pop(0)
            _recent_email_events.pop(oldest, None)
        return False


def _sms_event_dedupe_key(event: InboundSmsEvent) -> str:
    if not event.message_id:
        return ""
    return f"sms:{event.message_id}"


def _remember_sms_event(key: str) -> bool:
    if not key:
        return False
    with _recent_email_events_lock:
        if key in _recent_sms_events:
            return True
        _recent_sms_events[key] = None
        _recent_sms_events_order.append(key)
        if len(_recent_sms_events_order) > _RECENT_SMS_EVENTS_MAX:
            oldest = _recent_sms_events_order.pop(0)
            _recent_sms_events.pop(oldest, None)
        return False


async def _parse_email_event(request: Request) -> tuple[str, InboundEmailEvent | None]:
    payload = await request.body()
    text = payload.decode("utf-8")
    _verify_resend_webhook(text, request)
    raw = await request.json()

    if "event_type" in raw and "from_email" in raw:
        return str(raw.get("event_type") or "email.replied"), InboundEmailEvent.model_validate(raw)

    if "type" in raw and "data" in raw:
        event_type = str(raw.get("type") or "")
        if event_type in IGNORED_EMAIL_EVENT_TYPES:
            return event_type, None
        return event_type, _normalize_resend_event(raw)

    raise ValueError("Unsupported email webhook payload format.")


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
async def inbound_email(request: Request) -> dict[str, str]:
    try:
        event_type, event = await _parse_email_event(request)
    except HTTPException:
        raise
    except ValidationError as exc:
        _log.error(
            "webhooks.email",
            extra=_route_log_extra(
                route="webhooks.email",
                outcome="failure",
                status_code=422,
                error_type=type(exc).__name__,
            ),
            exc_info=exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        status = _route_error(exc).status_code
        _log.error(
            "webhooks.email",
            extra=_route_log_extra(
                route="webhooks.email",
                outcome="failure",
                status_code=status,
                error_type=type(exc).__name__,
            ),
            exc_info=exc,
        )
        raise _route_error(exc) from exc

    if event is None:
        _log.info(
            "webhooks.email",
            extra=_route_log_extra(
                route="webhooks.email",
                outcome="success",
                status_code=200,
            ),
        )
        return {"status": "ignored", "event_type": event_type}

    if event.event_type in BOUNCE_EVENT_TYPES:
        try:
            orchestrator.handle_email_bounce(event)
        except Exception as exc:
            _log.error(
                "webhooks.email",
                extra=_route_log_extra(
                    route="webhooks.email",
                    outcome="failure",
                    status_code=500,
                    error_type=type(exc).__name__,
                ),
                exc_info=exc,
            )
            raise _route_error(exc) from exc
        _log.info(
            "webhooks.email",
            extra=_route_log_extra(
                route="webhooks.email",
                outcome="success",
                status_code=200,
            ),
        )
        return {"status": "bounce_recorded", "event_type": event.event_type}

    dedupe_key = _email_event_dedupe_key(event)
    if _remember_email_event(dedupe_key):
        _log.info(
            "webhooks.email",
            extra=_route_log_extra(
                route="webhooks.email",
                outcome="success",
                status_code=200,
            ),
        )
        return {"status": "duplicate", "event_type": event.event_type}

    try:
        orchestrator.handle_email(event)
    except Exception as exc:
        status = _route_error(exc).status_code
        _log.error(
            "webhooks.email",
            extra=_route_log_extra(
                route="webhooks.email",
                outcome="failure",
                status_code=status,
                error_type=type(exc).__name__,
            ),
            exc_info=exc,
        )
        raise _route_error(exc) from exc
    _log.info(
        "webhooks.email",
        extra=_route_log_extra(
            route="webhooks.email",
            outcome="success",
            status_code=200,
        ),
    )
    return {"status": "accepted"}


@router.post("/sms")
async def inbound_sms(request: Request) -> dict[str, str]:
    # Africa's Talking sends application/x-www-form-urlencoded with "from" as a field name.
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type == "application/json":
        _log.warning(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="failure",
                status_code=415,
                error_type="UnsupportedMediaType",
            ),
        )
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
        _log.warning(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="failure",
                status_code=422,
                error_type=type(exc).__name__,
            ),
        )
        raise _sms_validation_http_exception(exc) from exc

    message = event.text.strip().upper()
    store = _suppression_store()

    if message in STOP_KEYWORDS:
        store.suppress(event.from_number)
        if conversations.enabled:
            resolved = conversations.resolve_thread_for_sms(from_phone=event.from_number)
            if resolved:
                conversations.insert_event(
                    thread_id=resolved.thread_id,
                    event_type="opt_out",
                    payload={
                        "channel": "sms",
                        "source": "webhooks.sms",
                        "message_id": event.message_id,
                    },
                )
                prior = conversations.fetch_state(thread_id=resolved.thread_id)
                msgs = conversations.fetch_recent_messages(thread_id=resolved.thread_id, limit=200)
                evs = conversations.fetch_events(thread_id=resolved.thread_id, limit=200)
                conversations.upsert_state(
                    thread_id=resolved.thread_id,
                    state=recompute_state(messages=msgs, events=evs, prior_state=prior),
                )
        _log.info(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="success",
                status_code=200,
            ),
        )
        return {
            "status": "suppressed",
            "message": "You have been unsubscribed. Reply START to opt back in.",
        }

    if message == "START":
        store.unsuppress(event.from_number)
        if conversations.enabled:
            resolved = conversations.resolve_thread_for_sms(from_phone=event.from_number)
            if resolved:
                conversations.insert_event(
                    thread_id=resolved.thread_id,
                    event_type="opt_in",
                    payload={
                        "channel": "sms",
                        "source": "webhooks.sms",
                        "message_id": event.message_id,
                    },
                )
                prior = conversations.fetch_state(thread_id=resolved.thread_id)
                msgs = conversations.fetch_recent_messages(thread_id=resolved.thread_id, limit=200)
                evs = conversations.fetch_events(thread_id=resolved.thread_id, limit=200)
                conversations.upsert_state(
                    thread_id=resolved.thread_id,
                    state=recompute_state(messages=msgs, events=evs, prior_state=prior),
                )
        _log.info(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="success",
                status_code=200,
            ),
        )
        return {
            "status": "resubscribed",
            "message": "You are opted back in and can receive scheduling messages again.",
        }

    if message in HELP_KEYWORDS:
        _log.info(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="success",
                status_code=200,
            ),
        )
        return {
            "status": "help",
            "message": "Reply STOP to unsubscribe or START to opt back in.",
        }

    if store.is_suppressed(event.from_number):
        _log.info(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="success",
                status_code=200,
            ),
        )
        return {
            "status": "ignored",
            "message": "Number is currently unsubscribed.",
        }

    dedupe_key = _sms_event_dedupe_key(event)
    if _remember_sms_event(dedupe_key):
        _log.info(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="success",
                status_code=200,
            ),
        )
        return {"status": "duplicate"}

    try:
        orchestrator.handle_sms(event)
    except Exception as exc:
        mapped = _sms_route_error(exc)
        provider_kind = ""
        if isinstance(mapped.detail, dict):
            provider_kind = str(mapped.detail.get("error", {}).get("provider", {}).get("kind", ""))
        _log.error(
            "webhooks.sms",
            extra=_route_log_extra(
                route="webhooks.sms",
                outcome="failure",
                status_code=mapped.status_code,
                error_type=type(exc).__name__,
                provider_kind=provider_kind,
            ),
            exc_info=exc,
        )
        raise _sms_route_error(exc) from exc
    _log.info(
        "webhooks.sms",
        extra=_route_log_extra(
            route="webhooks.sms",
            outcome="success",
            status_code=200,
        ),
    )
    return {"status": "accepted"}
