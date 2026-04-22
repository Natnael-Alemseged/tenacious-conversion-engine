from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, Field


class InboundEmailEvent(BaseModel):
    """Generic inbound email reply payload."""
    from_email: EmailStr
    to: str = ""
    subject: str
    body: str
    message_id: str = ""
    in_reply_to: str = ""
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InboundSmsEvent(BaseModel):
    """Africa's Talking inbound SMS — parsed from form-encoded POST."""
    from_number: str
    to: str = ""
    text: str
    date: str = ""
    message_id: str = ""
