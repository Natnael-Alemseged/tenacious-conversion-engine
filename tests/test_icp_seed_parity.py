"""ICP doc vs classifier parity (drift detection). Fails if seed and code disagree."""

from pathlib import Path

import pytest

from agent.enrichment.pipeline import SEGMENT_1_MIN_OPEN_ROLES, _classify_segment

_SEED = (
    Path(__file__).resolve().parent.parent / "tenacious_sales_data" / "seed" / "icp_definition.md"
)


def _icp_text() -> str:
    if not _SEED.is_file():
        pytest.fail(f"Missing ICP seed doc: {_SEED}")
    return _SEED.read_text(encoding="utf-8")


def test_seed_doc_contains_segment1_open_engineering_roles() -> None:
    text = _icp_text()
    assert "five open engineering roles" in text, (
        "Segment 1 filter for open engineering headcount is missing or renamed"
    )


def test_seed_doc_contains_classification_rule_lines() -> None:
    text = _icp_text()
    # Stable substrings from `icp_definition.md` § Classification rules (order is authoritative).
    assert "If layoff in last 120 days AND fresh funding" in text
    assert "Segment 2" in text
    assert "If new CTO/VP Eng in last 90 days" in text
    assert "Segment 3" in text
    assert "If specialized capability signal AND AI-readiness" in text
    assert "Segment 4" in text
    assert "Otherwise, if fresh funding in last 180 days" in text
    assert "Segment 1" in text


def test_segment_1_min_open_roles_constant_matches_seed() -> None:
    assert SEGMENT_1_MIN_OPEN_ROLES == 5


def _cs(
    *,
    funding=None,
    layoff_events=None,
    leader_changes=None,
    ai_score: int = 0,
    open_roles: int = 0,
) -> int:
    return _classify_segment(
        funding=funding,
        layoff_events=layoff_events,
        leader_changes=leader_changes,
        ai_score=ai_score,
        open_roles=open_roles,
    )


def test_probe_layoff_and_fresh_funding_is_segment_2() -> None:
    funding = [{"investment_type": "series_b", "money_raised_usd": 18_000_000}]
    layoffs = [{"company": "Co", "laid_off_count": "10", "percentage": "12"}]
    # Dominates other signals (e.g. leadership) when both layoff and funding are present.
    leaders = [{"title": "CTO", "name": "A"}]
    assert (
        _cs(
            funding=funding,
            layoff_events=layoffs,
            leader_changes=leaders,
            open_roles=20,
        )
        == 2
    )


def test_probe_leadership_beats_fresh_funding_for_segment_1() -> None:
    funding = [{"investment_type": "series_a", "money_raised_usd": 8_000_000}]
    leaders = [{"title": "VP Engineering", "name": "B"}]
    # Rule 2 before "otherwise fresh funding" (Segment 1).
    assert _cs(funding=funding, leader_changes=leaders, open_roles=6, ai_score=0) == 3


def test_probe_capability_proxy_ai_readiness_beats_funding_for_segment_1() -> None:
    funding = [{"investment_type": "series_a", "money_raised_usd": 7_000_000}]
    # Rule 3 (AI >= 2) before Rule 4 (fresh funding -> Segment 1).
    # Classifier uses `ai_score` as a proxy probe.
    assert _cs(funding=funding, open_roles=8, ai_score=2) == 4


def test_probe_fresh_funding_open_roles_is_segment_1_when_lower_rules_absent() -> None:
    funding = [{"investment_type": "series_a", "money_raised_usd": 9_000_000}]
    assert _cs(funding=funding, open_roles=5, ai_score=0) == 1


def test_probe_abstain_when_no_rule_fires() -> None:
    # Rule 5: otherwise abstain.
    assert _cs(funding=[], layoff_events=[], leader_changes=[], open_roles=0, ai_score=0) == 0


def test_probe_abstain_when_funding_but_open_roles_below_threshold() -> None:
    # Seed Segment 1 requires at least five open engineering roles.
    funding = [{"investment_type": "series_a", "money_raised_usd": 9_000_000}]
    assert _cs(funding=funding, open_roles=4, ai_score=0) == 0
