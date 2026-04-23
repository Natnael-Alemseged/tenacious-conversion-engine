import logging

import httpx
from fastapi import APIRouter, HTTPException

from agent.models.webhooks import DiscoveryCallBookingRequest
from agent.workflows.booking_crm_writeback import BookingCrmWritebackError
from agent.workflows.lead_orchestrator import LeadOrchestrator

router = APIRouter()
orchestrator = LeadOrchestrator()
_log = logging.getLogger(__name__)


def _route_log_extra(
    *,
    outcome: str,
    status_code: int,
    error_type: str = "",
) -> dict[str, str]:
    return {
        "api_component": "bookings",
        "api_metric": "bookings.discovery_call.request",
        "api_route": "bookings.discovery_call",
        "api_outcome": outcome,
        "api_status_code": str(status_code),
        "api_error_type": error_type,
    }


def _route_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, BookingCrmWritebackError):
        booking_data = exc.booking.get("data", exc.booking)
        return HTTPException(
            status_code=502,
            detail={
                "message": (
                    "The calendar booking was created, but syncing booking details to the CRM "
                    f"failed after {exc.attempts} attempt(s). Reconcile the contact in the CRM "
                    "manually; avoid blindly rebooking the same slot without checking Cal.com."
                ),
                "crm_writeback": {
                    "contact_identifier": exc.contact_identifier,
                    "attempts": exc.attempts,
                    "last_error": f"{type(exc.failures[-1]).__name__}: {exc.failures[-1]}",
                    "errors": [f"{type(e).__name__}: {e}" for e in exc.failures],
                },
                "booking": {
                    "uid": booking_data.get("uid"),
                    "status": exc.booking.get("status"),
                },
            },
        )
    if isinstance(exc, httpx.HTTPStatusError):
        detail = (
            f"Upstream booking provider returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:300]}"
        )
        return HTTPException(status_code=502, detail=detail)
    if isinstance(exc, httpx.RequestError):
        return HTTPException(
            status_code=503,
            detail=f"Booking provider is unreachable: {exc}",
        )
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/discovery-call")
def book_discovery_call(request: DiscoveryCallBookingRequest) -> dict:
    try:
        result = orchestrator.book_discovery_call(
            attendee_name=request.attendee_name,
            attendee_email=request.attendee_email,
            start=request.start,
            timezone=request.timezone,
            length_in_minutes=request.length_in_minutes,
            attendee_phone=request.attendee_phone,
            metadata=request.metadata,
        )
        _log.info(
            "bookings.discovery_call",
            extra=_route_log_extra(outcome="success", status_code=200),
        )
        return result
    except Exception as exc:
        mapped = _route_error(exc)
        _log.error(
            "bookings.discovery_call",
            extra=_route_log_extra(
                outcome="failure",
                status_code=mapped.status_code,
                error_type=type(exc).__name__,
            ),
            exc_info=exc,
        )
        raise mapped from exc
