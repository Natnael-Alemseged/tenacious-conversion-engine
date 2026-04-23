from datetime import UTC, datetime
from re import fullmatch
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

_E164_FROM = r"^\+[1-9]\d{1,14}$"
_TO_MAX = 32

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

    from_number: str = Field(
        min_length=1,
        max_length=20,
        description="Sender in E.164 (e.g. +251911000000).",
    )
    to: str = Field(default="", max_length=_TO_MAX)
    text: str = Field(min_length=1, max_length=4096)
    date: str = Field(default="", max_length=64)
    message_id: str = Field(default="", max_length=128)

    @field_validator("from_number", "to", "text", "date", "message_id", mode="before")
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("from_number")
    @classmethod
    def _from_e164(cls, value: str) -> str:
        if fullmatch(_E164_FROM, value) is None:
            raise ValueError(
                "from_number must be E.164: +, country code, subscriber number "
                "(max 15 digits after +)."
            )
        return value

    @field_validator("to")
    @classmethod
    def _to_destination(cls, value: str) -> str:
        if not value:
            return value
        if fullmatch(r"^[\d+]{1,32}$", value) is None:
            raise ValueError(
                "to must be empty or a digits-only destination (optional leading +), max 32 chars."
            )
        return value


class DiscoveryCallBookingRequest(BaseModel):
    attendee_name: str
    attendee_email: EmailStr
    start: str
    timezone: str = "UTC"
    length_in_minutes: int = 30
    attendee_phone: str | None = None
    metadata: dict[str, str] | None = None
