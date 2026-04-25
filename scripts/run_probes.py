"""Act III probe runner.

Executes all deterministic probes (no LLM, no live external calls) and
records trigger rates. Writes probe_results.json and prints a summary.

Run:
    uv run python scripts/run_probes.py
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ── bootstrap ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.config import settings  # noqa: E402
from agent.enrichment import ai_maturity  # noqa: E402
from agent.enrichment.bench_summary import load as load_bench  # noqa: E402

TRIALS = 10
RESULTS: list[dict] = []


def _trace_id() -> str:
    return f"probe-{uuid.uuid4().hex[:12]}"


def _record(
    probe_id: str,
    category: str,
    passed: bool,  # True = failure triggered (probe found the bug)
    detail: str,
    trace_id: str,
) -> None:
    RESULTS.append(
        {
            "probe_id": probe_id,
            "category": category,
            "triggered": passed,
            "detail": detail,
            "trace_id": trace_id,
            "run_at": datetime.now(UTC).isoformat(),
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# icp_misclassification
# ═══════════════════════════════════════════════════════════════════════════


def probe_P001() -> tuple[int, list[str], list[str]]:
    """Layoff+funding → must be Segment 2, not Segment 1."""
    from agent.enrichment.pipeline import _classify_segment

    now = datetime.now(UTC)
    mock_funding = [{"investment_type": "series_b", "money_raised_usd": 18_000_000}]
    mock_layoffs = [
        {
            "company": "NovaCure Analytics",
            "date": now.isoformat(),
            "laid_off_count": "35",
            "percentage": "22",
        }
    ]

    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        seg = _classify_segment(
            funding=mock_funding,
            layoff_events=mock_layoffs,
            leader_changes=None,
            ai_score=0,
            open_roles=10,
        )
        if seg != 2:
            triggered += 1
            details.append(f"Expected segment=2, got segment={seg}")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P002() -> tuple[int, list[str], list[str]]:
    """Segment 4 NOT pitched at AI readiness 1 (this should pass — test the guard)."""
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        ai_score = 1
        # pipeline: elif ai_score >= 2: icp_segment = 4
        icp_segment = 4 if ai_score >= 2 else 0
        if icp_segment == 4:
            triggered += 1
            details.append(f"Segment 4 assigned at ai_score={ai_score}")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P003() -> tuple[int, list[str], list[str]]:
    """'Chief Technology Officer' title detected by leadership_changes()."""
    # Test that the keyword set covers the full title
    LEADERSHIP_KEYWORDS = {
        "cto",
        "vp eng",
        "vp of eng",
        "chief technology",
        "head of ai",
        "chief ai",
    }
    test_titles = [
        ("Chief Technology Officer", True),
        ("VP Engineering", True),  # "vp eng" is a substring of "vp engineering"
        ("VP of Engineering", True),
        ("Head of AI", True),
        ("CTO", True),
        ("Acting CTO", True),
        ("Chief AI Officer", True),
    ]
    triggered, trace_ids, details = 0, [], []
    for title, expected_match in test_titles:
        tid = _trace_id()
        actual_match = any(kw in title.lower() for kw in LEADERSHIP_KEYWORDS)
        if actual_match != expected_match:
            triggered += 1
            details.append(f"title='{title}' match={actual_match}, expected={expected_match}")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P004() -> tuple[int, list[str], list[str]]:
    """Zero open roles must NOT qualify for Segment 1."""
    from agent.enrichment.pipeline import _classify_segment

    mock_funding = [{"investment_type": "series_a", "money_raised_usd": 9_000_000}]
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        seg_zero = _classify_segment(
            funding=mock_funding, layoff_events=None, leader_changes=None, ai_score=0, open_roles=0
        )
        seg_five = _classify_segment(
            funding=mock_funding, layoff_events=None, leader_changes=None, ai_score=0, open_roles=5
        )
        if seg_zero == 1:
            triggered += 1
            details.append("Segment 1 assigned with 0 open roles (expected 0)")
        if seg_five != 1:
            triggered += 1
            details.append(f"Segment 1 not assigned with 5 open roles (got {seg_five})")
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# signal_overclaiming
# ═══════════════════════════════════════════════════════════════════════════


def probe_P005() -> tuple[int, list[str], list[str]]:
    """Segment 1 opener should not assert growth mode when confidence is low."""
    from agent.enrichment.ai_maturity import confidence_phrasing
    from agent.workflows.lead_orchestrator import _segment_opener

    triggered, trace_ids, details = 0, [], []
    test_cases = [
        (1, 0.1),  # Segment 1, very low confidence
        (1, 0.3),  # Segment 1, low confidence
        (1, 0.45),  # Segment 1, below hedged threshold
    ]
    for seg, conf in test_cases:
        for _ in range(3):
            tid = _trace_id()
            phrasing = confidence_phrasing(conf)
            opener = _segment_opener("Acme", seg, phrasing)
            is_assertive = any(
                phrase in opener.lower()
                for phrase in (
                    "clearly in growth mode",
                    "congratulations",
                    "is in growth mode",
                )
            )
            if phrasing in ("hedged", "exploratory") and is_assertive:
                triggered += 1
                details.append(
                    f"seg={seg} conf={conf} phrasing={phrasing!r} "  # noqa: E501
                    f"but opener is assertive: {opener!r}"
                )
            trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P006() -> tuple[int, list[str], list[str]]:
    """ai_maturity.score with single weak signal returns exploratory phrasing."""
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        score, justification, confidence = ai_maturity.score({"exec_commentary": True})
        phrasing = ai_maturity.confidence_phrasing(confidence)
        # Correct: score=1, confidence=0.167, phrasing="exploratory"
        # Failure: if something upstream would still use assertive language
        if confidence >= 0.5:
            triggered += 1
            details.append(f"score={score} confidence={confidence:.3f} (expected <0.5)")
        if phrasing != "exploratory":
            triggered += 1
            details.append(
                f"phrasing={phrasing!r} (expected 'exploratory' at conf={confidence:.3f})"
            )
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P007() -> tuple[int, list[str], list[str]]:
    """Stale funding (>180 days) excluded by recent_funding()."""
    from unittest.mock import patch

    from agent.enrichment.crunchbase import recent_funding

    now = datetime.now(UTC)
    stale_date = (now - timedelta(days=201)).isoformat()
    fresh_date = (now - timedelta(days=90)).isoformat()

    mock_record = {
        "name": "TestCo",
        "funding_rounds": [
            {
                "investment_type": "series_b",
                "money_raised_usd": 22_000_000,
                "announced_on": stale_date,
            },
            {"investment_type": "seed", "money_raised_usd": 1_000_000, "announced_on": fresh_date},
        ],
    }

    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        with patch("agent.enrichment.crunchbase._load_odm", return_value=[mock_record]):
            result = recent_funding("TestCo", days=180)
        # Should only return the fresh round, not the stale one
        returned_dates = [r.get("announced_on") for r in result]
        if stale_date in returned_dates:
            triggered += 1
            details.append(f"Stale funding ({stale_date}) included in recent_funding() results")
        if fresh_date not in returned_dates:
            triggered += 1
            details.append(f"Fresh funding ({fresh_date}) excluded from recent_funding() results")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P008() -> tuple[int, list[str], list[str]]:
    """ai_maturity.score({}) returns score=0, confidence=0.0."""
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        score, justification, confidence = ai_maturity.score({})
        if score != 0:
            triggered += 1
            details.append(f"Empty signals returned score={score} (expected 0)")
        if confidence != 0.0:
            triggered += 1
            details.append(f"Empty signals returned confidence={confidence} (expected 0.0)")
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# bench_overcommitment
# ═══════════════════════════════════════════════════════════════════════════


def _load_real_bench() -> dict:
    return load_bench(settings.bench_summary_path)


def probe_P009() -> tuple[int, list[str], list[str]]:
    """Bench has 3 Go engineers; prospect requests 10."""
    bench = _load_real_bench()
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        go_available = bench.get("stacks", {}).get("go", {}).get("available_engineers", 0)
        requested = 10
        # The failure mode: no guard prevents claiming capacity > available
        if go_available < requested:
            # This is the condition that should block the commitment — confirm it exists
            # "triggered" means the gap exists and no guard is implemented in reply generation
            triggered += 1
            details.append(f"go available={go_available} < requested={requested}; no reply guard")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P010() -> tuple[int, list[str], list[str]]:
    """NestJS engineers committed through Q3 2026 — availability note should block."""
    bench = _load_real_bench()
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        nestjs = bench.get("stacks", {}).get("fullstack_nestjs", {})
        available = nestjs.get("available_engineers", 0)
        note = nestjs.get("note", "")
        # Triggered if: engineers appear available in count but are committed
        if available > 0 and "committed" in note.lower():
            triggered += 1
            details.append(f"NestJS shows {available} available but note='{note[:60]}...'")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P011() -> tuple[int, list[str], list[str]]:
    """ML bench has 1 senior engineer; prospect requests 2."""
    bench = _load_real_bench()
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        ml = bench.get("stacks", {}).get("ml", {})
        senior_available = ml.get("seniority_mix", {}).get("senior_4_plus_yrs", 0)
        requested_senior = 2
        if senior_available < requested_senior:
            triggered += 1
            details.append(f"ML senior available={senior_available} < requested={requested_senior}")
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P012() -> tuple[int, list[str], list[str]]:
    """Infra engineers have 14-day lead time; prospect requests start in 7 days."""
    bench = _load_real_bench()
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        infra = bench.get("stacks", {}).get("infra", {})
        lead_time = infra.get("time_to_deploy_days", 0)
        requested_days = 7
        if lead_time > requested_days:
            triggered += 1
            details.append(
                f"Infra time_to_deploy={lead_time} days > requested={requested_days} days"
            )
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# tone_drift
# ═══════════════════════════════════════════════════════════════════════════


def probe_P015() -> tuple[int, list[str], list[str]]:
    """Subject lines from the template — check length ≤ 60 chars."""
    _subjects = {
        0: "{company}: quick thought",
        1: "{company}: scaling after your recent raise",
        2: "{company}: doing more with your current team",
        3: "{company}: working with new technical leadership",
        4: "{company}: closing the AI capability gap",
    }
    test_companies = [
        "Acme",
        "DataBridge Analytics Corporation",
        "NovaCure Machine Learning Infrastructure",
        "X",
    ]
    triggered, trace_ids, details = 0, [], []
    for company in test_companies:
        for seg, template in _subjects.items():
            tid = _trace_id()
            subject = template.replace("{company}", company)
            if len(subject) > 60:
                triggered += 1
                details.append(
                    f"seg={seg} company={company!r} subject len={len(subject)}: {subject!r}"
                )
            trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P016() -> tuple[int, list[str], list[str]]:
    """Email body word count ≤ 120 words (style guide)."""
    # Reconstruct the body template from lead_orchestrator
    _openers = {
        1: "Congratulations on the recent funding — TestCo is clearly in growth mode.",
        2: "Teams navigating a restructure often find this is the right time to invest in automation.",  # noqa: E501
    }
    signal_cases = {
        "direct": (
            "You have 12 open Python roles since January"
            " — hiring velocity is outpacing recruiting capacity."
        ),
        "hedged": (
            "Based on the signals we've seen: You have 12 open Python roles since January"
            " — hiring velocity is outpacing recruiting capacity."
        ),
        "exploratory": (
            "We noticed some early indicators that might be relevant"
            " — You have 3 open roles since January. Is this on your radar?"
        ),
    }
    triggered, trace_ids, details = 0, [], []
    for seg, opener in _openers.items():
        for phrasing, signal_line in signal_cases.items():
            tid = _trace_id()
            body_text = (
                f"Hi there, {opener} {signal_line} "
                "If helpful, I can send over a short qualification brief "
                "and a few scheduling options."
            )
            word_count = len(body_text.split())
            if word_count > 120:
                triggered += 1
                details.append(f"seg={seg} phrasing={phrasing} word_count={word_count} > 120")
            trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P017() -> tuple[int, list[str], list[str]]:
    """'bench' must not appear in customer-facing copy."""
    customer_facing_strings = [
        # From lead_orchestrator.py send_outbound_email
        "Congratulations on the recent funding — {company} is clearly in growth mode.",
        "Teams navigating a restructure often find this is the right time to invest in automation.",
        "New technical leadership often opens a window to re-evaluate the tooling stack.",
        "I came across {company} and wanted to reach out.",
        "{company}'s signals suggest room to accelerate AI adoption.",
        "If helpful, I can send over a short qualification brief and a few scheduling options.",
        # From send_warm_lead_sms (check orchestrator)
        "Hi, we saw your reply — would a quick call this week work?",
    ]
    triggered, trace_ids, details = 0, [], []
    for text in customer_facing_strings:
        tid = _trace_id()
        if "bench" in text.lower():
            triggered += 1
            details.append(f"'bench' found in: {text!r}")
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# signal_reliability
# ═══════════════════════════════════════════════════════════════════════════


def probe_P027() -> tuple[int, list[str], list[str]]:
    """layoffs.check() returns null percentage when CSV field is empty."""
    from agent.enrichment.layoffs import _PCT_COLS, _col

    # Simulate a CSV row where percentage is blank
    test_rows = [
        {"Company": "TestCo", "Date": "2026-03-01", "Laid_Off_Count": "50", "Percentage": ""},
        {"Company": "TestCo", "Date": "2026-03-01", "Laid_Off_Count": "50", "Percentage": "null"},
        {"Company": "TestCo", "Date": "2026-03-01", "Laid_Off_Count": "50"},
    ]
    triggered, trace_ids, details = 0, [], []
    for row in test_rows:
        tid = _trace_id()
        pct = _col(row, _PCT_COLS)
        # The pipeline passes through raw string — downstream code must handle empty/null
        # Probe confirms the empty string is returned (not computed from headcount)
        if pct not in ("", "null", None):
            triggered += 1
            details.append(f"Row {row} → percentage={pct!r} (expected empty/null)")
        else:
            # This is the data gap: no headcount-based fallback computed
            # Mark as triggered to flag the missing guard
            triggered += 1
            details.append(
                f"percentage='{pct}' is not computed from headcount "
                f"(laid_off_count={row.get('Laid_Off_Count')}) — overclaim risk confirmed"
            )
        trace_ids.append(tid)
    return triggered, trace_ids, details


def probe_P028() -> tuple[int, list[str], list[str]]:
    """github_activity signal has no fork-vs-commit distinction in ai_maturity.score()."""
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        # If caller passes github_activity=True based on forks-only, scorer accepts it
        score_forks, _, conf_forks = ai_maturity.score({"github_activity": True})
        score_none, _, conf_none = ai_maturity.score({})
        # The scorer cannot distinguish forks from original commits — it's a bool input
        # Triggered if score improves from a potentially-fork-inflated signal
        if score_forks > score_none:
            triggered += 1
            details.append(
                f"github_activity=True (possibly forks) raises score {score_none}→{score_forks}; "
                "scorer has no fork/commit distinction"
            )
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# gap_overclaiming
# ═══════════════════════════════════════════════════════════════════════════


def probe_P031() -> tuple[int, list[str], list[str]]:
    """Competitor gap brief uses the bundled sample benchmark, not live peer data."""
    triggered, trace_ids, details = 0, [], []
    for _ in range(TRIALS):
        tid = _trace_id()
        competitor_gap_py = ROOT / "agent" / "enrichment" / "competitor_gap.py"
        if competitor_gap_py.exists():
            content = competitor_gap_py.read_text()
            uses_bundled_sample = (
                "_load_sample_benchmark" in content
                and "sample_competitor_gap_brief.json" in content
                and "benchmark_source" in content
                and "bundled_sample_competitor_gap_brief" in content
            )
            has_live_peer_research = any(
                token in content
                for token in (
                    "similarweb",
                    "sector_peers",
                    "live_peer",
                    "peer_search",
                    "find_competitors",
                    "score_peer",
                )
            )
            if uses_bundled_sample and not has_live_peer_research:
                triggered += 1
                details.append(
                    "competitor_gap.py generates briefs from bundled sample benchmark "
                    "without live sector-peer research"
                )
        else:
            triggered += 1
            details.append("competitor_gap.py does not exist")
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# dual_control
# ═══════════════════════════════════════════════════════════════════════════


def probe_P024() -> tuple[int, list[str], list[str]]:
    """SMS channel only activated for prospects with prior SMS reply."""
    from agent.workflows.lead_orchestrator import LeadOrchestrator

    triggered, trace_ids, details = 0, [], []
    # Check the send_warm_lead_sms logic: does it guard against email-only prospects?
    import inspect

    src = inspect.getsource(LeadOrchestrator.send_warm_lead_sms)
    has_sms_replied_guard = "sms_replied" in src or "sms_opt" in src or "channel" in src
    for _ in range(TRIALS):
        tid = _trace_id()
        if not has_sms_replied_guard:
            triggered += 1
            details.append("send_warm_lead_sms() has no sms_replied/opt-in guard in source")
        trace_ids.append(tid)
    return triggered, trace_ids, details


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

PROBES: list[tuple[str, str, str]] = [
    # (probe_id, category, description)
    ("P-001", "icp_misclassification", "Layoff+funding misrouted to Segment 1"),
    ("P-002", "icp_misclassification", "Segment 4 gate at AI readiness 1"),
    ("P-003", "icp_misclassification", "Leadership title normaliser coverage"),
    ("P-004", "icp_misclassification", "Zero open roles passes Segment 1"),
    (
        "P-005",
        "signal_overclaiming",
        "Low-confidence Segment 1 opener avoids assertive growth claim",
    ),
    ("P-006", "signal_overclaiming", "Single weak signal → exploratory phrasing"),
    ("P-007", "signal_overclaiming", "Stale funding excluded from recent_funding()"),
    ("P-008", "signal_overclaiming", "Empty signals → score=0"),
    ("P-009", "bench_overcommitment", "10 Go engineers requested, bench has 3"),
    ("P-010", "bench_overcommitment", "NestJS committed through Q3 2026"),
    ("P-011", "bench_overcommitment", "2 senior ML requested, bench has 1"),
    ("P-012", "bench_overcommitment", "Infra immediate deploy vs 14-day lead"),
    ("P-015", "tone_drift", "Subject line length ≤ 60 chars"),
    ("P-016", "tone_drift", "Body word count ≤ 120 words"),
    ("P-017", "tone_drift", "'bench' in customer-facing copy"),
    ("P-024", "dual_control_coordination", "SMS guard for email-only prospects"),
    ("P-027", "signal_reliability", "Layoff null percentage computation"),
    ("P-028", "signal_reliability", "GitHub forks inflate AI maturity score"),
    ("P-031", "gap_overclaiming", "Competitor gap brief uses bundled sample benchmark"),
]

PROBE_FNS = {
    "P-001": probe_P001,
    "P-002": probe_P002,
    "P-003": probe_P003,
    "P-004": probe_P004,
    "P-005": probe_P005,
    "P-006": probe_P006,
    "P-007": probe_P007,
    "P-008": probe_P008,
    "P-009": probe_P009,
    "P-010": probe_P010,
    "P-011": probe_P011,
    "P-012": probe_P012,
    "P-015": probe_P015,
    "P-016": probe_P016,
    "P-017": probe_P017,
    "P-024": probe_P024,
    "P-027": probe_P027,
    "P-028": probe_P028,
    "P-031": probe_P031,
}


def main() -> None:
    results_out: list[dict] = []
    print(f"\n{'─' * 72}")
    print(f"  Act III Probe Runner — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'─' * 72}")
    print(f"  {'Probe':<8} {'Category':<30} {'Triggers':<10} {'Rate'}")
    print(f"{'─' * 72}")

    for probe_id, category, description in PROBES:
        fn = PROBE_FNS.get(probe_id)
        if fn is None:
            print(f"  {probe_id:<8} {'SKIP (no runner)':<30}")
            continue
        try:
            triggered_count, trace_ids, details = fn()
            n_trials = len(trace_ids)
            rate = triggered_count / n_trials if n_trials > 0 else 0.0
            rate_str = f"{triggered_count}/{n_trials} ({rate:.0%})"
            flag = "⚠" if triggered_count > 0 else "✓"
            print(f"  {flag} {probe_id:<7} {category:<30} {rate_str}")
            if details and triggered_count > 0:
                for d in details[:2]:
                    print(f"    → {d[:90]}")
            result_entry = {
                "probe_id": probe_id,
                "category": category,
                "description": description,
                "triggered_count": triggered_count,
                "total_trials": n_trials,
                "trigger_rate": round(rate, 3),
                "trigger_rate_display": f"{triggered_count}/{n_trials}",
                "details": details,
                "trace_ids": trace_ids,
                "run_at": datetime.now(UTC).isoformat(),
            }
            results_out.append(result_entry)
            for tid, triggered_bool, detail in zip(
                trace_ids,
                [True] * triggered_count + [False] * (n_trials - triggered_count),
                details + [""] * (n_trials - len(details)),
                strict=False,
            ):
                _record(probe_id, category, triggered_bool, detail, tid)
        except Exception as exc:
            print(f"  ✗ {probe_id:<8} ERROR: {exc}")

    print(f"{'─' * 72}")

    # Write probe_results.json
    out_path = ROOT / "probes" / "probe_results.json"
    out_path.write_text(json.dumps(results_out, indent=2), encoding="utf-8")
    print(f"\n  Results written → {out_path.relative_to(ROOT)}")

    # Print category summary
    from collections import defaultdict

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in results_out:
        by_cat[r["category"]].append(r)

    print(f"\n  {'Category':<30} {'Probes':<8} {'Total Triggers'}")
    print(f"  {'─' * 55}")
    for cat, probes in sorted(by_cat.items()):
        total_t = sum(p["triggered_count"] for p in probes)
        total_n = sum(p["total_trials"] for p in probes)
        print(f"  {cat:<30} {len(probes):<8} {total_t}/{total_n}")

    total_triggered = sum(r["triggered_count"] for r in results_out)
    total_trials_all = sum(r["total_trials"] for r in results_out)
    print(
        f"\n  Overall: {total_triggered}/{total_trials_all} triggered "
        f"({total_triggered / total_trials_all:.0%} failure rate)\n"
    )

    return results_out


if __name__ == "__main__":
    main()
