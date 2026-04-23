from __future__ import annotations

from typing import Any

from agent.enrichment import ai_maturity, crunchbase, job_posts, layoffs


def run(company_name: str, careers_url: str = "") -> dict:
    """Return hiring_signal_brief with per-signal data and confidence scores."""

    # --- Crunchbase firmographics ---
    cb = crunchbase.lookup(company_name)
    cb_confidence = 1.0 if cb else 0.0

    # --- Recent funding ---
    funding = crunchbase.recent_funding(company_name)
    funding_confidence = 1.0 if funding else (0.5 if cb else 0.0)

    # --- Layoffs ---
    layoff_events = layoffs.check(company_name)
    layoffs_confidence = 1.0 if layoff_events else (0.5 if cb else 0.0)

    # --- Leadership changes ---
    leader_changes = crunchbase.leadership_changes(company_name)
    leadership_confidence = 1.0 if leader_changes else (0.5 if cb else 0.0)

    # --- Job posts ---
    jobs = (
        job_posts.scrape(careers_url)
        if careers_url
        else {"url": "", "open_roles": 0, "ai_adjacent_roles": 0}
    )
    jobs_confidence = (
        0.9 if careers_url and not jobs.get("error") else (0.3 if careers_url else 0.0)
    )

    # --- AI maturity ---
    # Only pass signals observed from a real source. Avoid counting defaulted values toward
    # confidence, so outbound phrasing cannot sound more certain than the evidence supports.
    ai_signals: dict[str, Any] = {}
    if careers_url and not jobs.get("error") and jobs.get("open_roles", 0) > 0:
        ai_signals["ai_roles_fraction"] = jobs.get("ai_roles_fraction", 0.0)

    named_ai_leadership = any(
        ("ai" in (c.get("title") or "") or "scientist" in (c.get("title") or ""))
        for c in (leader_changes or [])
    )
    if leader_changes:
        ai_signals["named_ai_leadership"] = named_ai_leadership
    ai_score, ai_justification, ai_confidence = ai_maturity.score(ai_signals)

    # --- ICP segment classification ---
    # 0 = general (no dominant trigger); 1-4 = specific buying signal
    icp_segment = 0
    if funding:
        icp_segment = 1  # recently funded
    elif layoff_events:
        icp_segment = 2  # mid-market restructuring
    elif leader_changes:
        icp_segment = 3  # leadership transition
    elif ai_score >= 2:
        icp_segment = 4  # capability gap

    overall_confidence = round(
        sum(
            [
                cb_confidence,
                funding_confidence,
                layoffs_confidence,
                leadership_confidence,
                jobs_confidence,
            ]
        )
        / 5,
        3,
    )

    return {
        "company_name": company_name,
        "icp_segment": icp_segment,
        "overall_confidence": overall_confidence,
        "signals": {
            "crunchbase": {
                "data": {
                    "uuid": (cb or {}).get("uuid"),
                    "employee_count": (cb or {}).get("num_employees_enum"),
                    "country": (cb or {}).get("country_code"),
                    "categories": (cb or {}).get("categories", []),
                },
                "confidence": cb_confidence,
            },
            "funding": {
                "data": funding,
                "confidence": funding_confidence,
            },
            "layoffs": {
                "data": layoff_events,
                "confidence": layoffs_confidence,
            },
            "leadership_change": {
                "data": leader_changes,
                "confidence": leadership_confidence,
            },
            "job_posts": {
                "data": jobs,
                "confidence": jobs_confidence,
            },
            "ai_maturity": {
                "score": ai_score,
                "justification": ai_justification,
                "confidence": ai_confidence,
            },
        },
    }
