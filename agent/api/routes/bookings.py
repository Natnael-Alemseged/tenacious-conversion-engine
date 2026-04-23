import httpx
from fastapi import APIRouter, HTTPException

from agent.models.webhooks import DiscoveryCallBookingRequest
from agent.workflows.booking_crm_writeback import BookingCrmWritebackError
from agent.workflows.lead_orchestrator import LeadOrchestrator

router = APIRouter()
orchestrator = LeadOrchestrator()


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
        return orchestrator.book_discovery_call(
            attendee_name=request.attendee_name,
            attendee_email=request.attendee_email,
            start=request.start,
            timezone=request.timezone,
            length_in_minutes=request.length_in_minutes,
            attendee_phone=request.attendee_phone,
            metadata=request.metadata,
        )
    except Exception as exc:
        raise _route_error(exc) from exc
