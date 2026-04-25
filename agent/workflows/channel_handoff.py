from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Channel = Literal["email", "sms"]


@dataclass(frozen=True)
class OutboundRoutingConfig:
    outbound_enabled: bool
    outbound_sink_email: str
    outbound_sink_phone: str


@dataclass(frozen=True)
class ReplyDecision:
    action: Literal["send", "skip"]
    reason: str


def should_send_email_reply(
    *,
    routing: OutboundRoutingConfig,
    bench_gate_passed: bool,
    exploratory_reply_ok: bool,
) -> ReplyDecision:
    if not (routing.outbound_enabled or routing.outbound_sink_email):
        return ReplyDecision(action="skip", reason="outbound_disabled_without_sink")
    if bench_gate_passed or exploratory_reply_ok:
        return ReplyDecision(action="send", reason="ok")
    return ReplyDecision(action="skip", reason="bench_to_brief_gate_failed")


def should_send_sms_reply(
    *,
    routing: OutboundRoutingConfig,
    prior_email_replied: bool,
    sms_suppressed: bool,
) -> ReplyDecision:
    if sms_suppressed:
        return ReplyDecision(action="skip", reason="sms_suppressed")
    if not prior_email_replied:
        return ReplyDecision(action="skip", reason="warm_lead_gate_failed")
    if routing.outbound_enabled or routing.outbound_sink_phone:
        return ReplyDecision(action="send", reason="ok")
    return ReplyDecision(action="skip", reason="outbound_disabled_without_sink")
