from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from agent.enrichment import ai_maturity as ai_maturity_score
from agent.enrichment.ai_maturity_collectors.collectors import collect_all_ai_maturity_signals
from agent.enrichment.ai_maturity_collectors.fetch import fetch_text
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


def find_competitors(
    *,
    prospect_name: str,
    categories: list[str],
    odm_data: list[dict[str, Any]],
    max_peers: int = 6,
) -> list[dict[str, Any]]:
    """Return sector peers from enrichment ODM data matching the prospect's categories.

    Uses the same Crunchbase ODM the enrichment pipeline already loads rather than
    the bundled sample benchmark.
    """
    if not categories or not odm_data:
        return []
    lower_cats = {c.lower() for c in categories}
    peers: list[dict[str, Any]] = []
    for company in odm_data:
        name = str(company.get("name") or "")
        if name.lower() == prospect_name.lower():
            continue
        company_cats = [str(c).lower() for c in (company.get("categories") or [])]
        if any(cat in lower_cats for cat in company_cats):
            peers.append(
                {
                    "name": name,
                    "domain": company.get("domain") or company.get("homepage_url") or "",
                    "ai_maturity_score": int(company.get("ai_maturity_score") or 0),
                    "categories": company.get("categories") or [],
                    "top_quartile": bool(int(company.get("ai_maturity_score") or 0) >= 2),
                }
            )
    return peers[:max_peers]


def _headcount_band(employee_enum: Any) -> str:
    val = str(employee_enum or "")
    if not val:
        return "15_to_80"
    if val in {"c_00001_00010", "c_00011_00050"}:
        return "15_to_80"
    if val in {"c_00051_00100", "c_00101_00250"}:
        return "80_to_200"
    if val == "c_00251_00500":
        return "200_to_500"
    if val in {"c_00501_01000", "c_01001_05000"}:
        return "500_to_2000"
    return "2000_plus"


_LEADERSHIP_HINT = re.compile(
    r"\b(head of ai|vp of ai|vp ai|chief scientist|chief ai|director of ai)\b", re.I
)


def _leadership_page_signal(
    *,
    domain: str,
    transport: httpx.BaseTransport | None,
) -> tuple[bool, list[dict[str, str]]]:
    if not domain:
        return False, []
    candidates = [
        f"https://{domain}/team",
        f"https://{domain}/leadership",
        f"https://{domain}/about",
    ]
    for url in candidates:
        page = fetch_text(url, transport=transport)
        if not page.ok:
            continue
        match = _LEADERSHIP_HINT.search(page.text)
        if match:
            return True, [
                {
                    "signal": "named_ai_leadership",
                    "source_url": url,
                    "fetched_at": page.fetched_at,
                    "snippet": f"Detected leadership hint: {match.group(0)}",
                }
            ]
    return False, []


def _score_peer_company(
    *,
    name: str,
    domain: str,
    tech_stack: list[str],
    transport: httpx.BaseTransport | None,
) -> dict[str, Any]:
    signals, evidence, _strength = collect_all_ai_maturity_signals(
        company_domain=domain,
        tech_stack=tech_stack,
        job_role_titles=[],
        transport=transport,
    )
    leadership, leadership_ev = _leadership_page_signal(domain=domain, transport=transport)
    signals["named_ai_leadership"] = leadership
    evidence = [*evidence, *leadership_ev]
    score, justification, _confidence = ai_maturity_score.score(signals)
    justification_lines = [justification]
    for item in evidence[:6]:
        if item.get("signal") and item.get("source_url"):
            justification_lines.append(f"{item['signal']}: {item['source_url']}")
    sources_checked = sorted(
        {item.get("source_url", "") for item in evidence if item.get("source_url")}
    )
    return {
        "name": name,
        "domain": domain,
        "ai_maturity_score": score,
        "ai_maturity_justification": justification_lines[:6],
        "headcount_band": "15_to_80",
        "top_quartile": False,
        "sources_checked": sources_checked[:8],
        "_evidence": evidence,
        "_signals": signals,
    }


def _percentile(*, score: int, peer_scores: list[int]) -> float:
    if not peer_scores:
        return 0.0
    leq = sum(1 for s in peer_scores if s <= score)
    return round(leq / len(peer_scores), 3)


def _top_quartile_flags(scored: list[dict[str, Any]]) -> None:
    scores = sorted(int(item.get("ai_maturity_score") or 0) for item in scored)
    if not scores:
        return
    idx = max(0, int(round(0.75 * (len(scores) - 1))))
    threshold = scores[idx]
    for item in scored:
        item["top_quartile"] = bool(int(item.get("ai_maturity_score") or 0) >= threshold)


def _gap_findings_from_scored(
    *,
    brief: HiringSignalBrief,
    scored: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Practice 1: leadership role evidence (prefer high confidence if peers show it).
    peers_with_leadership = [
        item for item in scored if item.get("_signals", {}).get("named_ai_leadership") is True
    ]
    leadership_peers = peers_with_leadership[:2]
    leadership_evidence = []
    for peer in leadership_peers:
        for ev in peer.get("_evidence", []):
            if ev.get("signal") == "named_ai_leadership" and ev.get("source_url"):
                leadership_evidence.append(
                    {
                        "competitor_name": peer["name"],
                        "evidence": ev.get("snippet", "Named AI leadership signal."),
                        "source_url": ev["source_url"],
                    }
                )
                break
    findings: list[dict[str, Any]] = []
    if len(leadership_evidence) >= 2:
        findings.append(
            {
                "practice": "Dedicated AI/ML leadership role at the executive level",
                "peer_evidence": leadership_evidence[:3],
                "prospect_state": (
                    "Prospect leadership-change inputs did not show a named AI/ML executive role "
                    "in the current enrichment sources."
                ),
                "confidence": "high" if brief.signals.ai_maturity.score <= 1 else "medium",
                "segment_relevance": _SEGMENT_RELEVANCE.get(
                    brief.icp_segment, ["segment_4_specialized_capability"]
                ),
            }
        )

    # Practice 2: technical commentary / exec commentary evidence.
    peers_with_commentary = [
        item for item in scored if item.get("_signals", {}).get("exec_commentary") is True
    ]
    commentary_evidence = []
    for peer in peers_with_commentary[:2]:
        for ev in peer.get("_evidence", []):
            if ev.get("signal") == "exec_commentary" and ev.get("source_url"):
                commentary_evidence.append(
                    {
                        "competitor_name": peer["name"],
                        "evidence": ev.get("snippet", "Exec commentary signal."),
                        "source_url": ev["source_url"],
                    }
                )
                break
    if len(commentary_evidence) >= 2:
        findings.append(
            {
                "practice": "Public technical commentary on agentic or evaluation-framework work",
                "peer_evidence": commentary_evidence[:3],
                "prospect_state": (
                    "No strong public technical commentary signal was detected in the currently "
                    "integrated sources; treat any gap claim as a research question."
                ),
                "confidence": "medium",
                "segment_relevance": ["segment_1_series_a_b"],
            }
        )

    if not findings:
        findings.append(
            {
                "practice": "Public-signal competitor comparison is sparse in the current peer set",
                "peer_evidence": [
                    {
                        "competitor_name": scored[0]["name"] if scored else "n/a",
                        "evidence": (
                            "Insufficient public evidence to assert a specific practice gap."
                        ),
                        "source_url": (scored[0].get("sources_checked") or [""])[0]
                        if scored
                        else "",
                    },
                    {
                        "competitor_name": scored[1]["name"] if len(scored) > 1 else "n/a",
                        "evidence": "Keep outbound phrasing exploratory until evidence improves.",
                        "source_url": (scored[1].get("sources_checked") or [""])[0]
                        if len(scored) > 1
                        else "",
                    },
                ],
                "prospect_state": "Sparse competitor evidence set; do not assert a gap as fact.",
                "confidence": "low",
                "segment_relevance": ["segment_4_specialized_capability"],
            }
        )
    return findings[:3]


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
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    sample = _load_sample_benchmark(benchmark_path)
    domain = _infer_domain(brief)
    sector, sub_niche = _prospect_sector(brief)

    from agent.enrichment import crunchbase as _crunchbase

    odm = _crunchbase._load_odm() or []
    live_peers = find_competitors(
        prospect_name=brief.company_name,
        categories=brief.signals.crunchbase.data.categories,
        odm_data=odm,
        max_peers=10,
    )

    # Ensure 5–10 competitors; if sparse, explicitly fall back to sample cohort.
    benchmark_source = "odm_sector_peers"
    competitors_raw = live_peers
    sparse_sector = len(competitors_raw) < 5
    if sparse_sector:
        benchmark_source = "sparse_sector_fallback_to_sample"
        competitors_raw = [
            item
            for item in sample.get("competitors_analyzed", [])
            if item.get("domain") != sample.get("prospect_domain")
        ][:10]

    tech_stack = brief.tech_stack
    scored: list[dict[str, Any]] = []
    for comp in competitors_raw[:10]:
        name = str(comp.get("name") or comp.get("competitor_name") or "")
        raw_domain = str(comp.get("domain") or comp.get("homepage_url") or "")
        parsed = raw_domain.replace("https://", "").replace("http://", "").split("/", 1)[0]
        if not parsed:
            continue
        scored_item = _score_peer_company(
            name=name,
            domain=parsed,
            tech_stack=tech_stack,
            transport=transport,
        )
        # If ODM has an employee enum, map it.
        if isinstance(comp, dict) and comp.get("employee_count_enum"):
            scored_item["headcount_band"] = _headcount_band(comp.get("employee_count_enum"))
        scored.append(scored_item)
        if len(scored) >= 10:
            break

    # If scoring produced too few, pad with sample competitors.
    if len(scored) < 5:
        for comp in sample.get("competitors_analyzed", []):
            raw_domain = str(comp.get("domain") or "")
            parsed = raw_domain.replace("https://", "").replace("http://", "").split("/", 1)[0]
            if not parsed:
                continue
            scored.append(
                {
                    "name": str(comp.get("name") or ""),
                    "domain": parsed,
                    "ai_maturity_score": int(comp.get("ai_maturity_score") or 0),
                    "ai_maturity_justification": list(comp.get("ai_maturity_justification") or [])[
                        :6
                    ],
                    "headcount_band": str(comp.get("headcount_band") or "15_to_80"),
                    "top_quartile": bool(comp.get("top_quartile") is True),
                    "sources_checked": list(comp.get("sources_checked") or [])[:8],
                    "_evidence": [],
                    "_signals": {},
                }
            )
            if len(scored) >= 5:
                break

    _top_quartile_flags(scored)
    top_quartile_scores = [
        int(item.get("ai_maturity_score") or 0) for item in scored if item["top_quartile"]
    ]
    benchmark = (
        round(sum(top_quartile_scores) / len(top_quartile_scores), 2)
        if top_quartile_scores
        else float(sample.get("sector_top_quartile_benchmark", 0))
    )
    gap_findings = (
        _select_gap_findings(brief, sample)
        if sparse_sector
        else _gap_findings_from_scored(brief=brief, scored=scored)
    )

    peer_scores = [int(item.get("ai_maturity_score") or 0) for item in scored]
    prospect_percentile = _percentile(
        score=brief.signals.ai_maturity.score, peer_scores=peer_scores
    )

    return {
        "prospect_domain": domain,
        "prospect_sector": sector,
        "prospect_sub_niche": sub_niche,
        "generated_at": brief.generated_at,
        "prospect_ai_maturity_score": brief.signals.ai_maturity.score,
        "sector_top_quartile_benchmark": benchmark,
        "competitors_analyzed": [
            {k: v for k, v in item.items() if not k.startswith("_")}
            for item in scored[:10]
            if item.get("name") and item.get("domain")
        ][:10],
        "gap_findings": gap_findings,
        "suggested_pitch_shift": _pitch_shift(gap_findings),
        "prospect_sector_percentile": prospect_percentile,
        "sparse_sector": sparse_sector,
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
        "benchmark_source": benchmark_source,
        "benchmark_source_path": str(_sample_path() if benchmark_path is None else benchmark_path),
    }
