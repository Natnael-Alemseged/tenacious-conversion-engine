from fastapi import APIRouter

from app.models.webhooks import DiscoveryCallBookingRequest
from app.workflows.lead_orchestrator import LeadOrchestrator

router = APIRouter()
orchestrator = LeadOrchestrator()


@router.post("/discovery-call")
def book_discovery_call(request: DiscoveryCallBookingRequest) -> dict:
    return orchestrator.book_discovery_call(
        attendee_name=request.attendee_name,
        attendee_email=request.attendee_email,
        start=request.start,
        timezone=request.timezone,
        length_in_minutes=request.length_in_minutes,
        attendee_phone=request.attendee_phone,
        metadata=request.metadata,
    )
