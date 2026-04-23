from __future__ import annotations

from typing import Any

from agent.enrichment.schemas import ConfidenceMeta, tier_from_score


def _meta(score: float, *, factors: dict[str, float], codes: tuple[str, ...]) -> ConfidenceMeta:
    return ConfidenceMeta(tier=tier_from_score(score), factors=dict(factors), rationale_codes=codes)


def crunchbase_confidence(cb: dict[str, Any] | None) -> tuple[float, ConfidenceMeta]:
    if cb:
        return 1.0, _meta(1.0, factors={"company_resolved": 1.0}, codes=("crunchbase_match",))
    return 0.0, _meta(0.0, factors={}, codes=("crunchbase_no_match",))


def funding_confidence(
    *,
    funding: list[dict[str, Any]],
    cb: dict[str, Any] | None,
) -> tuple[float, ConfidenceMeta]:
    if funding:
        return 1.0, _meta(
            1.0,
            factors={"recent_funding_in_window": 1.0},
            codes=("funding_recent_round",),
        )
    if not cb:
        return 0.0, _meta(0.0, factors={}, codes=("funding_no_company_context",))

    rounds: list[dict[str, Any]] = cb.get("funding_rounds", []) or []
    if rounds:
        score = 0.45
        return score, _meta(
            score,
            factors={"company_resolved": 0.25, "no_round_in_window": 0.2},
            codes=("funding_stale_or_outside_window",),
        )
    score = 0.35
    return score, _meta(
        score,
        factors={"company_resolved": 0.35},
        codes=("funding_no_rounds_on_record",),
    )


def layoffs_confidence(
    *,
    layoff_events: list[dict[str, Any]],
    cb: dict[str, Any] | None,
) -> tuple[float, ConfidenceMeta]:
    if layoff_events:
        return 1.0, _meta(
            1.0,
            factors={"layoff_rows_matched": 1.0},
            codes=("layoffs_positive_signal",),
        )
    if cb:
        score = 0.38
        return score, _meta(
            score,
            factors={"company_resolved": 0.38},
            codes=("layoffs_no_match_in_corpus",),
        )
    return 0.0, _meta(0.0, factors={}, codes=("layoffs_no_company_context",))


def leadership_confidence(
    *,
    leader_changes: list[dict[str, Any]],
    cb: dict[str, Any] | None,
) -> tuple[float, ConfidenceMeta]:
    if leader_changes:
        return 1.0, _meta(
            1.0,
            factors={"leadership_rows_in_window": 1.0},
            codes=("leadership_transition_signal",),
        )
    if cb:
        score = 0.38
        return score, _meta(
            score,
            factors={"company_resolved": 0.38},
            codes=("leadership_no_recent_change",),
        )
    return 0.0, _meta(0.0, factors={}, codes=("leadership_no_company_context",))


def job_posts_confidence(*, careers_url: str, jobs: dict[str, Any]) -> tuple[float, ConfidenceMeta]:
    if not careers_url:
        return 0.0, _meta(0.0, factors={}, codes=("job_posts_no_careers_url",))

    err = jobs.get("error")
    if err:
        score = 0.28
        return score, _meta(
            score,
            factors={"fetch_attempted": 0.28},
            codes=("job_posts_fetch_failed", str(err)),
        )

    open_roles = int(jobs.get("open_roles") or 0)
    if open_roles > 0:
        score = 0.95
        return score, _meta(
            score,
            factors={"careers_page_ok": 0.5, "open_roles_observed": 0.45},
            codes=("job_posts_roles_detected",),
        )

    score = 0.55
    return score, _meta(
        score,
        factors={"careers_page_ok": 0.55},
        codes=("job_posts_zero_roles_parsed",),
    )


def bench_confidence(*, bench: Any, bench_keywords: set[str]) -> tuple[float, ConfidenceMeta]:
    if not bench:
        return 0.0, _meta(0.0, factors={}, codes=("bench_corpus_missing",))
    if bench_keywords:
        return 1.0, _meta(1.0, factors={"keyword_lexicon_loaded": 1.0}, codes=("bench_loaded",))
    # Non-empty bench payload but no extractable keywords — keep score high (historical behavior).
    return 1.0, _meta(
        1.0,
        factors={"bench_record_present": 1.0},
        codes=("bench_loaded_empty_keyword_extract",),
    )


def ai_maturity_confidence_meta(ai_confidence: float) -> ConfidenceMeta:
    return _meta(
        ai_confidence,
        factors={"signal_coverage": round(ai_confidence, 3)},
        codes=("ai_maturity_weighted_signals",),
    )


# Weights for overall_confidence_weighted (must sum to 1.0)
_WEIGHTED_SIGNAL_KEYS = (
    "crunchbase",
    "funding",
    "layoffs",
    "leadership_change",
    "job_posts",
)
_WEIGHTS: dict[str, float] = {
    "crunchbase": 0.28,
    "funding": 0.18,
    "layoffs": 0.12,
    "leadership_change": 0.12,
    "job_posts": 0.30,
}


def weighted_overall_confidence(signal_scores: dict[str, float]) -> float:
    total = 0.0
    for key in _WEIGHTED_SIGNAL_KEYS:
        total += signal_scores.get(key, 0.0) * _WEIGHTS[key]
    return round(total, 3)
