from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from agent.core.config import settings
from agent.enrichment import ai_maturity, crunchbase, job_posts, layoffs
from agent.enrichment.ai_maturity_collectors.collectors import collect_all_ai_maturity_signals
from agent.enrichment.bench_summary import bench_match, infer_required_stacks, load
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
from agent.enrichment.velocity_store import (
    VelocitySnapshot,
    append_snapshot,
    compute_60_day_velocity,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _company_domain(cb: dict[str, Any] | None, careers_url: str) -> str:
    candidates = (
        (cb or {}).get("domain"),
        (cb or {}).get("website"),
        (cb or {}).get("homepage_url"),
        careers_url,
    )
    for candidate in candidates:
        if not candidate:
            continue
        parsed = urlparse(str(candidate))
        if parsed.netloc:
            return parsed.netloc.lower()
        value = str(candidate).strip().lower().removeprefix("https://").removeprefix("http://")
        if "/" in value:
            value = value.split("/", 1)[0]
        if value:
            return value
    return ""


def _segment_confidence(
    *,
    icp_segment: int,
    funding_confidence: float,
    layoffs_confidence: float,
    leadership_confidence: float,
    jobs_confidence: float,
    ai_confidence: float,
) -> float:
    if icp_segment == 1:
        return funding_confidence
    if icp_segment == 2:
        return layoffs_confidence
    if icp_segment == 3:
        return leadership_confidence
    if icp_segment == 4:
        return max(ai_confidence, jobs_confidence)
    return max(funding_confidence, layoffs_confidence, leadership_confidence, jobs_confidence) * 0.5


SEGMENT_1_MIN_OPEN_ROLES: int = 5


def _classify_segment(
    *,
    funding: list[dict[str, Any]] | None,
    layoff_events: list[dict[str, Any]] | None,
    leader_changes: list[dict[str, Any]] | None,
    ai_score: int,
    open_roles: int,
) -> int:
    """Return ICP segment with correct priority: layoff > funding > leadership > AI."""
    if layoff_events:
        return 2
    if funding and open_roles >= SEGMENT_1_MIN_OPEN_ROLES:
        return 1
    if leader_changes:
        return 3
    if ai_score >= 2:
        return 4
    return 0


def _infer_tech_stack(
    *,
    categories: list[str],
    role_titles: list[str],
) -> list[str]:
    aliases = {
        "python": "Python",
        "django": "Python",
        "fastapi": "Python",
        "flask": "Python",
        "go": "Go",
        "golang": "Go",
        "dbt": "dbt",
        "snowflake": "Snowflake",
        "databricks": "Databricks",
        "airflow": "Airflow",
        "fivetran": "Fivetran",
        "quicksight": "QuickSight",
        "powerbi": "PowerBI",
        "mlops": "MLOps",
        "langchain": "LangChain",
        "langgraph": "LangGraph",
        "llm": "LLM",
        "pytorch": "PyTorch",
        "hugging face": "Hugging Face",
        "huggingface": "Hugging Face",
        "aws": "AWS",
        "gcp": "GCP",
        "terraform": "Terraform",
        "kubernetes": "Kubernetes",
        "docker": "Docker",
        "react": "React",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "typescript": "TypeScript",
        "tailwind": "Tailwind",
        "node.js": "Node.js",
        "nestjs": "NestJS",
        "prisma": "Prisma",
        "typeorm": "TypeORM",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
    }
    haystack = " ".join([*categories, *role_titles]).lower()
    inferred: list[str] = []
    for token, label in aliases.items():
        if token in haystack and label not in inferred:
            inferred.append(label)
    return inferred


def run(company_name: str, careers_url: str = "") -> HiringSignalBrief:
    """Return hiring_signal_brief with typed signals, scores, and confidence metadata."""

    cb = crunchbase.lookup(company_name)
    cb_confidence, cb_meta = score_crunchbase_confidence(cb)

    funding = crunchbase.recent_funding(company_name)
    funding_confidence, funding_meta = score_funding_confidence(funding=funding, cb=cb)

    layoff_events = layoffs.check(
        company_name,
        employee_count_enum=(cb or {}).get("num_employees_enum"),
    )
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
    if careers_url and jobs and not jobs.get("error"):
        domain_for_velocity = _company_domain(cb, careers_url)
        if domain_for_velocity:
            append_snapshot(
                settings.hiring_velocity_store_path,
                VelocitySnapshot(
                    recorded_at=str(jobs.get("recorded_at") or _now_iso()),
                    domain=domain_for_velocity,
                    open_roles=int(jobs.get("open_roles") or 0),
                    ai_adjacent_roles=int(jobs.get("ai_adjacent_roles") or 0),
                    source_url=str(jobs.get("url") or careers_url),
                ),
            )
            jobs.update(
                compute_60_day_velocity(
                    path=settings.hiring_velocity_store_path,
                    domain=domain_for_velocity,
                    open_roles_today=int(jobs.get("open_roles") or 0),
                )
            )
    jobs_confidence, jobs_meta = score_job_posts_confidence(careers_url=careers_url, jobs=jobs)

    role_titles = list(jobs.get("role_titles") or [])
    categories = (cb or {}).get("categories", []) or []
    tech_stack = _infer_tech_stack(categories=categories, role_titles=role_titles)
    company_domain = _company_domain(cb, careers_url)

    ai_signals: dict[str, Any] = {}
    if careers_url and not jobs.get("error") and jobs.get("open_roles", 0) > 0:
        ai_signals["ai_roles_fraction"] = jobs.get("ai_roles_fraction", 0.0)

    named_ai_leadership = any(
        ("ai" in (c.get("title") or "") or "scientist" in (c.get("title") or ""))
        for c in (leader_changes or [])
    )
    if leader_changes:
        ai_signals["named_ai_leadership"] = named_ai_leadership

    extra_signals, ai_evidence, ai_evidence_strength = collect_all_ai_maturity_signals(
        company_domain=company_domain,
        tech_stack=tech_stack,
        job_role_titles=role_titles,
    )
    ai_signals.update(extra_signals)
    ai_score, ai_justification, ai_confidence = ai_maturity.score(ai_signals)
    ai_meta = ai_maturity_confidence_meta(ai_confidence)

    icp_segment = _classify_segment(
        funding=funding,
        layoff_events=layoff_events,
        leader_changes=leader_changes,
        ai_score=ai_score,
        open_roles=jobs.get("open_roles", 0),
    )
    segment_confidence = _segment_confidence(
        icp_segment=icp_segment,
        funding_confidence=funding_confidence,
        layoffs_confidence=layoffs_confidence,
        leadership_confidence=leadership_confidence,
        jobs_confidence=jobs_confidence,
        ai_confidence=ai_confidence,
    )

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
    required_stacks = infer_required_stacks(
        bench,
        tech_stack=tech_stack,
        role_titles=role_titles,
        categories=categories,
        ai_score=ai_score,
    )
    bench_result = bench_match(bench, required_stacks=required_stacks)
    bench_hits = sorted(required_stacks)
    bench_gate_passed = bool(required_stacks) and bool(bench_result["bench_available"])
    bench_confidence_v, bench_meta = bench_confidence(
        bench=bench, bench_keywords=set(required_stacks)
    )
    generated_at = _now_iso()

    cb_data = CrunchbaseBriefData(
        uuid=(cb or {}).get("uuid"),
        employee_count=(cb or {}).get("num_employees_enum"),
        country=(cb or {}).get("country_code"),
        categories=categories,
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
        evidence_strength=ai_evidence_strength,
        evidence=ai_evidence,
    )
    bench_block = BenchSignal(
        data=BenchSignalData(
            keywords=sorted(required_stacks),
            hits=bench_hits,
            bench_to_brief_gate_passed=bench_gate_passed,
            required_stacks=required_stacks,
            gaps=list(bench_result["gaps"]),
            available_counts=dict(bench_result["available_counts"]),
        ),
        confidence=bench_confidence_v,
        confidence_meta=bench_meta,
    )
    data_sources_checked = [
        {
            "source": "crunchbase_odm",
            "status": "success" if cb else "no_data",
            "fetched_at": generated_at,
        },
        {
            "source": "layoffs_fyi",
            "status": "success" if layoff_events else "no_data",
            "fetched_at": generated_at,
        },
        {
            "source": "leadership_changes",
            "status": "success" if leader_changes else "no_data",
            "fetched_at": generated_at,
        },
    ]
    if careers_url:
        data_sources_checked.append(
            {
                "source": "company_careers_page",
                "status": (
                    "error"
                    if jobs.get("error")
                    else ("success" if jobs.get("open_roles", 0) > 0 else "no_data")
                ),
                "error_message": str(jobs.get("error", "")),
                "fetched_at": generated_at,
            }
        )
    honesty_flags: list[str] = []
    if jobs_confidence < 0.6:
        honesty_flags.append("weak_hiring_velocity_signal")
    if ai_confidence < 0.6:
        honesty_flags.append("weak_ai_maturity_signal")
    if funding and layoff_events:
        honesty_flags.append("conflicting_segment_signals")
        honesty_flags.append("layoff_overrides_funding")
    if bench_result["gaps"]:
        honesty_flags.append("bench_gap_detected")
    if tech_stack:
        honesty_flags.append("tech_stack_inferred_not_confirmed")

    return HiringSignalBrief(
        company_name=company_name,
        company_domain=company_domain,
        generated_at=generated_at,
        icp_segment=icp_segment,
        segment_confidence=round(segment_confidence, 3),
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
        tech_stack=tech_stack,
        data_sources_checked=data_sources_checked,
        honesty_flags=honesty_flags,
    )
