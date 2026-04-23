from __future__ import annotations

import errno
import logging

import pytest

from agent.workflows.booking_crm_writeback import (
    BookingCrmWritebackError,
    upsert_contact_with_booking_retries,
)


def test_writeback_retries_transient_then_succeeds(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "agent.workflows.booking_crm_writeback.time.sleep", lambda s: sleeps.append(s)
    )

    calls = {"n": 0}

    def upsert() -> dict:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("mcp slow")
        return {"id": "42"}

    outcome = upsert_contact_with_booking_retries(
        upsert,
        booking={"data": {"uid": "u1"}},
        contact_identifier="a@b.com",
        max_attempts=3,
        base_delay_sec=1.0,
    )

    assert outcome.hubspot_result == {"id": "42"}
    assert outcome.attempts == 3
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_writeback_no_retry_on_non_transient() -> None:
    def upsert() -> dict:
        raise ValueError("bad property")

    with pytest.raises(BookingCrmWritebackError) as ei:
        upsert_contact_with_booking_retries(
            upsert,
            booking={"data": {"uid": "u2"}},
            contact_identifier="x@y.com",
            max_attempts=3,
        )

    err = ei.value
    assert err.attempts == 1
    assert len(err.failures) == 1
    assert isinstance(err.failures[0], ValueError)


def test_writeback_exhausts_transient_retries(monkeypatch) -> None:
    monkeypatch.setattr("agent.workflows.booking_crm_writeback.time.sleep", lambda _s: None)

    def upsert() -> dict:
        raise BrokenPipeError()

    with pytest.raises(BookingCrmWritebackError) as ei:
        upsert_contact_with_booking_retries(
            upsert,
            booking={"data": {"uid": "u3"}},
            contact_identifier="p@q.com",
            max_attempts=2,
            base_delay_sec=0.01,
        )

    assert ei.value.attempts == 2
    assert len(ei.value.failures) == 2


def test_writeback_retries_on_errno_epipe(monkeypatch) -> None:
    monkeypatch.setattr("agent.workflows.booking_crm_writeback.time.sleep", lambda _s: None)
    n = 0

    def upsert() -> dict:
        nonlocal n
        n += 1
        if n == 1:
            exc = OSError("broken pipe")
            exc.errno = errno.EPIPE
            raise exc
        return {"ok": True}

    outcome = upsert_contact_with_booking_retries(
        upsert,
        booking={"data": {"uid": "u4"}},
        contact_identifier="z@z.com",
    )

    assert outcome.attempts == 2
    assert outcome.hubspot_result == {"ok": True}


def test_writeback_logs_retry_attempt(caplog, monkeypatch) -> None:
    monkeypatch.setattr("agent.workflows.booking_crm_writeback.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def upsert() -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("slow")
        return {"ok": True}

    with caplog.at_level(logging.WARNING, logger="agent.workflows.booking_crm_writeback"):
        outcome = upsert_contact_with_booking_retries(
            upsert,
            booking={"data": {"uid": "u5"}},
            contact_identifier="trace@example.com",
            max_attempts=3,
        )

    assert outcome.attempts == 2
    records = [r for r in caplog.records if r.getMessage() == "booking_crm_writeback_attempt"]
    assert records
    assert records[-1].bcw_outcome == "retry"
    assert records[-1].bcw_attempt == "1"
    assert records[-1].bcw_transient == "true"
