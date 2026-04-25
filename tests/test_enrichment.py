from __future__ import annotations

import json

from agent.enrichment.ai_maturity import confidence_phrasing, score
from agent.enrichment.artifacts import (
    write_competitor_gap_brief,
    write_discovery_call_context_brief,
    write_hiring_signal_brief,
)
from agent.enrichment.bench_capacity import check_capacity
from agent.enrichment.competitor_gap import find_competitors
from agent.enrichment.layoffs import _approximate_headcount
from agent.enrichment.layoffs import check as layoffs_check
from agent.enrichment.pipeline import _classify_segment, run
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
    # Segment 1 now requires open_roles >= 5 — mock the scraper so this test still validates
    # the segment_1_series_a_b path without a live careers page.
    monkeypatch.setattr(
        "agent.enrichment.pipeline.job_posts.scrape",
        lambda url: {
            "url": url,
            "open_roles": 6,
            "ai_adjacent_roles": 1,
            "ai_roles_fraction": 0.167,
            "role_titles": [],
        },
    )

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


def test_write_competitor_gap_brief_emits_benchmark_backed_shape(tmp_path, monkeypatch) -> None:
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
    bench.write_text(json.dumps({"stacks": {"python": {"available_engineers": 2}}}))
    monkeypatch.setattr(
        "agent.enrichment.pipeline.crunchbase.settings.crunchbase_odm_path", str(odm)
    )
    monkeypatch.setattr(
        "agent.enrichment.pipeline.layoffs.settings.layoffs_fyi_path", str(layoffs_csv)
    )
    monkeypatch.setattr("agent.enrichment.pipeline.settings.bench_summary_path", str(bench))

    output_path = tmp_path / "competitor_gap_brief.json"
    payload = write_competitor_gap_brief(
        company_name="Acme Data",
        careers_url="https://acme.example/careers",
        path=str(output_path),
    )

    assert output_path.exists()
    saved = json.loads(output_path.read_text())
    assert saved["prospect_domain"] == "acme.example"
    assert len(saved["competitors_analyzed"]) >= 5
    assert saved["benchmark_source"] in {
        "bundled_sample_competitor_gap_brief",
        "sparse_sector_fallback_to_sample",
    }
    assert payload["gap_quality_self_check"]["all_peer_evidence_has_source_url"] is True


def test_write_discovery_call_context_brief_emits_required_sections(tmp_path, monkeypatch) -> None:
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
    bench.write_text(json.dumps({"stacks": {"python": {"available_engineers": 2}}}))
    monkeypatch.setattr(
        "agent.enrichment.pipeline.crunchbase.settings.crunchbase_odm_path", str(odm)
    )
    monkeypatch.setattr(
        "agent.enrichment.pipeline.layoffs.settings.layoffs_fyi_path", str(layoffs_csv)
    )
    monkeypatch.setattr("agent.enrichment.pipeline.settings.bench_summary_path", str(bench))

    output_path = tmp_path / "discovery_call_context_brief.md"
    content = write_discovery_call_context_brief(
        company_name="Acme Data",
        careers_url="https://acme.example/careers",
        path=str(output_path),
        prospect_name="Jordan Doe",
        prospect_title="VP Engineering",
        call_datetime_utc="2026-04-25T09:00:00Z",
        call_datetime_prospect_tz="2026-04-25 11:00 EAT",
        tenacious_lead_name="Yabebal",
        original_subject="Acme Data: quick thought",
    )

    assert output_path.exists()
    assert "# Discovery Call Context Brief" in content
    assert "## 3. Competitor gap findings" in content
    assert "## 4. Bench-to-brief match" in content
    assert "## 10. Agent confidence and unknowns" in content


# ---------------------------------------------------------------------------
# _classify_segment — ICP priority rules
# ---------------------------------------------------------------------------


def _classify(
    *, funding=None, layoff_events=None, leader_changes=None, ai_score=0, open_roles=0
) -> int:
    return _classify_segment(
        funding=funding,
        layoff_events=layoff_events,
        leader_changes=leader_changes,
        ai_score=ai_score,
        open_roles=open_roles,
    )


def test_layoff_overrides_funding_p001() -> None:
    funding = [{"investment_type": "series_b", "money_raised_usd": 18_000_000}]
    layoffs = [{"company": "TestCo", "laid_off_count": "35", "percentage": "22"}]
    seg = _classify(funding=funding, layoff_events=layoffs, open_roles=10)
    assert seg == 2, f"Expected Segment 2 (layoff > funding), got {seg}"


def test_funding_with_enough_open_roles_is_segment_1_p004() -> None:
    funding = [{"investment_type": "series_a", "money_raised_usd": 9_000_000}]
    seg = _classify(funding=funding, open_roles=5)
    assert seg == 1


def test_funding_with_zero_open_roles_abstains_p004() -> None:
    funding = [{"investment_type": "series_a", "money_raised_usd": 9_000_000}]
    seg = _classify(funding=funding, open_roles=0)
    assert seg == 0, f"Segment 1 must not fire with 0 open roles, got {seg}"


def test_approximate_headcount_enum() -> None:
    assert _approximate_headcount("c_00051_00100") == 75
    assert _approximate_headcount("c_00101_00250") == 175
    assert _approximate_headcount(None) is None
    assert _approximate_headcount("unknown_value") is None


def test_layoff_percentage_fallback_computed_p027(tmp_path) -> None:
    csv_content = "Company,Date,Laid_Off_Count,Percentage\nTestCo,2026-03-01,50,\n"
    csv_file = tmp_path / "layoffs.csv"
    csv_file.write_text(csv_content)
    results = layoffs_check("TestCo", path=str(csv_file), employee_count_enum="c_00251_00500")
    assert results[0]["percentage"] != ""
    pct = float(results[0]["percentage"])
    assert 10.0 < pct < 20.0, f"Expected ~13%, got {pct}"
    assert results[0].get("percentage_source") == "computed"


def test_layoff_percentage_preserved_when_present(tmp_path) -> None:
    csv_content = "Company,Date,Laid_Off_Count,Percentage\nTestCo,2026-03-01,50,22\n"
    csv_file = tmp_path / "layoffs.csv"
    csv_file.write_text(csv_content)
    results = layoffs_check("TestCo", path=str(csv_file), employee_count_enum="c_00251_00500")
    assert results[0]["percentage"] == "22"
    assert results[0].get("percentage_source") == "reported"


def test_github_fork_only_does_not_inflate_score_p028() -> None:
    """github_activity=True with github_fork_only=True must not raise score above baseline."""
    score_forks, _, _ = score({"github_activity": True, "github_fork_only": True})
    score_none, _, _ = score({})
    assert score_forks == score_none, (
        f"Fork-only activity should not inflate score: {score_none} → {score_forks}"
    )


def test_github_original_commits_inflate_score_p028() -> None:
    """github_activity=True without github_fork_only raises score."""
    score_original, _, _ = score({"github_activity": True})
    score_none, _, _ = score({})
    assert score_original > score_none


def test_github_fork_only_does_not_count_toward_confidence() -> None:
    _, _, conf_forks = score({"github_activity": True, "github_fork_only": True})
    _, _, conf_none = score({})
    assert conf_forks == conf_none


# ---------------------------------------------------------------------------
# bench_capacity.check_capacity — P-009 through P-012
# ---------------------------------------------------------------------------

_SAMPLE_BENCH = {
    "stacks": {
        "go": {
            "available_engineers": 3,
            "seniority_mix": {"junior_0_2_yrs": 1, "mid_2_4_yrs": 1, "senior_4_plus_yrs": 1},
            "time_to_deploy_days": 14,
            "note": "",
        },
        "ml": {
            "available_engineers": 5,
            "seniority_mix": {"junior_0_2_yrs": 2, "mid_2_4_yrs": 2, "senior_4_plus_yrs": 1},
            "time_to_deploy_days": 10,
            "note": "",
        },
        "infra": {
            "available_engineers": 4,
            "seniority_mix": {"junior_0_2_yrs": 1, "mid_2_4_yrs": 2, "senior_4_plus_yrs": 1},
            "time_to_deploy_days": 14,
            "note": "",
        },
        "fullstack_nestjs": {
            "available_engineers": 2,
            "seniority_mix": {"junior_0_2_yrs": 0, "mid_2_4_yrs": 2, "senior_4_plus_yrs": 0},
            "time_to_deploy_days": 14,
            "note": "Currently committed on the Modo Compass engagement through Q3 2026.",
        },
    }
}


def test_capacity_check_blocks_overcount_p009() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="go", requested_count=10)
    assert not result["feasible"]
    assert result["available"] == 3
    assert "10" in result["reason"] or "3" in result["reason"]


def test_capacity_check_blocks_commitment_note_p010() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="fullstack_nestjs", requested_count=1)
    assert not result["feasible"]
    assert "committed" in result["reason"].lower() or "Q3 2026" in result["reason"]


def test_capacity_check_blocks_seniority_shortfall_p011() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="ml", requested_count=2, seniority="senior")
    assert not result["feasible"]
    assert result["available_seniority"] == 1


def test_capacity_check_blocks_lead_time_p012() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="infra", requested_count=1, lead_days=7)
    assert not result["feasible"]
    assert "14" in result["reason"] or "lead" in result["reason"].lower()


def test_capacity_check_passes_valid_request() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="go", requested_count=2)
    assert result["feasible"]


def test_capacity_check_unknown_stack_returns_clear_reason() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="rust", requested_count=1)
    assert not result["feasible"]
    assert "not present" in result["reason"]


def test_capacity_check_unknown_seniority_blocks() -> None:
    result = check_capacity(_SAMPLE_BENCH, stack="go", requested_count=1, seniority="principal")
    assert not result["feasible"]
    assert "not recognised" in result["reason"].lower() or "recognised" in result["reason"]


# ---------------------------------------------------------------------------
# find_competitors — P-031 live ODM sector-peer lookup
# ---------------------------------------------------------------------------


def test_find_competitors_returns_sector_peers() -> None:
    odm_data = [
        {
            "name": "PeerCo",
            "categories": ["Artificial Intelligence", "Machine Learning"],
        },
        {
            "name": "UnrelatedCo",
            "categories": ["Real Estate"],
        },
    ]
    peers = find_competitors(
        prospect_name="TestCo",
        categories=["Artificial Intelligence"],
        odm_data=odm_data,
    )
    names = [p["name"] for p in peers]
    assert "PeerCo" in names
    assert "UnrelatedCo" not in names


def test_find_competitors_excludes_prospect() -> None:
    odm_data = [
        {"name": "TestCo", "categories": ["AI"]},
        {"name": "OtherCo", "categories": ["AI"]},
    ]
    peers = find_competitors(
        prospect_name="TestCo",
        categories=["AI"],
        odm_data=odm_data,
    )
    assert all(p["name"] != "TestCo" for p in peers)


def test_find_competitors_empty_when_no_match() -> None:
    peers = find_competitors(
        prospect_name="TestCo",
        categories=["Fintech"],
        odm_data=[{"name": "AICo", "categories": ["Machine Learning"]}],
    )
    assert peers == []
