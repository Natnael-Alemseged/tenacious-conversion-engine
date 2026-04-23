from __future__ import annotations

from typing import Any

from agent.core.config import settings
from agent.enrichment import ai_maturity, crunchbase, job_posts, layoffs
from agent.enrichment.bench_summary import extract_keywords, load
from agent.enrichment.schemas import (
    AiMaturitySignal,
    BenchSignal,
    BenchSignalData,
    CrunchbaseBriefData,
    CrunchbaseSignal,
    EnrichmentSignals,
    FundingSignal,
    HiringSignalBrief,
    JobPostsSignal,
    LayoffsSignal,
    LeadershipSignal,
)
from agent.enrichment.signal_confidence import (
    ai_maturity_confidence_meta,
    bench_confidence,
    weighted_overall_confidence,
)
from agent.enrichment.signal_confidence import (
    crunchbase_confidence as score_crunchbase_confidence,
)
from agent.enrichment.signal_confidence import (
    funding_confidence as score_funding_confidence,
)
from agent.enrichment.signal_confidence import (
    job_posts_confidence as score_job_posts_confidence,
)
from agent.enrichment.signal_confidence import (
    layoffs_confidence as score_layoffs_confidence,
)
from agent.enrichment.signal_confidence import (
    leadership_confidence as score_leadership_confidence,
)


def run(company_name: str, careers_url: str = "") -> HiringSignalBrief:
    """Return hiring_signal_brief with typed signals, scores, and confidence metadata."""

    cb = crunchbase.lookup(company_name)
    cb_confidence, cb_meta = score_crunchbase_confidence(cb)

    funding = crunchbase.recent_funding(company_name)
    funding_confidence, funding_meta = score_funding_confidence(funding=funding, cb=cb)

    layoff_events = layoffs.check(company_name)
    layoffs_confidence, layoffs_meta = score_layoffs_confidence(layoff_events=layoff_events, cb=cb)

    leader_changes = crunchbase.leadership_changes(company_name)
    leadership_confidence, leadership_meta = score_leadership_confidence(
        leader_changes=leader_changes, cb=cb
    )

    jobs = (
        job_posts.scrape(careers_url)
        if careers_url
        else {"url": "", "open_roles": 0, "ai_adjacent_roles": 0}
    )
    jobs_confidence, jobs_meta = score_job_posts_confidence(careers_url=careers_url, jobs=jobs)

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
    ai_meta = ai_maturity_confidence_meta(ai_confidence)

    icp_segment = 0
    if funding:
        icp_segment = 1
    elif layoff_events:
        icp_segment = 2
    elif leader_changes:
        icp_segment = 3
    elif ai_score >= 2:
        icp_segment = 4

    mean_inputs = [
        cb_confidence,
        funding_confidence,
        layoffs_confidence,
        leadership_confidence,
        jobs_confidence,
    ]
    overall_confidence = round(sum(mean_inputs) / len(mean_inputs), 3)
    overall_weighted = weighted_overall_confidence(
        {
            "crunchbase": cb_confidence,
            "funding": funding_confidence,
            "layoffs": layoffs_confidence,
            "leadership_change": leadership_confidence,
            "job_posts": jobs_confidence,
        }
    )

    bench = load(settings.bench_summary_path)
    bench_keywords = extract_keywords(bench)
    role_titles = jobs.get("role_titles") or []
    haystack = " ".join(
        [company_name, " ".join((cb or {}).get("categories", [])), " ".join(role_titles)]
    )
    haystack_lc = haystack.lower()
    bench_hits = sorted([kw for kw in bench_keywords if kw and kw in haystack_lc])
    bench_gate_passed = bool(bench_hits)
    bench_confidence_v, bench_meta = bench_confidence(bench=bench, bench_keywords=bench_keywords)

    cb_data = CrunchbaseBriefData(
        uuid=(cb or {}).get("uuid"),
        employee_count=(cb or {}).get("num_employees_enum"),
        country=(cb or {}).get("country_code"),
        categories=(cb or {}).get("categories", []) or [],
    )

    crunchbase_block = CrunchbaseSignal(
        data=cb_data,
        confidence=cb_confidence,
        confidence_meta=cb_meta,
    )
    funding_block = FundingSignal(
        data=funding,
        confidence=funding_confidence,
        confidence_meta=funding_meta,
    )
    layoffs_block = LayoffsSignal(
        data=layoff_events,
        confidence=layoffs_confidence,
        confidence_meta=layoffs_meta,
    )
    leadership_block = LeadershipSignal(
        data=leader_changes,
        confidence=leadership_confidence,
        confidence_meta=leadership_meta,
    )
    job_posts_block = JobPostsSignal(
        data=jobs,
        confidence=jobs_confidence,
        confidence_meta=jobs_meta,
    )
    ai_block = AiMaturitySignal(
        score=ai_score,
        justification=ai_justification,
        confidence=ai_confidence,
        confidence_meta=ai_meta,
    )
    bench_block = BenchSignal(
        data=BenchSignalData(
            keywords=sorted(list(bench_keywords)),
            hits=bench_hits,
            bench_to_brief_gate_passed=bench_gate_passed,
        ),
        confidence=bench_confidence_v,
        confidence_meta=bench_meta,
    )

    return HiringSignalBrief(
        company_name=company_name,
        icp_segment=icp_segment,
        overall_confidence=overall_confidence,
        overall_confidence_weighted=overall_weighted,
        signals=EnrichmentSignals(
            crunchbase=crunchbase_block,
            funding=funding_block,
            layoffs=layoffs_block,
            leadership_change=leadership_block,
            job_posts=job_posts_block,
            ai_maturity=ai_block,
            bench=bench_block,
        ),
    )
