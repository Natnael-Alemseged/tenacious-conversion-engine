"""Retry and error typing for discovery-call booking → HubSpot writebacks."""

from __future__ import annotations

import errno
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger(__name__)


class BookingCrmWritebackError(Exception):
    """Cal.com booking succeeded but persisting booking metadata to CRM failed.

    Callers should treat the calendar booking as real (avoid double-booking the
    same slot without reconciliation) while repairing CRM state out of band.
    """

    def __init__(
        self,
        *,
        booking: dict[str, Any],
        contact_identifier: str,
        attempts: int,
        failures: list[Exception],
    ) -> None:
        self.booking = booking
        self.contact_identifier = contact_identifier
        self.attempts = attempts
        self.failures = failures
        last = failures[-1]
        msg = (
            f"CRM writeback failed after {attempts} attempt(s) for "
            f"{contact_identifier!r}: {type(last).__name__}: {last}"
        )
        super().__init__(msg)


@dataclass(frozen=True)
class CrmWritebackOutcome:
    hubspot_result: dict[str, Any]
    attempts: int


def _is_transient_crm_writeback_failure(exc: Exception) -> bool:
    """Heuristic for HubSpot MCP / stdio transport flakes and thread timeouts."""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionError)):
        return True
    if isinstance(exc, OSError) and exc.errno in {
        errno.EPIPE,
        errno.ECONNRESET,
        errno.ETIMEDOUT,
        errno.EAGAIN,
    }:
        return True
    return False


def upsert_contact_with_booking_retries(
    upsert: Callable[[], dict[str, Any]],
    *,
    booking: dict[str, Any],
    contact_identifier: str,
    max_attempts: int = 3,
    base_delay_sec: float = 0.75,
) -> CrmWritebackOutcome:
    """Run CRM upsert with exponential backoff on transient failures."""
    failures: list[Exception] = []
    for attempt in range(1, max_attempts + 1):
        try:
            result = upsert()
            return CrmWritebackOutcome(hubspot_result=result, attempts=attempt)
        except Exception as exc:
            failures.append(exc)
            is_last = attempt >= max_attempts
            transient = _is_transient_crm_writeback_failure(exc)
            _log.warning(
                "booking_crm_writeback_attempt",
                extra={
                    "bcw_metric": "booking.crm_writeback",
                    "bcw_outcome": "retry" if transient and not is_last else "failure",
                    "bcw_attempt": str(attempt),
                    "bcw_max_attempts": str(max_attempts),
                    "bcw_transient": "true" if transient else "false",
                    "bcw_error_type": type(exc).__name__,
                    "bcw_contact_identifier": contact_identifier[:255],
                },
                exc_info=exc,
            )
            if is_last or not transient:
                raise BookingCrmWritebackError(
                    booking=booking,
                    contact_identifier=contact_identifier,
                    attempts=attempt,
                    failures=failures,
                ) from exc
            delay = base_delay_sec * (2 ** (attempt - 1))
            time.sleep(delay)

    raise AssertionError("unreachable")  # pragma: no cover
