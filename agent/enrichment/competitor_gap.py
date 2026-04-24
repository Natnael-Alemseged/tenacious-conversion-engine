from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.enrichment.public_briefs import _infer_domain
from agent.enrichment.schemas import HiringSignalBrief

_SEGMENT_RELEVANCE = {
    1: ["segment_1_series_a_b"],
    2: ["segment_2_mid_market_restructure"],
    3: ["segment_3_leadership_transition"],
    4: ["segment_4_specialized_capability"],
}


def _sample_path() -> Path:
    return Path("tenacious_sales_data/schemas/sample_competitor_gap_brief.json")


def _load_sample_benchmark(path: str | None = None) -> dict[str, Any]:
    sample = Path(path) if path else _sample_path()
    return json.loads(sample.read_text(encoding="utf-8"))


def _prospect_sector(brief: HiringSignalBrief) -> tuple[str, str]:
    categories = brief.signals.crunchbase.data.categories
    if not categories:
        return "Software / Data", "General software"
    sector = " / ".join(categories[:2])
    sub_niche = " / ".join(categories[:3])
    return sector, sub_niche


def _prospect_state_for_leadership(brief: HiringSignalBrief) -> tuple[str, str]:
    changes = brief.signals.leadership_change.data
    if changes:
        title = str(changes[0].get("title") or "leadership change")
        return (
            f"Public leadership-change signal exists ({title}), but no explicit AI/ML executive "
            "role is visible in the current enrichment sources.",
            "medium",
        )
    return (
        "No public signal of a dedicated AI/ML leadership role was found in the current "
        "Crunchbase/leadership-change inputs.",
        "high" if brief.signals.ai_maturity.score <= 1 else "medium",
    )


def _prospect_state_for_mlops(brief: HiringSignalBrief) -> tuple[str, str]:
    jobs = brief.signals.job_posts.data
    role_titles = [str(item) for item in jobs.get("role_titles") or []]
    if any("mlops" in title.lower() or "platform" in title.lower() for title in role_titles):
        return (
            "Public job-post signal already shows ML-platform-adjacent hiring, so this is likely "
            "an active build rather than a clean gap.",
            "low",
        )
    if jobs.get("open_roles", 0):
        return (
            "Public hiring signal shows engineering hiring, but no explicitly MLOps-labeled or "
            "ML-platform role was detected in the current careers scrape.",
            "medium",
        )
    return (
        "No public hiring signal currently shows a dedicated MLOps or ML-platform function.",
        "medium",
    )


def _prospect_state_for_commentary(brief: HiringSignalBrief) -> tuple[str, str]:
    if brief.signals.ai_maturity.score >= 2:
        return (
            "Public signals suggest AI work is active, but the current artifact set does not "
            "include strong technical commentary or evaluation-framework evidence.",
            "medium",
        )
    return (
        "No public technical commentary on agentic systems, evaluation frameworks, or ML "
        "operations was found in the currently integrated sources.",
        "high",
    )


def _select_gap_findings(
    brief: HiringSignalBrief,
    sample: dict[str, Any],
) -> list[dict[str, Any]]:
    sample_findings = sample.get("gap_findings", [])
    selected: list[dict[str, Any]] = []
    states = {
        "Dedicated AI/ML leadership role at the executive level": _prospect_state_for_leadership(
            brief
        ),
        (
            "Dedicated MLOps / ML-platform engineering function "
            "(roles open 45+ days suggests active buildout)"
        ): _prospect_state_for_mlops(brief),
        (
            "Public technical commentary on agentic or evaluation-framework work"
        ): _prospect_state_for_commentary(brief),
    }
    for finding in sample_findings:
        practice = str(finding.get("practice") or "")
        state = states.get(practice)
        if not state:
            continue
        prospect_state, confidence = state
        selected.append(
            {
                "practice": practice,
                "peer_evidence": finding.get("peer_evidence", []),
                "prospect_state": prospect_state,
                "confidence": confidence,
                "segment_relevance": _SEGMENT_RELEVANCE.get(
                    brief.icp_segment,
                    finding.get("segment_relevance", ["segment_4_specialized_capability"]),
                ),
            }
        )
    return selected[:3]


def _pitch_shift(gap_findings: list[dict[str, Any]]) -> str:
    if not gap_findings:
        return (
            "Keep the outreach exploratory. Ask whether the current capability build is active "
            "rather than asserting a sector-gap claim."
        )
    first = gap_findings[0]
    practice = str(first.get("practice") or "the highest-confidence peer gap")
    confidence = str(first.get("confidence") or "medium")
    if confidence == "high":
        return (
            f"Lead with {practice.lower()} as a research-backed question. Keep the phrasing "
            "specific and evidence-led rather than accusatory."
        )
    return (
        f"Use {practice.lower()} as a soft research prompt. Ask whether the capability is "
        "already being scoped internally before making any stronger claim."
    )


def to_public_competitor_gap_brief(
    brief: HiringSignalBrief,
    *,
    benchmark_path: str | None = None,
) -> dict[str, Any]:
    sample = _load_sample_benchmark(benchmark_path)
    domain = _infer_domain(brief)
    sector, sub_niche = _prospect_sector(brief)

    competitors = [
        item
        for item in sample.get("competitors_analyzed", [])
        if item.get("domain") != sample.get("prospect_domain")
    ]
    top_quartile_scores = [
        int(item.get("ai_maturity_score", 0))
        for item in competitors
        if item.get("top_quartile") is True
    ]
    benchmark = (
        round(sum(top_quartile_scores) / len(top_quartile_scores), 2)
        if top_quartile_scores
        else float(sample.get("sector_top_quartile_benchmark", 0))
    )
    gap_findings = _select_gap_findings(brief, sample)

    return {
        "prospect_domain": domain,
        "prospect_sector": sector,
        "prospect_sub_niche": sub_niche,
        "generated_at": brief.generated_at,
        "prospect_ai_maturity_score": brief.signals.ai_maturity.score,
        "sector_top_quartile_benchmark": benchmark,
        "competitors_analyzed": competitors[:6],
        "gap_findings": gap_findings,
        "suggested_pitch_shift": _pitch_shift(gap_findings),
        "gap_quality_self_check": {
            "all_peer_evidence_has_source_url": all(
                all(item.get("source_url") for item in finding.get("peer_evidence", []))
                for finding in gap_findings
            ),
            "at_least_one_gap_high_confidence": any(
                finding.get("confidence") == "high" for finding in gap_findings
            ),
            "prospect_silent_but_sophisticated_risk": (
                brief.signals.ai_maturity.score >= 2
                and not brief.signals.leadership_change.data
                and brief.signals.job_posts.confidence < 0.75
            ),
        },
        "benchmark_source": "bundled_sample_competitor_gap_brief",
        "benchmark_source_path": str(_sample_path() if benchmark_path is None else benchmark_path),
    }
