from __future__ import annotations

from typing import Any

from agent.enrichment.public_briefs import _segment_name
from agent.enrichment.schemas import HiringSignalBrief, tier_from_score


def _fmt_bool(value: bool, *, yes: str = "Yes", no: str = "No") -> str:
    return yes if value else no


def _funding_line(brief: HiringSignalBrief) -> str:
    funding = brief.signals.funding.data[0] if brief.signals.funding.data else {}
    if not funding:
        return "- **Funding event:** No recent public funding event detected"
    stage = str(funding.get("investment_type") or funding.get("round") or "funding").lower()
    amount = funding.get("money_raised_usd")
    date = funding.get("announced_on") or funding.get("date") or "unknown date"
    source = brief.company_domain or "Crunchbase ODM"
    amount_text = f"${amount:,}" if isinstance(amount, (int, float)) else "undisclosed amount"
    return f"- **Funding event:** {stage} {amount_text} closed {date} — {source}"


def _hiring_velocity_line(brief: HiringSignalBrief) -> str:
    jobs = brief.signals.job_posts.data
    today = int(jobs.get("open_roles") or 0)
    return (
        f"- **Hiring velocity:** {today} open roles today vs 0 sixty days ago → insufficient_signal"
    )


def _layoff_line(brief: HiringSignalBrief) -> str:
    layoff = brief.signals.layoffs.data[0] if brief.signals.layoffs.data else {}
    if not layoff:
        return "- **Layoff event:** No recent layoffs.fyi event detected"
    return (
        f"- **Layoff event:** Yes — {layoff.get('date', 'date unknown')}, "
        f"{layoff.get('laid_off_count', 'unknown')} affected"
    )


def _leadership_line(brief: HiringSignalBrief) -> str:
    change = brief.signals.leadership_change.data[0] if brief.signals.leadership_change.data else {}
    if not change:
        return "- **Leadership change:** No recent public leadership transition detected"
    return (
        f"- **Leadership change:** Yes — {change.get('title', 'leadership role')} "
        f"({change.get('started_on', 'date unknown')})"
    )


def _bench_table(brief: HiringSignalBrief) -> str:
    required = brief.signals.bench.data.required_stacks
    counts = brief.signals.bench.data.available_counts
    if not required:
        return "| Stack | Available |\n|---|---|\n| none inferred | n/a |"
    rows = ["| Stack | Available |", "|---|---|"]
    for stack in required:
        rows.append(f"| {stack} | {counts.get(stack, 0)} |")
    return "\n".join(rows)


def _gap_lines(competitor_gap_brief: dict[str, Any]) -> tuple[list[str], list[str]]:
    high_conf = []
    avoid = []
    for finding in competitor_gap_brief.get("gap_findings", []):
        peers = ", ".join(
            f"{item.get('competitor_name')}: {item.get('evidence')}"
            for item in finding.get("peer_evidence", [])[:2]
        )
        line = f"- {finding.get('practice')} — peers: {peers}"
        if finding.get("confidence") == "low":
            avoid.append(line)
        else:
            high_conf.append(line)
    if not high_conf:
        high_conf = ["- No high-confidence peer-gap findings available in the current brief."]
    if not avoid:
        avoid = ["- No explicitly low-confidence gap findings were generated."]
    return high_conf[:2], avoid[:1]


def _conversation_summary(brief: HiringSignalBrief) -> list[str]:
    jobs = brief.signals.job_posts.data
    required_stacks = ", ".join(brief.signals.bench.data.required_stacks) or "no special stacks"
    honesty = ", ".join(brief.honesty_flags) if brief.honesty_flags else "none"
    summary = [
        (
            f"Primary segment match is {_segment_name(brief)} with confidence "
            f"{brief.segment_confidence:.2f}."
        ),
        f"AI maturity currently scores {brief.signals.ai_maturity.score}/3 with "
        f"{tier_from_score(brief.signals.ai_maturity.confidence)} confidence.",
        f"Public job-post scrape shows {int(jobs.get('open_roles') or 0)} open roles and "
        f"{int(jobs.get('ai_adjacent_roles') or 0)} AI-adjacent roles.",
        (
            f"Bench match requires {required_stacks} and gate status is "
            f"{_fmt_bool(brief.signals.bench.data.bench_to_brief_gate_passed)}."
        ),
        f"Honesty flags: {honesty}.",
    ]
    return summary


def render_discovery_call_context_brief(
    brief: HiringSignalBrief,
    competitor_gap_brief: dict[str, Any],
    *,
    prospect_name: str = "",
    prospect_title: str = "",
    prospect_company: str = "",
    call_datetime_utc: str = "TBD",
    call_datetime_prospect_tz: str = "TBD",
    tenacious_lead_name: str = "TBD",
    duration_minutes: int = 30,
    thread_start_date: str = "TBD",
    original_subject: str = "",
    langfuse_trace_url: str = "",
    price_bands_quoted: str = "none",
    thread_insights: list[str] | None = None,
    objections: list[tuple[str, str, str]] | None = None,
) -> str:
    high_conf, avoid = _gap_lines(competitor_gap_brief)
    insights = (thread_insights or _conversation_summary(brief))[:5]
    default_objection = [("No explicit objection logged", "n/a", "validate scope and urgency")]
    objections = (objections or default_objection)[:2]
    company = prospect_company or brief.company_name
    name = prospect_name or "Unknown prospect"
    title = prospect_title or "Unknown title"
    uncertain = (
        ", ".join(brief.honesty_flags)
        if brief.honesty_flags
        else "no major uncertainty flags surfaced."
    )

    lines = [
        "# Discovery Call Context Brief",
        "",
        f"**Prospect:** {name} — {title} at {company}",
        f"**Scheduled:** {call_datetime_utc} ({call_datetime_prospect_tz} prospect local)",
        f"**Delivery lead assigned:** {tenacious_lead_name}",
        f"**Call length booked:** {duration_minutes} minutes",
        f'**Thread origin:** {thread_start_date} — Email subject: "{original_subject}"',
        f"**Full thread:** [Link to Langfuse trace]({langfuse_trace_url or 'https://cloud.langfuse.com'})",
        "",
        "---",
        "",
        "## 1. Segment and confidence",
        "",
        f"- **Primary segment match:** {_segment_name(brief)}",
        f"- **Confidence:** {brief.segment_confidence:.2f}",
        (
            f"- **Why this segment:** ICP segment {brief.icp_segment} with dominant "
            "public signal cluster."
        ),
        (
            f"- **Abstention risk:** {_fmt_bool(brief.segment_confidence < 0.6)}"
            + (
                " — low confidence, keep discovery broad."
                if brief.segment_confidence < 0.6
                else " — acceptable confidence for a segment-led conversation."
            )
        ),
        "",
        "## 2. Key signals (from hiring_signal_brief.json)",
        "",
        _funding_line(brief),
        _hiring_velocity_line(brief),
        _layoff_line(brief),
        _leadership_line(brief),
        f"- **AI maturity score:** {brief.signals.ai_maturity.score} / 3 "
        f"(confidence {tier_from_score(brief.signals.ai_maturity.confidence)})",
        "",
        "## 3. Competitor gap findings (from competitor_gap_brief.json)",
        "",
        "High-confidence findings the delivery lead should be ready to discuss:",
        "",
        *high_conf,
        "",
        "Findings to avoid in the call (low confidence or likely to land wrong):",
        "",
        *avoid,
        "",
        "## 4. Bench-to-brief match",
        "",
        f"- **Stacks the prospect will likely need:** "
        f"{', '.join(brief.signals.bench.data.required_stacks) or 'no special stacks inferred'}",
        "- **Available engineers per stack (from bench_summary.json):**",
        "",
        _bench_table(brief),
        "",
        f"- **Gaps:** {', '.join(brief.signals.bench.data.gaps) or 'none'}",
        (
            f"- **Honest flag:** "
            f"{_fmt_bool(not brief.signals.bench.data.bench_to_brief_gate_passed)}"
            + (
                " — route capacity mismatch to a human."
                if not brief.signals.bench.data.bench_to_brief_gate_passed
                else " — no bench mismatch detected."
            )
        ),
        "",
        "## 5. Conversation history summary",
        "",
    ]
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(insights, start=1))
    lines.extend(
        [
            "",
            "## 6. Objections already raised (and the agent's responses)",
            "",
            "| Objection | Agent response | Delivery lead should be ready to |",
            "|---|---|---|",
        ]
    )
    for objection, response, deeper in objections:
        lines.append(f"| {objection} | {response} | {deeper} |")
    lines.extend(
        [
            "",
            "## 7. Commercial signals",
            "",
            f"- **Price bands already quoted:** {price_bands_quoted}",
            "- **Has the prospect asked for a specific total contract value?** No",
            "- **Is the prospect comparing vendors?** Unknown",
            (
                "- **Urgency signals:** None captured yet from the thread context "
                "available to the generator."
            ),
            "",
            "## 8. Suggested call structure",
            "",
            (
                "- **Minutes 0–2:** Open on the specific trigger that got the "
                "meeting booked and confirm it is still the live priority."
            ),
            (
                "- **Minutes 2–10:** Validate the delivery bottleneck, timeline, "
                "and whether the signal-led hypothesis is directionally correct."
            ),
            (
                "- **Minutes 10–20:** Discuss the capability gap and the smallest "
                "credible team or phase shape that would de-risk it."
            ),
            (
                "- **Minutes 20–25:** Anchor pricing only at the public band level "
                "and route anything scoped or discounted to follow-up."
            ),
            (
                "- **Minutes 25–30:** Confirm next step: proposal, technical "
                "follow-up, or explicit no-fit."
            ),
            "",
            "## 9. What NOT to do on this call",
            "",
            "- Do not overstate competitor-gap confidence beyond what the brief can evidence.",
            (
                "- Do not commit staffing capacity or custom pricing outside the "
                "current bench and pricing sheet."
            ),
            "",
            "## 10. Agent confidence and unknowns",
            "",
            (
                "- **Things the agent is confident about:** segment match, bench "
                f"view, AI maturity score {brief.signals.ai_maturity.score}/3."
            ),
            (f"- **Things the agent is uncertain about:** {uncertain}"),
            (
                "- **Things the agent could not find:** complete thread transcript, "
                "explicit commercial asks, and verified live peer-comparison "
                "research beyond the benchmark cohort."
            ),
            (
                "- **Overall agent confidence in this brief:** "
                f"{brief.overall_confidence_weighted:.2f}"
            ),
            "",
            "---",
            "",
            (
                "*This brief was generated by the TRP1 Week 10 Conversion Engine. "
                f"Generated at {brief.generated_at}.*"
            ),
        ]
    )
    return "\n".join(lines) + "\n"
