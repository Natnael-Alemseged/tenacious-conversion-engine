from __future__ import annotations

from agent.enrichment.ai_maturity import confidence_phrasing, score
from agent.enrichment.pipeline import run

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
# ai_maturity.score — confidence rises with more signals provided
# ---------------------------------------------------------------------------


def test_score_with_two_signals_gives_low_confidence() -> None:
    _, _, conf = score({"ai_roles_fraction": 0.4, "named_ai_leadership": True})
    # score() rounds to 3 decimals; 2/6 = 0.333
    assert conf == 0.333


def test_score_with_four_signals_gives_higher_confidence() -> None:
    _, _, conf = score(
        {
            "ai_roles_fraction": 0.35,
            "named_ai_leadership": True,
            "modern_ml_stack": False,
            "strategic_comms": False,
        }
    )
    # 4/6 = 0.667
    assert conf == 0.667


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
    # Empty ODM and layoffs files → no signals fire
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
    assert result["icp_segment"] == 0


def test_pipeline_modern_ml_stack_derived_from_job_titles(monkeypatch) -> None:
    """modern_ml_stack signal is True when job titles contain ML stack keywords."""
    fake_jobs = {
        "open_roles": 10,
        "ai_adjacent_roles": 3,
        "ai_roles_fraction": 0.3,
        "role_titles": ["dbt Engineer", "ML Platform Lead"],
    }
    monkeypatch.setattr("agent.enrichment.pipeline.crunchbase.lookup", lambda _: None)
    monkeypatch.setattr("agent.enrichment.pipeline.crunchbase.recent_funding", lambda _: [])
    monkeypatch.setattr("agent.enrichment.pipeline.crunchbase.leadership_changes", lambda _: [])
    monkeypatch.setattr("agent.enrichment.pipeline.layoffs.check", lambda _: [])
    monkeypatch.setattr("agent.enrichment.pipeline.job_posts.scrape", lambda _: fake_jobs)

    result = run("TechCo", careers_url="https://techco.com/jobs")
    # With modern_ml_stack=True and ai_roles_fraction=0.3, score should be ≥ 1
    assert result["signals"]["ai_maturity"]["score"] >= 1
    # 3/6 signals present: ai_roles_fraction, named_ai_leadership=False, modern_ml_stack=True
    assert result["signals"]["ai_maturity"]["confidence"] >= 0.5


def test_pipeline_strategic_comms_derived_from_cb_categories(monkeypatch) -> None:
    fake_cb = {
        "uuid": "abc",
        "num_employees_enum": "1001-5000",
        "country_code": "USA",
        "categories": ["Artificial Intelligence", "SaaS"],
    }
    monkeypatch.setattr("agent.enrichment.pipeline.crunchbase.lookup", lambda _: fake_cb)
    monkeypatch.setattr("agent.enrichment.pipeline.crunchbase.recent_funding", lambda _: [])
    monkeypatch.setattr("agent.enrichment.pipeline.crunchbase.leadership_changes", lambda _: [])
    monkeypatch.setattr("agent.enrichment.pipeline.layoffs.check", lambda _: [])

    result = run("AICo")
    # strategic_comms=True from "Artificial Intelligence" category → confidence ≥ 2/6 (0.333)
    assert result["signals"]["ai_maturity"]["confidence"] >= 0.333
