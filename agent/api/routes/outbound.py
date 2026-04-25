import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from agent.core.config import settings
from agent.integrations.hubspot import HubSpotMcpError
from agent.storage.conversations import ConversationStore
from agent.storage.suppression import SmsSuppressionStore
from agent.workflows.lead_orchestrator import LeadOrchestrator, _signal_summary_from_brief
from agent.workflows.sms_handoff import send_warm_lead_sms_handoff

router = APIRouter()
orchestrator = LeadOrchestrator()
conversations = ConversationStore()
_log = logging.getLogger(__name__)


class OutboundEmailRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    to_email: EmailStr
    careers_url: str = Field(default="", max_length=2048)
    outbound_variant: str = Field(default="api_trigger", max_length=64)


@router.post("/email")
def trigger_outbound_email(request: OutboundEmailRequest) -> dict[str, Any]:
    """
    Production-like operator entrypoint:
    - run enrichment
    - write HubSpot contact fields
    - send outbound email (sink-routed unless OUTBOUND_ENABLED=true)
    """
    _log.info(
        "outbound.email.request",
        extra={
            "ob_phase": "start",
            "ob_company_name": request.company_name,
            "ob_to_email_domain": str(request.to_email).split("@")[-1],
            "ob_outbound_variant": request.outbound_variant,
        },
    )
    try:
        brief = orchestrator.enrichment_runner(
            company_name=request.company_name, careers_url=request.careers_url
        )
        _log.info(
            "outbound.email.enrichment_complete",
            extra={
                "ob_phase": "enrichment_complete",
                "ob_company_name": brief.company_name,
                "ob_icp_segment": str(brief.icp_segment),
                "ob_segment_confidence": f"{brief.segment_confidence:.3f}",
                "ob_ai_maturity_score": str(brief.signals.ai_maturity.score),
                "ob_bench_gate": str(brief.signals.bench.data.bench_to_brief_gate_passed).lower(),
            },
        )
        signal_summary = _signal_summary_from_brief(brief)
        result = orchestrator.send_outbound_email(
            to_email=str(request.to_email),
            company_name=brief.company_name,
            signal_summary=signal_summary,
            icp_segment=brief.icp_segment,
            ai_maturity_score=brief.signals.ai_maturity.score,
            confidence=brief.segment_confidence,
            segment_confidence=brief.segment_confidence,
            crunchbase_id=brief.signals.crunchbase.data.uuid,
            bench_to_brief_gate_passed=bool(brief.signals.bench.data.bench_to_brief_gate_passed),
            outbound_variant=request.outbound_variant,
            idempotency_key=f"outbound:{request.outbound_variant}:{request.to_email}:{brief.company_name}",
        )
        _log.info(
            "outbound.email.sent",
            extra={
                "ob_phase": "sent",
                "ob_message_id": str(result.get("id") or ""),
                "ob_status": str(result.get("status") or ""),
            },
        )
        return {
            "status": "sent",
            "outbound": result,
            "enrichment": {
                "company_name": brief.company_name,
                "icp_segment": brief.icp_segment,
                "segment_confidence": brief.segment_confidence,
                "ai_maturity_score": brief.signals.ai_maturity.score,
                "bench_to_brief_gate_passed": bool(
                    brief.signals.bench.data.bench_to_brief_gate_passed
                ),
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HubSpotMcpError as exc:
        status = 502 if exc.error_kind == "http_status" else 503
        raise HTTPException(
            status_code=status,
            detail=f"HubSpot integration error ({exc.error_kind}): {exc.detail[:500]}",
            headers={"Retry-After": "5"} if status == 503 else None,
        ) from exc
    except Exception as exc:
        _log.exception("outbound.email.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class OutboundSmsRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64)
    company_name: str = Field(min_length=1, max_length=255)
    to_phone: str = Field(pattern=r"^\+\d{10,15}$")
    outbound_variant: str = Field(default="warm_sms_api_trigger", max_length=64)
    message_override: str | None = Field(default=None, max_length=1000)


@router.post("/sms")
def trigger_outbound_sms(request: OutboundSmsRequest) -> dict[str, Any]:
    """
    Warm-lead-only SMS entrypoint (Tenacious Consulting scenario).

    Hard gates:
    - must have prior email engagement (conversation state email_replied=true)
    - must not be opted out (sms_opted_out or suppression store contains number)
    """
    _log.info(
        "outbound.sms.request",
        extra={
            "ob_phase": "start",
            "ob_thread_id": request.thread_id,
            "ob_company_name": request.company_name,
            "ob_to_phone_suffix": request.to_phone[-6:],
            "ob_outbound_variant": request.outbound_variant,
        },
    )
    try:
        suppression = SmsSuppressionStore(settings.sms_suppression_path)
        result = send_warm_lead_sms_handoff(
            orchestrator=orchestrator,
            conversations=conversations,
            suppression=suppression,
            thread_id=request.thread_id,
            to_phone=request.to_phone,
            company_name=request.company_name,
            outbound_variant=request.outbound_variant,
            message_override=request.message_override,
        )
        _log.info(
            "outbound.sms.sent",
            extra={
                "ob_phase": "sent",
                "ob_status": str(result.get("status") or ""),
            },
        )
        return {"status": "sent", "outbound": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HubSpotMcpError as exc:
        status = 502 if exc.error_kind == "http_status" else 503
        raise HTTPException(
            status_code=status,
            detail=f"HubSpot integration error ({exc.error_kind}): {exc.detail[:500]}",
            headers={"Retry-After": "5"} if status == 503 else None,
        ) from exc
    except Exception as exc:
        _log.exception("outbound.sms.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
