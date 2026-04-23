from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

EmailEventType = Literal[
    "email.replied",
    "email.bounced",
    "email.complained",
    "email.delivery_delayed",
    "email.delivered",
    "email.sent",
]


class InboundEmailEvent(BaseModel):
    """Inbound email webhook payload — covers replies and Resend delivery events."""

    event_type: EmailEventType = "email.replied"
    from_email: EmailStr
    to: str = ""
    subject: str = ""
    body: str = ""
    message_id: str = ""
    in_reply_to: str = ""
    bounce_type: str = ""
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InboundSmsEvent(BaseModel):
    """Africa's Talking inbound SMS — parsed from form-encoded POST."""

    from_number: str
    to: str = ""
    text: str
    date: str = ""
    message_id: str = ""


class DiscoveryCallBookingRequest(BaseModel):
    attendee_name: str
    attendee_email: EmailStr
    start: str
    timezone: str = "UTC"
    length_in_minutes: int = 30
    attendee_phone: str | None = None
    metadata: dict[str, str] | None = None
