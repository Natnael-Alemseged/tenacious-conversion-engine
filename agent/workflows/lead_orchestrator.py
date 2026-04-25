from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from act5.autoresponder import classify_autoresponder, load_heuristics
from act5.outbound_events import (
    append_outbound_event,
    append_reply_classification,
    append_thread_outcome,
    now_iso,
)
from agent.core.config import settings
from agent.enrichment.ai_maturity import confidence_phrasing
from agent.enrichment.pipeline import run as run_enrichment_pipeline
from agent.enrichment.schemas import HiringSignalBrief
from agent.integrations.africastalking_sms import AfricasTalkingSmsClient
from agent.integrations.calcom import CalComClient
from agent.integrations.hubspot import HubSpotClient
from agent.integrations.langfuse import LangfuseClient
from agent.integrations.resend_email import ResendClient, ResendSendError
from agent.models.webhooks import InboundEmailEvent, InboundSmsEvent
from agent.workflows.booking_crm_writeback import upsert_contact_with_booking_retries
from agent.workflows.channel_handoff import (
    OutboundRoutingConfig,
    should_send_email_reply,
    should_send_sms_reply,
)

DownstreamEventHandler = (
    Callable[[str, dict[str, Any], InboundEmailEvent | InboundSmsEvent], None] | None
)
EnrichmentRunner = Callable[..., HiringSignalBrief]

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


def _handle_email_log_extra(
    *,
    phase: str,
    outcome: str,
    identifier: str,
    company_name: str = "",
    icp_segment: int | None = None,
    segment_confidence: float | None = None,
    booking_requested: bool | None = None,
    requested_booking_start: str = "",
    booking_created: bool | None = None,
    reply_status: str = "",
    reply_reason: str = "",
) -> dict[str, object]:
    extra = _workflow_log_extra(
        workflow="handle_email",
        outcome=outcome,
        phase=phase,
        identifier=identifier,
        channel="email",
    )
    extra.update(
        {
            "he_company_name": company_name[:255],
            "he_icp_segment": "" if icp_segment is None else str(icp_segment),
            "he_segment_confidence": (
                "" if segment_confidence is None else f"{segment_confidence:.3f}"
            ),
            "he_booking_requested": (
                "" if booking_requested is None else ("true" if booking_requested else "false")
            ),
            "he_requested_booking_start": requested_booking_start[:64],
            "he_booking_created": (
                "" if booking_created is None else ("true" if booking_created else "false")
            ),
            "he_reply_status": reply_status,
            "he_reply_reason": reply_reason,
        }
    )
    return extra


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


def _company_name_from_email(email: str) -> str:
    domain = _email_domain(email)
    if not domain:
        return "your team"
    root = domain.split(".")[0].replace("-", " ").replace("_", " ").strip()
    return root.title() if root else "your team"


def _attendee_name_from_email(email: str) -> str:
    local = str(email).split("@", 1)[0]
    name = local.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return name.title() if name else "Prospect"


def _booking_intent(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "book",
            "calendar",
            "cal.com",
            "call",
            "demo",
            "meet",
            "meeting",
            "schedule",
            "time to talk",
        )
    )


def _booking_start_from_text(text: str) -> str | None:
    match = re.search(
        r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})\b",
        text,
    )
    if match is None:
        return None
    start = match.group(0)
    if re.fullmatch(r".*T\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", start):
        start = start.replace("Z", ":00Z")
        if not start.endswith("Z"):
            start = f"{start[:-6]}:00{start[-6:]}"
    return start


def _calcom_booking_url() -> str:
    username = (settings.calcom_username or "").strip()
    if not username:
        return ""
    return f"https://cal.com/{username}"


def _signal_summary_from_brief(brief: HiringSignalBrief) -> str:
    parts: list[str] = []
    if brief.signals.funding.data:
        parts.append("public funding signals")
    if brief.signals.layoffs.data:
        parts.append("restructuring signals")
    open_roles = brief.signals.job_posts.data.get("open_roles", 0)
    if open_roles:
        parts.append(f"{open_roles} open roles in the current hiring signal")
    if brief.signals.ai_maturity.score:
        parts.append(f"AI maturity score {brief.signals.ai_maturity.score}/3")
    if parts:
        return "We found " + ", ".join(parts) + "."
    return "We found limited public signal, so this is best treated as an exploratory fit check."


def _reply_subject(subject: str) -> str:
    cleaned = subject.strip()
    if not cleaned:
        return "Re: your note"
    if cleaned.lower().startswith("re:"):
        return cleaned
    return f"Re: {cleaned}"


def _extract_hiring_focus(text: str) -> str:
    lowered = text.lower()
    matches: list[str] = []
    for token, label in (
        ("fastapi", "FastAPI"),
        ("python", "Python"),
        ("backend", "backend"),
        ("data engineer", "data engineering"),
        ("data engineers", "data engineering"),
        ("frontend", "frontend"),
        ("react", "React"),
        ("node", "Node.js"),
        ("devops", "DevOps"),
    ):
        if token in lowered and label not in matches:
            matches.append(label)
    if not matches:
        return "engineering hiring"
    if len(matches) == 1:
        return f"{matches[0]} hiring"
    if len(matches) == 2:
        return f"{matches[0]} and {matches[1]} hiring"
    return f"{', '.join(matches[:-1])}, and {matches[-1]} hiring"


def _build_inbound_sms_reply(*, event: InboundSmsEvent) -> str:
    focus = _extract_hiring_focus(event.text)
    lowered = event.text.lower()
    if _booking_intent(event.text):
        booking_url = _calcom_booking_url()
        if booking_url:
            return (
                "Happy to help. You can pick a slot here: "
                f"{booking_url}. If you'd rather, share a preferred time + timezone overlap."
            )
        return (
            "Happy to help. Share a preferred time, timezone overlap, and rough role count, "
            "or say 'schedule' and I can send next-step options."
        )
    if any(token in lowered for token in ("price", "pricing", "rate", "cost", "budget")):
        return (
            "I can help with that. Send the role count, seniority level, timezone overlap, "
            "and target start date and I'll narrow the recommendation."
        )
    return (
        f"Thanks for reaching out about {focus}. "
        "If helpful, text the role count, seniority level, timezone overlap, "
        "and target start date and I can tighten the recommendation."
    )


def _build_inbound_email_reply(
    *,
    event: InboundEmailEvent,
    company_name: str,
    booking_requested: bool,
    booking_result: dict[str, Any] | None,
    requested_booking_start: str | None,
) -> tuple[str, str, str]:
    name = _attendee_name_from_email(str(event.from_email)).split(" ", 1)[0]
    focus = _extract_hiring_focus(f"{event.subject}\n{event.body}")
    greeting = f"Hi {name},"
    opener = f"Thanks for reaching out about {focus} at {company_name}."
    if booking_result is not None and requested_booking_start:
        middle = f"I've booked the call for {requested_booking_start} UTC."
        closing = (
            "If you want to make the conversation more concrete, send the role count, "
            "seniority, timezone overlap, and target start date and I'll tailor the prep."
        )
    elif booking_requested:
        if settings.calcom_username:
            middle = (
                f"Happy to set up time. You can pick a slot here: "
                f"https://cal.com/{settings.calcom_username}."
            )
        else:
            middle = "Happy to set up time. I can send over a few scheduling options."
        closing = (
            "If you already know the role count, seniority mix, timezone overlap, "
            "or target start date, send that over and I can make the next step "
            "more specific."
        )
    else:
        middle = (
            "If helpful, send the role count, seniority level, timezone overlap, and target "
            "start date and I can reply with a tighter recommendation."
        )
        closing = "I can also send a few scheduling options if you'd rather talk it through live."
    html = f"<p>{greeting}</p><p>{opener}</p><p>{middle}</p><p>{closing}</p>"
    text = f"{greeting}\n\n{opener}\n\n{middle}\n\n{closing}"
    return _reply_subject(event.subject), html, text


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
        enrichment_runner: EnrichmentRunner | None = None,
    ) -> None:
        self.hubspot = hubspot or HubSpotClient()
        self.calcom = calcom or CalComClient()
        self.langfuse = langfuse or LangfuseClient()
        self._autoresponder_heuristics = load_heuristics()
        self.resend = resend or ResendClient()
        self.sms = sms or AfricasTalkingSmsClient()
        self.reply_handler = reply_handler
        self.bounce_handler = bounce_handler
        self.enrichment_runner = enrichment_runner or run_enrichment_pipeline

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
        company_name = _company_name_from_email(str(event.from_email))
        _log.info(
            "handle_email",
            extra=_handle_email_log_extra(
                phase="start",
                outcome="success",
                identifier=str(event.from_email),
                company_name=company_name,
            ),
        )
        brief = self.enrichment_runner(company_name=company_name)
        signal_summary = _signal_summary_from_brief(brief)
        inbound_text = f"{event.subject}\n{event.body}"
        booking_requested = _booking_intent(inbound_text)
        requested_booking_start = _booking_start_from_text(inbound_text)
        _log.info(
            "handle_email",
            extra=_handle_email_log_extra(
                phase="enrichment_complete",
                outcome="success",
                identifier=str(event.from_email),
                company_name=brief.company_name,
                icp_segment=brief.icp_segment,
                segment_confidence=brief.segment_confidence,
                booking_requested=booking_requested,
                requested_booking_start=requested_booking_start or "",
            ),
        )
        enrichment_props = {
            "lead_source": "inbound_email_reply",
            "last_email_reply_at": event.received_at.isoformat(),
            "last_email_subject": event.subject,
            "email_replied": "true",
            "enrichment_timestamp": _now_iso(),
            "icp_segment": str(brief.icp_segment),
            "segment_confidence": f"{brief.segment_confidence:.3f}",
            "overall_confidence": f"{brief.overall_confidence:.3f}",
            "overall_confidence_weighted": f"{brief.overall_confidence_weighted:.3f}",
            "ai_maturity_score": str(brief.signals.ai_maturity.score),
            "ai_maturity_confidence": f"{brief.signals.ai_maturity.confidence:.3f}",
            "bench_to_brief_gate_passed": str(
                brief.signals.bench.data.bench_to_brief_gate_passed
            ).lower(),
            "enrichment_summary": signal_summary[:1000],
            "honesty_flags": ", ".join(brief.honesty_flags)[:1000],
        }
        with self.langfuse.trace_workflow("handle_email", event.model_dump(mode="json")):
            with self.langfuse.span(
                "hubspot.upsert_contact",
                input={
                    "identifier": event.from_email,
                    "source": "email",
                    "icp_segment": brief.icp_segment,
                    "segment_confidence": brief.segment_confidence,
                },
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
                hubspot_contact_id = str(result.get("id") or "")
                bench_gate_passed = brief.signals.bench.data.bench_to_brief_gate_passed
                exploratory_reply_ok = brief.icp_segment == 0 or brief.segment_confidence < 0.6
                routing = OutboundRoutingConfig(
                    outbound_enabled=settings.outbound_enabled,
                    outbound_sink_email=settings.outbound_sink_email or "",
                    outbound_sink_phone=settings.outbound_sink_phone or "",
                )
                reply_decision = should_send_email_reply(
                    routing=routing,
                    bench_gate_passed=bench_gate_passed,
                    exploratory_reply_ok=exploratory_reply_ok,
                )
                booking_result: dict[str, Any] | None = None
                if booking_requested and requested_booking_start and bench_gate_passed:
                    booking_result = self.book_discovery_call(
                        attendee_name=_attendee_name_from_email(str(event.from_email)),
                        attendee_email=str(event.from_email),
                        start=requested_booking_start,
                        timezone="UTC",
                        icp_segment=brief.icp_segment,
                        enrichment_summary=signal_summary,
                        metadata={
                            "source": "inbound_email",
                            "message_id": event.message_id,
                            "icp_segment": str(brief.icp_segment),
                        },
                        bench_to_brief_gate_passed=bench_gate_passed,
                    )
                    result["booking"] = booking_result
                    _log.info(
                        "handle_email",
                        extra=_handle_email_log_extra(
                            phase="booking_created",
                            outcome="success",
                            identifier=str(event.from_email),
                            company_name=brief.company_name,
                            icp_segment=brief.icp_segment,
                            segment_confidence=brief.segment_confidence,
                            booking_requested=booking_requested,
                            requested_booking_start=requested_booking_start,
                            booking_created=True,
                        ),
                    )
                elif booking_requested:
                    booking_reason = (
                        "missing_booking_start"
                        if not requested_booking_start
                        else "bench_to_brief_gate_failed"
                    )
                    _log.info(
                        "handle_email",
                        extra=_handle_email_log_extra(
                            phase="booking_skipped",
                            outcome="success",
                            identifier=str(event.from_email),
                            company_name=brief.company_name,
                            icp_segment=brief.icp_segment,
                            segment_confidence=brief.segment_confidence,
                            booking_requested=booking_requested,
                            requested_booking_start=requested_booking_start or "",
                            booking_created=False,
                            reply_reason=booking_reason,
                        ),
                    )
                if reply_decision.action == "send":
                    reply_subject, reply_html, reply_text = _build_inbound_email_reply(
                        event=event,
                        company_name=brief.company_name,
                        booking_requested=booking_requested,
                        booking_result=booking_result,
                        requested_booking_start=requested_booking_start,
                    )
                    reference_message_ids = [
                        ref for ref in (event.in_reply_to, event.message_id) if ref
                    ]
                    reply_result = self.send_outbound_email(
                        to_email=str(event.from_email),
                        company_name=brief.company_name,
                        signal_summary=signal_summary,
                        icp_segment=brief.icp_segment,
                        ai_maturity_score=brief.signals.ai_maturity.score,
                        confidence=brief.segment_confidence,
                        bench_to_brief_gate_passed=True,
                        subject_override=reply_subject,
                        html_override=reply_html,
                        text_override=reply_text,
                        reply_to_message_id=event.message_id or None,
                        reference_message_ids=reference_message_ids or None,
                        idempotency_key=(
                            f"inbound-reply:{event.message_id}" if event.message_id else None
                        ),
                    )
                    result["reply"] = reply_result
                    _log.info(
                        "handle_email",
                        extra=_handle_email_log_extra(
                            phase="reply_sent",
                            outcome="success",
                            identifier=str(event.from_email),
                            company_name=brief.company_name,
                            icp_segment=brief.icp_segment,
                            segment_confidence=brief.segment_confidence,
                            booking_requested=booking_requested,
                            requested_booking_start=requested_booking_start or "",
                            booking_created=booking_result is not None,
                            reply_status="sent",
                        ),
                    )
                else:
                    result["reply"] = {
                        "status": "skipped",
                        "reason": reply_decision.reason,
                    }
                    _log.info(
                        "handle_email",
                        extra=_handle_email_log_extra(
                            phase="reply_skipped",
                            outcome="success",
                            identifier=str(event.from_email),
                            company_name=brief.company_name,
                            icp_segment=brief.icp_segment,
                            segment_confidence=brief.segment_confidence,
                            booking_requested=booking_requested,
                            requested_booking_start=requested_booking_start or "",
                            booking_created=booking_result is not None,
                            reply_status="skipped",
                            reply_reason=reply_decision.reason,
                        ),
                    )
                result["enrichment"] = {
                    "company_name": brief.company_name,
                    "icp_segment": brief.icp_segment,
                    "segment_confidence": brief.segment_confidence,
                    "ai_maturity_score": brief.signals.ai_maturity.score,
                    "bench_to_brief_gate_passed": (
                        brief.signals.bench.data.bench_to_brief_gate_passed
                    ),
                    "booking_requested": booking_requested,
                    "requested_booking_start": requested_booking_start,
                    "booking_created": booking_result is not None,
                }

                # Act V measurement: record inbound email + autoresponder classification.
                resend_thread_key = event.in_reply_to or event.message_id
                inbound_class = classify_autoresponder(
                    subject=event.subject,
                    body=event.body,
                    heuristics=self._autoresponder_heuristics,
                )
                append_outbound_event(
                    {
                        "event_type": "inbound_email",
                        "sent_at": now_iso(),
                        "channel": "email",
                        "hubspot_contact_id": hubspot_contact_id,
                        "resend_thread_key": resend_thread_key,
                        "outbound_variant": "",
                        "message_id": event.message_id,
                        "idempotency_key": "",
                        "intended_to": str(event.to),
                        "routed_to": str(event.to),
                    }
                )
                append_reply_classification(
                    {
                        "hubspot_contact_id": hubspot_contact_id,
                        "resend_thread_key": resend_thread_key,
                        "inbound_message_id": event.message_id,
                        "classified_at": now_iso(),
                        "is_autoresponder": inbound_class.is_autoresponder,
                        "matched_on": inbound_class.matched_on,
                        "matched_pattern": inbound_class.matched_pattern,
                    }
                )
                append_thread_outcome(
                    {
                        "recorded_at": now_iso(),
                        "hubspot_contact_id": hubspot_contact_id,
                        "resend_thread_key": resend_thread_key,
                        "booking_created": bool(booking_result is not None),
                        "booking_requested": bool(booking_requested),
                        "reply_status": str(result.get("reply", {}).get("status", "")),
                        "reply_reason": str(result.get("reply", {}).get("reason", "")),
                    }
                )
                self._emit_reply_handler(channel="email", result=result, event=event)
                _log.info(
                    "handle_email",
                    extra=_handle_email_log_extra(
                        phase="complete",
                        outcome="success",
                        identifier=str(event.from_email),
                        company_name=brief.company_name,
                        icp_segment=brief.icp_segment,
                        segment_confidence=brief.segment_confidence,
                        booking_requested=booking_requested,
                        requested_booking_start=requested_booking_start or "",
                        booking_created=booking_result is not None,
                        reply_status=str(result["reply"].get("status", "")),
                        reply_reason=str(result["reply"].get("reason", "")),
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
                routing = OutboundRoutingConfig(
                    outbound_enabled=settings.outbound_enabled,
                    outbound_sink_email=settings.outbound_sink_email or "",
                    outbound_sink_phone=settings.outbound_sink_phone or "",
                )
                sms_decision = should_send_sms_reply(
                    routing=routing,
                    prior_email_replied=True,
                    sms_suppressed=False,
                )
                if sms_decision.action == "send":
                    reply_text = _build_inbound_sms_reply(event=event)
                    reply_result = self.send_warm_lead_sms(
                        to_phone=event.from_number,
                        company_name=_company_name_from_email(f"team@{event.to}.example")
                        if event.to
                        else "your team",
                        scheduling_hint=reply_text,
                        prior_email_replied=True,
                        message_override=reply_text,
                    )
                    result["reply"] = reply_result
                else:
                    result["reply"] = {
                        "status": "skipped",
                        "reason": sms_decision.reason,
                    }
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
        segment_confidence: float | None = None,
        crunchbase_id: str | None = None,
        bench_to_brief_gate_passed: bool = True,
        subject_override: str | None = None,
        html_override: str | None = None,
        text_override: str | None = None,
        reply_to_message_id: str | None = None,
        reference_message_ids: list[str] | None = None,
        idempotency_key: str | None = None,
        outbound_variant: str = "generic",
    ) -> dict[str, Any]:
        seg = icp_segment if icp_segment in _SUBJECT_SUFFIXES else 0
        subject = _build_subject(company_name, seg)
        if subject_override is not None:
            subject = subject_override
        phrasing_score = segment_confidence if segment_confidence is not None else confidence
        phrasing = confidence_phrasing(phrasing_score) if phrasing_score is not None else "hedged"
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

        html = html_override or (
            f"<p>Hi there,</p>"
            f"<p>{opener}</p>"
            f"<p>{signal_line}</p>"
            "<p>If helpful, I can send over a short qualification brief "
            "and a few scheduling options.</p>"
        )
        text = text_override
        headers: dict[str, str] = {}
        if reply_to_message_id:
            headers["In-Reply-To"] = reply_to_message_id
        if reference_message_ids:
            refs = [ref for ref in reference_message_ids if ref]
            if refs:
                headers["References"] = " ".join(refs)
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
            "segment_confidence": segment_confidence,
            "outbound_variant": outbound_variant,
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
                        text=text,
                        tags={
                            "tenacious_draft": "true",
                            "outbound_mode": str(outbound_audit["outbound_mode"]),
                        },
                        headers=headers or None,
                        idempotency_key=idempotency_key,
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
                    hs_result = self.hubspot.upsert_contact(
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

            hubspot_contact_id = str((hs_result or {}).get("id") or "")
            resend_thread_key = reply_to_message_id or str(result.get("id") or "")
            append_outbound_event(
                {
                    "event_type": "outbound_email",
                    "sent_at": now_iso(),
                    "channel": "email",
                    "hubspot_contact_id": hubspot_contact_id,
                    "resend_thread_key": resend_thread_key,
                    "outbound_variant": outbound_variant,
                    "message_id": str(result.get("id") or ""),
                    "idempotency_key": idempotency_key or "",
                    "intended_to": to_email,
                    "routed_to": routed_to,
                }
            )

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
        message_override: str | None = None,
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
        message = message_override or (
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
