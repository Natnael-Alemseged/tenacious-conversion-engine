from __future__ import annotations

import json
from pathlib import Path

from agent.enrichment.competitor_gap import to_public_competitor_gap_brief
from agent.enrichment.discovery_context import render_discovery_call_context_brief
from agent.enrichment.pipeline import run
from agent.enrichment.public_briefs import to_public_hiring_signal_brief
from agent.enrichment.schemas import HiringSignalBrief


def write_hiring_signal_brief(
    *,
    company_name: str,
    careers_url: str = "",
    path: str = "artifacts/hiring_signal_brief.json",
) -> HiringSignalBrief:
    result = run(company_name=company_name, careers_url=careers_url)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(to_public_hiring_signal_brief(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def write_competitor_gap_brief(
    *,
    company_name: str,
    careers_url: str = "",
    path: str = "artifacts/competitor_gap_brief.json",
) -> dict[str, object]:
    result = run(company_name=company_name, careers_url=careers_url)
    payload = to_public_competitor_gap_brief(result)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def write_discovery_call_context_brief(
    *,
    company_name: str,
    careers_url: str = "",
    path: str = "artifacts/discovery_call_context_brief.md",
    prospect_name: str = "",
    prospect_title: str = "",
    call_datetime_utc: str = "TBD",
    call_datetime_prospect_tz: str = "TBD",
    tenacious_lead_name: str = "TBD",
    duration_minutes: int = 30,
    thread_start_date: str = "TBD",
    original_subject: str = "",
    langfuse_trace_url: str = "",
    price_bands_quoted: str = "none",
) -> str:
    result = run(company_name=company_name, careers_url=careers_url)
    competitor_gap = to_public_competitor_gap_brief(result)
    content = render_discovery_call_context_brief(
        result,
        competitor_gap,
        prospect_name=prospect_name,
        prospect_title=prospect_title,
        prospect_company=company_name,
        call_datetime_utc=call_datetime_utc,
        call_datetime_prospect_tz=call_datetime_prospect_tz,
        tenacious_lead_name=tenacious_lead_name,
        duration_minutes=duration_minutes,
        thread_start_date=thread_start_date,
        original_subject=original_subject,
        langfuse_trace_url=langfuse_trace_url,
        price_bands_quoted=price_bands_quoted,
    )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return content
