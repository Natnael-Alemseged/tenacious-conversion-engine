from __future__ import annotations

from urllib.parse import urlparse

from agent.enrichment.schemas import HiringSignalBrief

_SEGMENT_NAMES = {
    1: "segment_1_series_a_b",
    2: "segment_2_mid_market_restructure",
    3: "segment_3_leadership_transition",
    4: "segment_4_specialized_capability",
}


def _infer_domain(brief: HiringSignalBrief) -> str:
    if brief.company_domain:
        return brief.company_domain
    url = brief.signals.job_posts.data.get("url") or ""
    parsed = urlparse(str(url))
    return parsed.netloc.lower()


def _segment_name(brief: HiringSignalBrief) -> str:
    if brief.segment_confidence < 0.6:
        return "abstain"
    return _SEGMENT_NAMES.get(brief.icp_segment, "abstain")


def _signal_tier(signal_confidence: float) -> str:
    if signal_confidence >= 0.75:
        return "high"
    if signal_confidence >= 0.35:
        return "medium"
    return "low"


def _source_status_entries(brief: HiringSignalBrief) -> list[dict[str, str]]:
    if brief.data_sources_checked:
        return brief.data_sources_checked
    generated_at = brief.generated_at
    entries: list[dict[str, str]] = []
    entries.append(
        {
            "source": "crunchbase_odm",
            "status": "success" if brief.signals.crunchbase.confidence > 0 else "no_data",
            "fetched_at": generated_at,
        }
    )
    entries.append(
        {
            "source": "layoffs_fyi",
            "status": "success" if brief.signals.layoffs.data else "no_data",
            "fetched_at": generated_at,
        }
    )
    if brief.signals.job_posts.data.get("url"):
        entries.append(
            {
                "source": "company_careers_page",
                "status": (
                    "error"
                    if brief.signals.job_posts.data.get("error")
                    else (
                        "success"
                        if brief.signals.job_posts.data.get("open_roles", 0) > 0
                        else "no_data"
                    )
                ),
                "error_message": str(brief.signals.job_posts.data.get("error", "")),
                "fetched_at": generated_at,
            }
        )
    entries.append(
        {
            "source": "leadership_changes",
            "status": "success" if brief.signals.leadership_change.data else "no_data",
            "fetched_at": generated_at,
        }
    )
    return entries


def _ai_justifications(brief: HiringSignalBrief) -> list[dict[str, str]]:
    justifications: list[dict[str, str]] = []
    jobs = brief.signals.job_posts.data
    ai_fraction = float(jobs.get("ai_roles_fraction") or 0.0)
    justifications.append(
        {
            "signal": "ai_adjacent_open_roles",
            "status": (
                f"{jobs.get('ai_adjacent_roles', 0)} AI-adjacent roles across "
                f"{jobs.get('open_roles', 0)} engineering openings "
                f"({round(ai_fraction * 100)}% AI-adjacent)."
            ),
            "weight": "high",
            "confidence": _signal_tier(brief.signals.job_posts.confidence),
            "source_url": str(jobs.get("url") or ""),
        }
    )
    leadership = brief.signals.leadership_change.data
    if leadership:
        title = str(leadership[0].get("title") or "")
        justifications.append(
            {
                "signal": "named_ai_ml_leadership",
                "status": f"Recent leadership signal detected: {title or 'leadership change'}",
                "weight": "high",
                "confidence": _signal_tier(brief.signals.leadership_change.confidence),
            }
        )
    else:
        justifications.append(
            {
                "signal": "named_ai_ml_leadership",
                "status": "No recent public AI/ML-specific leadership change was detected.",
                "weight": "high",
                "confidence": "medium",
            }
        )
    modern_stack_labels = {"dbt", "snowflake", "databricks"}
    stack_hits = [item for item in brief.tech_stack if item.lower() in modern_stack_labels]
    justifications.append(
        {
            "signal": "modern_data_ml_stack",
            "status": (
                f"Inferred modern data stack signals: {', '.join(stack_hits)}."
                if stack_hits
                else "No strong public modern data/ML stack indicators detected."
            ),
            "weight": "low",
            "confidence": "medium" if stack_hits else "low",
        }
    )
    return justifications


def to_public_hiring_signal_brief(brief: HiringSignalBrief) -> dict[str, object]:
    domain = _infer_domain(brief)
    required_stacks = brief.signals.bench.data.required_stacks
    gaps = brief.signals.bench.data.gaps
    funding = brief.signals.funding.data[0] if brief.signals.funding.data else {}
    layoffs = brief.signals.layoffs.data[0] if brief.signals.layoffs.data else {}
    leadership = (
        brief.signals.leadership_change.data[0] if brief.signals.leadership_change.data else {}
    )

    return {
        "prospect_domain": domain,
        "prospect_name": brief.company_name,
        "generated_at": brief.generated_at,
        "primary_segment_match": _segment_name(brief),
        "segment_confidence": brief.segment_confidence,
        "ai_maturity": {
            "score": brief.signals.ai_maturity.score,
            "confidence": brief.signals.ai_maturity.confidence,
            "justifications": _ai_justifications(brief),
        },
        "hiring_velocity": {
            "open_roles_today": int(brief.signals.job_posts.data.get("open_roles") or 0),
            "open_roles_60_days_ago": 0,
            "velocity_label": "insufficient_signal",
            "signal_confidence": brief.signals.job_posts.confidence,
            "sources": ["company_careers_page"] if brief.signals.job_posts.data.get("url") else [],
        },
        "buying_window_signals": {
            "funding_event": {
                "detected": bool(brief.signals.funding.data),
                "stage": str(
                    funding.get("investment_type") or funding.get("round") or "none"
                ).lower(),
                "amount_usd": funding.get("money_raised_usd"),
                "closed_at": funding.get("announced_on") or funding.get("date"),
            },
            "layoff_event": {
                "detected": bool(brief.signals.layoffs.data),
                "date": layoffs.get("date"),
                "headcount_reduction": layoffs.get("laid_off_count"),
                "percentage_cut": layoffs.get("percentage"),
            },
            "leadership_change": {
                "detected": bool(brief.signals.leadership_change.data),
                "role": leadership.get("title", "none"),
                "new_leader_name": leadership.get("name"),
                "started_at": leadership.get("started_on"),
            },
        },
        "tech_stack": brief.tech_stack,
        "bench_to_brief_match": {
            "required_stacks": required_stacks,
            "bench_available": brief.signals.bench.data.bench_to_brief_gate_passed,
            "gaps": gaps,
        },
        "data_sources_checked": _source_status_entries(brief),
        "honesty_flags": brief.honesty_flags,
    }
