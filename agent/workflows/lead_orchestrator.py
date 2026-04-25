from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent.core.config import settings
from agent.enrichment.ai_maturity import confidence_phrasing
from agent.integrations.africastalking_sms import AfricasTalkingSmsClient
from agent.integrations.calcom import CalComClient
from agent.integrations.hubspot import HubSpotClient
from agent.integrations.langfuse import LangfuseClient
from agent.integrations.resend_email import ResendClient, ResendSendError
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent
from agent.workflows.booking_crm_writeback import upsert_contact_with_booking_retries

DownstreamEventHandler = (
    Callable[[str, dict[str, Any], InboundEmailEvent | InboundSmsEvent], None] | None
)

_log = logging.getLogger(__name__)


def _email_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].lower()[:255]


def _segment_opener(company_name: str, segment: int, phrasing: str) -> str:
    """Return confidence-calibrated opener copy for outbound email."""
    direct_openers: dict[int, str] = {
        0: f"I came across {company_name} and wanted to reach out.",
        1: f"Congratulations on the recent funding — {company_name} is clearly in growth mode.",
        2: (
            "Teams navigating a restructure often find this is the right time "
            "to invest in automation."
        ),
        3: "New technical leadership often opens a window to re-evaluate the tooling stack.",
        4: f"I noticed {company_name}'s signals suggest room to accelerate AI adoption.",
    }
    hedged_openers: dict[int, str] = {
        0: f"I came across {company_name} and wanted to reach out.",
        1: (
            f"The recent funding signal suggests {company_name} may be evaluating how to "
            "scale engineering capacity."
        ),
        2: (
            "When a team is navigating restructuring signals, automation can be worth "
            "a careful look."
        ),
        3: (
            "A technical leadership change can be a useful moment to review tooling "
            "and delivery priorities."
        ),
        4: (
            f"Some public signals suggest {company_name} may be exploring where AI "
            "capability should mature next."
        ),
    }
    exploratory_openers: dict[int, str] = {
        0: f"I came across {company_name} and wanted to reach out.",
        1: (
            f"I saw a recent funding signal for {company_name}, but I do not want to "
            "over-read it. Is scaling engineering capacity actually a current priority?"
        ),
        2: (
            "I saw a restructuring signal, but I do not want to assume the operating "
            "context. Is automation part of the current cost or capacity conversation?"
        ),
        3: (
            "I saw a technical leadership signal, but I do not want to infer too much "
            "from it. Is the tooling stack under review right now?"
        ),
        4: (
            f"I saw a few AI-adjacent signals for {company_name}, but they may be early. "
            "Is AI delivery capacity something your team is actively evaluating?"
        ),
    }
    if phrasing == "direct":
        return direct_openers.get(segment, direct_openers[0])
    if phrasing == "hedged":
        return hedged_openers.get(segment, hedged_openers[0])
    return exploratory_openers.get(segment, exploratory_openers[0])


_SUBJECT_SUFFIXES: dict[int, str] = {
    0: ": quick thought",
    1: ": scaling after your recent raise",
    2: ": doing more with your current team",
    3: ": working with new technical leadership",
    4: ": closing the AI capability gap",
}
_SUBJECT_MAX_LEN: int = 60


def _build_subject(company_name: str, segment: int) -> str:
    suffix = _SUBJECT_SUFFIXES.get(segment, _SUBJECT_SUFFIXES[0])
    subject = company_name + suffix
    if len(subject) <= _SUBJECT_MAX_LEN:
        return subject
    max_company = _SUBJECT_MAX_LEN - len(suffix)
    if max_company >= 4:
        return company_name[:max_company].rstrip() + suffix
    return subject[: _SUBJECT_MAX_LEN - 1] + "…"


def _outbound_email_log_extra(
    *,
    outcome: str,
    phase: str,
    outbound_mode: str = "",
    intended_to: str = "",
    routed_to: str = "",
    icp_segment: int | None = None,
    ai_maturity_score: int | None = None,
    has_crunchbase: bool | None = None,
    phrasing: str = "",
    error_type: str = "",
    error_kind: str = "",
    http_status: int | None = None,
    hubspot_source: str = "",
) -> dict[str, object]:
    """Structured fields for log aggregation (keys avoid stdlib LogRecord collisions)."""
    return {
        "oe_component": "outbound_email",
        "oe_metric": "outbound_email.send",
        "oe_outcome": outcome,
        "oe_phase": phase,
        "oe_outbound_mode": outbound_mode,
        "oe_intended_email_domain": _email_domain(intended_to),
        "oe_routed_email_domain": _email_domain(routed_to),
        "oe_icp_segment": "" if icp_segment is None else str(icp_segment),
        "oe_ai_maturity_score": "" if ai_maturity_score is None else str(ai_maturity_score),
        "oe_has_crunchbase": ""
        if has_crunchbase is None
        else ("true" if has_crunchbase else "false"),
        "oe_phrasing": phrasing,
        "oe_error_type": error_type,
        "oe_error_kind": error_kind,
        "oe_http_status": "" if http_status is None else str(http_status),
        "oe_hubspot_source": hubspot_source,
    }


def _workflow_log_extra(
    *,
    workflow: str,
    outcome: str,
    phase: str,
    identifier: str = "",
    channel: str = "",
    error_type: str = "",
    error_kind: str = "",
    attempt_count: int | None = None,
) -> dict[str, object]:
    identifier_kind = "email" if "@" in identifier else ("phone" if identifier else "")
    return {
        "wf_component": "lead_orchestrator",
        "wf_metric": f"{workflow}.{phase}",
        "wf_workflow": workflow,
        "wf_outcome": outcome,
        "wf_phase": phase,
        "wf_channel": channel,
        "wf_identifier_kind": identifier_kind,
        "wf_identifier_suffix": identifier[-6:] if identifier else "",
        "wf_error_type": error_type,
        "wf_error_kind": error_kind,
        "wf_attempt_count": "" if attempt_count is None else str(attempt_count),
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _outbound_route(*, intended_to: str, channel: str) -> tuple[str, dict[str, Any]]:
    if settings.outbound_enabled:
        return intended_to, {
            "outbound_mode": "live",
            "draft": True,
            "intended_to": intended_to,
            "routed_to": intended_to,
            "reason": "outbound_enabled",
            "channel": channel,
        }

    sink = settings.outbound_sink_email if channel == "email" else settings.outbound_sink_phone
    if not sink:
        raise ValueError(
            f"Outbound is disabled and no sink is configured for channel={channel}. "
            f"Set OUTBOUND_SINK_{'EMAIL' if channel == 'email' else 'PHONE'}."
        )
    return sink, {
        "outbound_mode": "sink",
        "draft": True,
        "intended_to": intended_to,
        "routed_to": sink,
        "reason": "outbound_disabled",
        "channel": channel,
    }


def _require_bench_gate(*, bench_to_brief_gate_passed: bool, operation: str) -> None:
    if not bench_to_brief_gate_passed:
        raise ValueError(
            f"Bench-to-brief gate failed for {operation}. "
            "Do not commit Tenacious capacity until the bench summary shows a matching capability."
        )


class LeadOrchestrator:
    def __init__(
        self,
        hubspot: HubSpotClient | None = None,
        calcom: CalComClient | None = None,
        langfuse: LangfuseClient | None = None,
        resend: ResendClient | None = None,
        sms: AfricasTalkingSmsClient | None = None,
        reply_handler: DownstreamEventHandler = None,
        bounce_handler: DownstreamEventHandler = None,
    ) -> None:
        self.hubspot = hubspot or HubSpotClient()
        self.calcom = calcom or CalComClient()
        self.langfuse = langfuse or LangfuseClient()
        self.resend = resend or ResendClient()
        self.sms = sms or AfricasTalkingSmsClient()
        self.reply_handler = reply_handler
        self.bounce_handler = bounce_handler

    def register_reply_handler(self, handler: DownstreamEventHandler) -> None:
        self.reply_handler = handler

    def register_bounce_handler(self, handler: DownstreamEventHandler) -> None:
        self.bounce_handler = handler

    def _emit_reply_handler(
        self,
        *,
        channel: str,
        result: dict[str, Any],
        event: InboundEmailEvent | InboundSmsEvent,
    ) -> None:
        if self.reply_handler is not None:
            self.reply_handler(channel, result, event)

    def _emit_bounce_handler(
        self,
        *,
        result: dict[str, Any],
        event: InboundEmailEvent,
    ) -> None:
        if self.bounce_handler is not None:
            self.bounce_handler("email_bounce", result, event)

    def _log_workflow_failure(
        self,
        *,
        workflow: str,
        phase: str,
        identifier: str,
        channel: str = "",
        exc: Exception,
        attempt_count: int | None = None,
    ) -> None:
        _log.error(
            workflow,
            extra=_workflow_log_extra(
                workflow=workflow,
                outcome="failure",
                phase=phase,
                identifier=identifier,
                channel=channel,
                error_type=type(exc).__name__,
                error_kind=getattr(exc, "error_kind", ""),
                attempt_count=attempt_count,
            ),
            exc_info=exc,
        )

    def handle_email(self, event: InboundEmailEvent) -> dict[str, Any]:
        enrichment_props = {
            "lead_source": "inbound_email_reply",
            "last_email_reply_at": event.received_at.isoformat(),
            "last_email_subject": event.subject,
            "email_replied": "true",
            "enrichment_timestamp": _now_iso(),
        }
        with self.langfuse.trace_workflow("handle_email", event.model_dump(mode="json")):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={"identifier": event.from_email, "source": "email"},
            ) as span:
                try:
                    result = self.hubspot.upsert_contact(
                        identifier=event.from_email,
                        source="email",
                        properties=enrichment_props,
                    )
                except Exception as exc:
                    if span:
                        span.update(
                            output={
                                "ok": False,
                                "error_type": type(exc).__name__,
                                "message_excerpt": str(exc)[:500],
                            }
                        )
                    self._log_workflow_failure(
                        workflow="handle_email",
                        phase="hubspot",
                        identifier=event.from_email,
                        channel="email",
                        exc=exc,
                    )
                    raise
                if span:
                    span.update(output=result)
                self._emit_reply_handler(channel="email", result=result, event=event)
                _log.info(
                    "handle_email",
                    extra=_workflow_log_extra(
                        workflow="handle_email",
                        outcome="success",
                        phase="complete",
                        identifier=event.from_email,
                        channel="email",
                    ),
                )
                return result

    def handle_email_bounce(self, event: InboundEmailEvent) -> dict[str, Any]:
        props = {
            "email_bounce_type": event.bounce_type or event.event_type,
            "email_bounced_at": event.received_at.isoformat(),
            "enrichment_timestamp": _now_iso(),
        }
        with self.langfuse.trace_workflow("handle_email_bounce", event.model_dump(mode="json")):
            try:
                result = self.hubspot.upsert_contact(
                    identifier=event.from_email,
                    source="email_bounce",
                    properties=props,
                )
            except Exception as exc:
                self._log_workflow_failure(
                    workflow="handle_email_bounce",
                    phase="hubspot",
                    identifier=event.from_email,
                    channel="email",
                    exc=exc,
                )
                raise
            self._emit_bounce_handler(result=result, event=event)
            _log.info(
                "handle_email_bounce",
                extra=_workflow_log_extra(
                    workflow="handle_email_bounce",
                    outcome="success",
                    phase="complete",
                    identifier=event.from_email,
                    channel="email",
                ),
            )
            return result

    def handle_sms(self, event: InboundSmsEvent) -> dict[str, Any]:
        enrichment_props = {
            "lead_source": "inbound_sms_reply",
            "last_sms_reply_text": event.text[:255],
            "sms_replied": "true",
            "enrichment_timestamp": _now_iso(),
        }
        with self.langfuse.trace_workflow("handle_sms", event.model_dump()):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={"identifier": event.from_number, "source": "sms"},
            ) as span:
                try:
                    result = self.hubspot.upsert_contact(
                        identifier=event.from_number,
                        source="sms",
                        properties=enrichment_props,
                    )
                except Exception as exc:
                    if span:
                        span.update(
                            output={
                                "ok": False,
                                "error_type": type(exc).__name__,
                                "message_excerpt": str(exc)[:500],
                            }
                        )
                    self._log_workflow_failure(
                        workflow="handle_sms",
                        phase="hubspot",
                        identifier=event.from_number,
                        channel="sms",
                        exc=exc,
                    )
                    raise
                if span:
                    span.update(output=result)
                self._emit_reply_handler(channel="sms", result=result, event=event)
                _log.info(
                    "handle_sms",
                    extra=_workflow_log_extra(
                        workflow="handle_sms",
                        outcome="success",
                        phase="complete",
                        identifier=event.from_number,
                        channel="sms",
                    ),
                )
                return result

    def send_outbound_email(
        self,
        *,
        to_email: str,
        company_name: str,
        signal_summary: str,
        icp_segment: int | None = None,
        ai_maturity_score: int | None = None,
        confidence: float | None = None,
        crunchbase_id: str | None = None,
        bench_to_brief_gate_passed: bool = True,
    ) -> dict[str, Any]:
        seg = icp_segment if icp_segment in _SUBJECT_SUFFIXES else 0
        subject = _build_subject(company_name, seg)
        phrasing = confidence_phrasing(confidence) if confidence is not None else "hedged"
        opener = _segment_opener(company_name, seg, phrasing)

        try:
            _require_bench_gate(
                bench_to_brief_gate_passed=bench_to_brief_gate_passed,
                operation="outbound_email",
            )
        except ValueError as exc:
            _log.error(
                "outbound_email_send",
                extra=_outbound_email_log_extra(
                    outcome="failure",
                    phase="bench_gate",
                    intended_to=to_email,
                    error_type=type(exc).__name__,
                ),
                exc_info=exc,
            )
            raise

        try:
            routed_to, outbound_audit = _outbound_route(intended_to=to_email, channel="email")
        except ValueError as exc:
            _log.error(
                "outbound_email_send",
                extra=_outbound_email_log_extra(
                    outcome="failure",
                    phase="routing",
                    intended_to=to_email,
                    error_type=type(exc).__name__,
                ),
                exc_info=exc,
            )
            raise

        if phrasing == "direct":
            signal_line = signal_summary
        elif phrasing == "hedged":
            signal_line = f"Based on the signals we've seen: {signal_summary}"
        else:
            signal_line = (
                f"We noticed some early indicators that might be relevant — {signal_summary}. "
                "Is this on your radar?"
            )

        html = (
            f"<p>Hi there,</p>"
            f"<p>{opener}</p>"
            f"<p>{signal_line}</p>"
            "<p>If helpful, I can send over a short qualification brief "
            "and a few scheduling options.</p>"
        )
        enrichment_props: dict[str, Any] = {
            "lead_source": "outbound_email",
            "last_outbound_email_at": _now_iso(),
            "enrichment_timestamp": _now_iso(),
            "last_outbound_mode": outbound_audit["outbound_mode"],
            "last_outbound_draft": str(outbound_audit["draft"]).lower(),
            "last_outbound_intended_to": str(outbound_audit["intended_to"])[:255],
            "last_outbound_routed_to": str(outbound_audit["routed_to"])[:255],
        }
        if crunchbase_id:
            enrichment_props["crunchbase_id"] = crunchbase_id
        if icp_segment is not None:
            enrichment_props["icp_segment"] = str(icp_segment)
        if ai_maturity_score is not None:
            enrichment_props["ai_maturity_score"] = str(ai_maturity_score)

        trace_payload: dict[str, Any] = {
            "to_email": to_email,
            "company_name": company_name,
            "icp_segment": icp_segment,
            "ai_maturity_score": ai_maturity_score,
            "confidence": confidence,
        }
        with self.langfuse.trace_workflow("send_outbound_email", trace_payload):
            with self.langfuse.span(
                "resend.send_email",
                input={
                    "to_email": routed_to,
                    "outbound_audit": outbound_audit,
                    "crunchbase_id": crunchbase_id,
                },
            ) as span:
                try:
                    result = self.resend.send_email(
                        to_email=routed_to,
                        subject=subject,
                        html=html,
                        tags={
                            "tenacious_draft": "true",
                            "outbound_mode": str(outbound_audit["outbound_mode"]),
                        },
                    )
                except ResendSendError as exc:
                    if span:
                        span.update(
                            output={
                                "ok": False,
                                "error_kind": exc.error_kind,
                                "http_status": exc.status_code,
                                "detail_excerpt": (exc.detail or "")[:500],
                            }
                        )
                    _log.error(
                        "outbound_email_send",
                        extra=_outbound_email_log_extra(
                            outcome="failure",
                            phase="resend",
                            outbound_mode=str(outbound_audit["outbound_mode"]),
                            intended_to=to_email,
                            routed_to=routed_to,
                            icp_segment=icp_segment,
                            ai_maturity_score=ai_maturity_score,
                            has_crunchbase=crunchbase_id is not None,
                            phrasing=phrasing,
                            error_type=type(exc).__name__,
                            error_kind=exc.error_kind,
                            http_status=exc.status_code,
                        ),
                        exc_info=exc,
                    )
                    raise
                if span:
                    span.update(output=result)

            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={
                    "identifier": to_email,
                    "source": "outbound_email",
                    "outbound_audit": outbound_audit,
                },
            ) as hs_span:
                try:
                    self.hubspot.upsert_contact(
                        identifier=to_email,
                        source="outbound_email",
                        properties=enrichment_props,
                    )
                except Exception as exc:
                    if hs_span:
                        hs_span.update(
                            output={
                                "ok": False,
                                "error_type": type(exc).__name__,
                                "message_excerpt": str(exc)[:500],
                            }
                        )
                    _log.error(
                        "outbound_email_send",
                        extra=_outbound_email_log_extra(
                            outcome="failure",
                            phase="hubspot",
                            outbound_mode=str(outbound_audit["outbound_mode"]),
                            intended_to=to_email,
                            routed_to=routed_to,
                            icp_segment=icp_segment,
                            ai_maturity_score=ai_maturity_score,
                            has_crunchbase=crunchbase_id is not None,
                            phrasing=phrasing,
                            error_type=type(exc).__name__,
                            hubspot_source="outbound_email",
                        ),
                        exc_info=exc,
                    )
                    raise
                if hs_span:
                    hs_span.update(output={"ok": True})

            _log.info(
                "outbound_email_send",
                extra=_outbound_email_log_extra(
                    outcome="success",
                    phase="complete",
                    outbound_mode=str(outbound_audit["outbound_mode"]),
                    intended_to=to_email,
                    routed_to=routed_to,
                    icp_segment=icp_segment,
                    ai_maturity_score=ai_maturity_score,
                    has_crunchbase=crunchbase_id is not None,
                    phrasing=phrasing,
                    hubspot_source="outbound_email",
                ),
            )
            return result

    def send_warm_lead_sms(
        self,
        *,
        to_phone: str,
        company_name: str,
        scheduling_hint: str,
        prior_email_replied: bool,
        crunchbase_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an SMS scheduling nudge. Only valid for warm leads who replied by email."""
        if not prior_email_replied:
            raise ValueError(
                "SMS is reserved for warm leads who have replied by email. "
                "Use send_outbound_email for first contact."
            )
        try:
            routed_to, outbound_audit = _outbound_route(intended_to=to_phone, channel="sms")
        except ValueError as exc:
            self._log_workflow_failure(
                workflow="send_warm_lead_sms",
                phase="routing",
                identifier=to_phone,
                channel="sms",
                exc=exc,
            )
            raise
        message = (
            f"{company_name}: following up on your email reply. "
            f"{scheduling_hint} Reply to confirm a time."
        )
        with self.langfuse.trace_workflow(
            "send_warm_lead_sms",
            {"to_phone": to_phone, "company_name": company_name},
        ):
            with self.langfuse.span(
                "africastalking.send_sms",
                input={
                    "to_phone": routed_to,
                    "message": message,
                    "outbound_audit": outbound_audit,
                    "crunchbase_id": crunchbase_id,
                },
            ) as span:
                try:
                    result = self.sms.send_sms(to_phone=routed_to, message=message)
                except Exception as exc:
                    if span:
                        span.update(
                            output={
                                "ok": False,
                                "error_type": type(exc).__name__,
                                "error_kind": getattr(exc, "error_kind", ""),
                                "message_excerpt": str(exc)[:500],
                            }
                        )
                    self._log_workflow_failure(
                        workflow="send_warm_lead_sms",
                        phase="provider",
                        identifier=to_phone,
                        channel="sms",
                        exc=exc,
                    )
                    raise
                if span:
                    span.update(output=result)
            try:
                self.hubspot.upsert_contact(
                    identifier=to_phone,
                    source="outbound_sms",
                    properties={
                        "lead_source": "outbound_sms",
                        "last_outbound_sms_at": _now_iso(),
                        "enrichment_timestamp": _now_iso(),
                        "last_outbound_mode": outbound_audit["outbound_mode"],
                        "last_outbound_draft": str(outbound_audit["draft"]).lower(),
                        "last_outbound_intended_to": str(outbound_audit["intended_to"])[:255],
                        "last_outbound_routed_to": str(outbound_audit["routed_to"])[:255],
                        "crunchbase_id": crunchbase_id or "",
                    },
                )
            except Exception as exc:
                self._log_workflow_failure(
                    workflow="send_warm_lead_sms",
                    phase="hubspot",
                    identifier=to_phone,
                    channel="sms",
                    exc=exc,
                )
                raise
            _log.info(
                "send_warm_lead_sms",
                extra=_workflow_log_extra(
                    workflow="send_warm_lead_sms",
                    outcome="success",
                    phase="complete",
                    identifier=to_phone,
                    channel="sms",
                ),
            )
            return result

    def book_discovery_call(
        self,
        *,
        attendee_name: str,
        attendee_email: str,
        start: str,
        timezone: str = "UTC",
        length_in_minutes: int = 30,
        attendee_phone: str | None = None,
        icp_segment: int | None = None,
        enrichment_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        bench_to_brief_gate_passed: bool = True,
    ) -> dict[str, Any]:
        _require_bench_gate(
            bench_to_brief_gate_passed=bench_to_brief_gate_passed,
            operation="booking",
        )
        payload: dict[str, Any] = {
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "start": start,
            "timezone": timezone,
            "length_in_minutes": length_in_minutes,
        }
        with self.langfuse.trace_workflow("book_discovery_call", payload):
            with self.langfuse.span("calcom.create_booking", input=payload) as span:
                booking = self.calcom.create_booking(
                    name=attendee_name,
                    email=attendee_email,
                    start=start,
                    timezone=timezone,
                    length_in_minutes=length_in_minutes,
                    phone_number=attendee_phone,
                    metadata=metadata,
                )
                if span:
                    span.update(output=booking)
            booking_data = booking.get("data", booking)
            booking_uid = str(booking_data.get("uid", "")).strip()
            if not booking_uid:
                exc = ValueError("Cal.com booking response is missing a booking uid.")
                self._log_workflow_failure(
                    workflow="book_discovery_call",
                    phase="booking_response",
                    identifier=attendee_email,
                    channel="booking",
                    exc=exc,
                )
                raise exc

            hs_props: dict[str, Any] = {
                "discovery_call_booked": "true",
                "discovery_call_start": start,
                "discovery_call_booking_uid": booking_uid,
                "discovery_call_booked_at": _now_iso(),
                "enrichment_timestamp": _now_iso(),
            }
            if icp_segment is not None:
                hs_props["icp_segment"] = str(icp_segment)
            if enrichment_summary:
                hs_props["enrichment_summary"] = enrichment_summary[:1000]

            with self.langfuse.span(
                "hubspot.upsert_contact_post_booking",
                input={"identifier": attendee_email},
            ) as span:
                try:
                    outcome = upsert_contact_with_booking_retries(
                        lambda: self.hubspot.upsert_contact(
                            identifier=attendee_email,
                            source="calcom_booking",
                            properties=hs_props,
                        ),
                        booking=booking,
                        contact_identifier=attendee_email,
                    )
                except Exception as exc:
                    if span:
                        span.update(
                            output={
                                "ok": False,
                                "error_type": type(exc).__name__,
                                "message_excerpt": str(exc)[:500],
                            }
                        )
                    self._log_workflow_failure(
                        workflow="book_discovery_call",
                        phase="hubspot_writeback",
                        identifier=attendee_email,
                        channel="booking",
                        exc=exc,
                        attempt_count=getattr(exc, "attempts", None),
                    )
                    raise
                hs_payload = {
                    **outcome.hubspot_result,
                    "crm_writeback_attempts": outcome.attempts,
                }
                if span:
                    span.update(output=hs_payload)
            _log.info(
                "book_discovery_call",
                extra=_workflow_log_extra(
                    workflow="book_discovery_call",
                    outcome="success",
                    phase="complete",
                    identifier=attendee_email,
                    channel="booking",
                    attempt_count=outcome.attempts,
                ),
            )

            return booking
