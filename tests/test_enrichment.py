from __future__ import annotations

import json

from agent.enrichment.ai_maturity import confidence_phrasing, score
from agent.enrichment.artifacts import write_hiring_signal_brief
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


def test_pipeline_uses_stack_based_bench_summary(tmp_path, monkeypatch) -> None:
    odm = tmp_path / "odm.json"
    odm.write_text(
        json.dumps(
            [
                {
                    "name": "Acme Data",
                    "categories": ["analytics", "python", "snowflake"],
                    "website": "https://acme.example",
                }
            ]
        )
    )
    layoffs_csv = tmp_path / "layoffs.csv"
    layoffs_csv.write_text("Company,Date,Laid_Off_Count\n")
    bench = tmp_path / "bench.json"
    bench.write_text(
        json.dumps(
            {
                "stacks": {
                    "python": {"available_engineers": 2, "skill_subsets": ["FastAPI"]},
                    "data": {"available_engineers": 1, "skill_subsets": ["Snowflake", "dbt"]},
                    "ml": {"available_engineers": 0, "skill_subsets": ["LangChain"]},
                }
            }
        )
    )

    monkeypatch.setattr(
        "agent.enrichment.pipeline.crunchbase.settings.crunchbase_odm_path", str(odm)
    )
    monkeypatch.setattr(
        "agent.enrichment.pipeline.layoffs.settings.layoffs_fyi_path", str(layoffs_csv)
    )
    monkeypatch.setattr("agent.enrichment.pipeline.settings.bench_summary_path", str(bench))

    result = run("Acme Data", careers_url="")

    assert result.tech_stack == ["Python", "Snowflake"]
    assert result.signals.bench.data.required_stacks == ["data", "python"]
    assert result.signals.bench.data.gaps == []
    assert result.signals.bench.data.bench_to_brief_gate_passed is True


def test_write_hiring_signal_brief_emits_public_schema_shape(tmp_path, monkeypatch) -> None:
    odm = tmp_path / "odm.json"
    odm.write_text(
        json.dumps(
            [
                {
                    "name": "Acme Data",
                    "categories": ["analytics", "python", "snowflake"],
                    "website": "https://acme.example",
                    "funding_rounds": [
                        {
                            "announced_on": "2026-04-01T00:00:00Z",
                            "investment_type": "series_b",
                            "money_raised_usd": 14000000,
                        }
                    ],
                }
            ]
        )
    )
    layoffs_csv = tmp_path / "layoffs.csv"
    layoffs_csv.write_text("Company,Date,Laid_Off_Count\n")
    bench = tmp_path / "bench.json"
    bench.write_text(
        json.dumps(
            {
                "stacks": {
                    "python": {"available_engineers": 2, "skill_subsets": ["FastAPI"]},
                    "data": {"available_engineers": 1, "skill_subsets": ["Snowflake", "dbt"]},
                }
            }
        )
    )
    monkeypatch.setattr(
        "agent.enrichment.pipeline.crunchbase.settings.crunchbase_odm_path", str(odm)
    )
    monkeypatch.setattr(
        "agent.enrichment.pipeline.layoffs.settings.layoffs_fyi_path", str(layoffs_csv)
    )
    monkeypatch.setattr("agent.enrichment.pipeline.settings.bench_summary_path", str(bench))

    output_path = tmp_path / "hiring_signal_brief.json"
    write_hiring_signal_brief(
        company_name="Acme Data",
        careers_url="https://acme.example/careers",
        path=str(output_path),
    )

    payload = json.loads(output_path.read_text())
    assert payload["prospect_name"] == "Acme Data"
    assert payload["prospect_domain"] == "acme.example"
    assert payload["primary_segment_match"] == "segment_1_series_a_b"
    assert payload["bench_to_brief_match"]["bench_available"] is True
    assert "generated_at" in payload
    assert "data_sources_checked" in payload
