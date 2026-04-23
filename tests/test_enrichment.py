from __future__ import annotations

from agent.enrichment.ai_maturity import confidence_phrasing, score
from agent.enrichment.pipeline import run
from agent.enrichment.schemas import HiringSignalBrief

# ---------------------------------------------------------------------------
# confidence_phrasing
# ---------------------------------------------------------------------------


def test_confidence_phrasing_direct() -> None:
    assert confidence_phrasing(0.8) == "direct"
    assert confidence_phrasing(1.0) == "direct"


def test_confidence_phrasing_hedged() -> None:
    assert confidence_phrasing(0.5) == "hedged"
    assert confidence_phrasing(0.79) == "hedged"


def test_confidence_phrasing_exploratory() -> None:
    assert confidence_phrasing(0.0) == "exploratory"
    assert confidence_phrasing(0.49) == "exploratory"


# ---------------------------------------------------------------------------
# ai_maturity.score — confidence only counts True bool signals
# ---------------------------------------------------------------------------


def test_score_false_booleans_do_not_count_toward_confidence() -> None:
    # Passing False bools should NOT inflate confidence vs not passing them at all.
    _, _, conf_with_false = score(
        {
            "ai_roles_fraction": 0.0,
            "named_ai_leadership": False,
            "modern_ml_stack": False,
        }
    )
    _, _, conf_without = score({"ai_roles_fraction": 0.0})
    assert conf_with_false == conf_without


def test_score_true_booleans_raise_confidence() -> None:
    _, _, conf_two = score({"ai_roles_fraction": 0.4, "named_ai_leadership": True})
    # score() rounds to 3 decimals; 2/6 = 0.333
    assert conf_two == 0.333

    _, _, conf_four = score(
        {
            "ai_roles_fraction": 0.35,
            "named_ai_leadership": True,
            "modern_ml_stack": True,
            "strategic_comms": True,
        }
    )
    # 4/6 = 0.667
    assert conf_four == 0.667
    assert conf_four > conf_two


def test_score_high_signals_reach_3() -> None:
    result, _, _ = score(
        {
            "ai_roles_fraction": 0.5,
            "named_ai_leadership": True,
            "github_activity": True,
            "exec_commentary": True,
            "modern_ml_stack": True,
            "strategic_comms": True,
        }
    )
    assert result == 3


def test_score_no_signals_returns_zero() -> None:
    result, _, conf = score({})
    assert result == 0
    assert conf == 0.0


# ---------------------------------------------------------------------------
# pipeline.run — icp_segment defaults to 0, not None
# ---------------------------------------------------------------------------


def test_pipeline_icp_segment_defaults_to_zero_when_no_signals(tmp_path, monkeypatch) -> None:
    odm = tmp_path / "odm.json"
    odm.write_text("[]")
    layoffs_csv = tmp_path / "layoffs.csv"
    layoffs_csv.write_text("Company,Date,Laid_Off_Count\n")

    monkeypatch.setattr(
        "agent.enrichment.pipeline.crunchbase.settings.crunchbase_odm_path", str(odm)
    )
    monkeypatch.setattr(
        "agent.enrichment.pipeline.layoffs.settings.layoffs_fyi_path", str(layoffs_csv)
    )

    result = run("UnknownCorp")
    assert result.icp_segment == 0
    roundtrip = HiringSignalBrief.model_validate(result.model_dump(mode="json"))
    assert roundtrip.overall_confidence == result.overall_confidence
    assert result.signals.funding.confidence_meta.tier == "none"
    assert result.signals.funding.confidence_meta.rationale_codes == ("funding_no_company_context",)
