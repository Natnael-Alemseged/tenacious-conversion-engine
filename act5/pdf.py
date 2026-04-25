from __future__ import annotations

from pathlib import Path
from typing import Any

from act5.memo_graph import claim_map, fmt_percent, fmt_usd, require_claim


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_page_stream(lines: list[str]) -> bytes:
    # Very small, deterministic PDF page stream using built-in Helvetica.
    # This is intentionally minimal to avoid external deps.
    y = 760
    ops: list[str] = ["BT", "/F1 12 Tf"]
    for line in lines:
        safe = _escape_pdf_text(line)[:160]
        ops.append(f"72 {y} Td ({safe}) Tj")
        y -= 16
    ops.append("ET")
    return ("\n".join(ops) + "\n").encode("utf-8")


def render_memo_pdf(*, evidence: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    claims = claim_map(evidence)
    is_draft = bool(evidence.get("draft", True))
    title_suffix = " (DRAFT)" if is_draft else ""

    sealed = require_claim(claims, "tau2_sealed_pass_at_1")["value"]
    day1 = require_claim(claims, "day1_sealed_baseline_pass_at_1")["value"]
    auto = require_claim(claims, "tau2_auto_opt_sealed_pass_at_1")["value"]
    published_ref = require_claim(claims, "tau2_published_reference_pass_at_1")["value"]
    task_dur = require_claim(claims, "tau2_task_duration_p50_seconds")["value"]

    total_cost = float(require_claim(claims, "total_cost_usd")["value"])
    cpl_value = require_claim(claims, "cost_per_qualified_lead")["value"]
    cpl = float(cpl_value) if isinstance(cpl_value, (int, float)) else None

    stalled = require_claim(claims, "stalled_thread_rate")["value"]
    manual_stalled = require_claim(claims, "tenacious_manual_stalled_thread_baseline")["value"]

    cg = require_claim(claims, "competitive_gap_reply_rate")["value"]
    gen = require_claim(claims, "generic_reply_rate")["value"]
    cg_delta = float(require_claim(claims, "competitive_gap_reply_rate_delta")["value"])
    top_quartile = require_claim(claims, "top_quartile_signal_grounded_reply_rate_range")["value"]

    rev_1 = require_claim(claims, "annualized_revenue_impact_one_segment")["value"]
    rev_2 = require_claim(claims, "annualized_revenue_impact_two_segments")["value"]
    rev_4 = require_claim(claims, "annualized_revenue_impact_all_four_segments")["value"]

    pilot = require_claim(claims, "pilot_recommendation")["value"]

    def _fmt_ci(v: dict[str, Any]) -> str:
        mean = float(v["mean"])
        lo, hi = v["ci_95"]
        return f"{mean:.3f} (95% CI [{float(lo):.3f}, {float(hi):.3f}], n={int(v['n'])})"

    def _fmt_rate_value(value_obj: dict[str, Any]) -> str:
        rr = float(value_obj["reply_rate"])
        return f"{fmt_percent(rr)} ({int(value_obj['replied_n'])}/{int(value_obj['outbound_n'])})"

    def _fmt_range_percent(r: dict[str, Any]) -> str:
        lo, hi = r["range"]
        return f"{fmt_percent(float(lo))}–{fmt_percent(float(hi))}"

    def _fmt_revenue_claim(v: dict[str, Any]) -> list[str]:
        comp = v["computed"]
        deals_lo, deals_hi = comp["closed_deals_per_year_range"]
        rev_lo, rev_hi = comp["annual_revenue_range_usd"]
        calls_wk = v["assumptions"]["discovery_calls_per_week"]
        segs = ", ".join(v["segments_included"])
        header = (
            f"- {segs}: assume {calls_wk} discovery calls/week → "
            f"{deals_lo:.1f}–{deals_hi:.1f} closes/yr"
        )
        impact = (
            f"  Annual revenue impact: {fmt_usd(float(rev_lo))}–{fmt_usd(float(rev_hi))} (range)"
        )
        return [
            header,
            impact,
        ]

    stalled_rate = float(stalled["stalled_rate"])
    stalled_n = int(stalled["stalled_n"])
    inbound_n = int(stalled["inbound_n"])
    manual_lo, manual_hi = manual_stalled["range"]

    page1: list[str] = [
        f"Tenacious Conversion Engine — Act V Memo{title_suffix}",
        "Page 1/2 — The Decision",
        "",
        "Executive summary (3 sentences):",
        (
            "We built a conversion engine that generates signal-grounded outbound and measures "
            "reply, stalled-thread, and cost-per-qualified-lead from traces."
        ),
        (
            f"On τ²-Bench retail (sealed), the method scores {_fmt_ci(sealed)} vs Day-1 baseline "
            f"{_fmt_ci(day1)}; auto-opt baseline = {float(auto):.3f}."
        ),
        (
            "Recommendation: run a 30-day Segment 2 pilot with a hard kill-switch on wrong-signal "
            "rate, and treat competitive-gap reply deltas as synthetic until validated on real "
            "prospects."
        ),
        "",
        "1) τ²-Bench baseline performance (sealed, 95% CIs):",
        f"- Method pass@1: {_fmt_ci(sealed)}",
        f"- Day-1 baseline pass@1: {_fmt_ci(day1)}",
        f"- Auto-opt baseline pass@1: {float(auto):.3f}",
        f"- Published reference (point): {float(published_ref):.2f}",
        (
            f"- τ² task duration: p50={task_dur['p50_s']}s, p95={task_dur['p95_s']}s "
            "(simulator runtime; not email response latency)"
        ),
        "",
        "2) Cost per qualified lead (CPL):",
        f"- Total measured cost (Act V rollup): {fmt_usd(total_cost)}",
        f"- CPL (qualified = booking_created): {fmt_usd(cpl) if cpl is not None else 'n/a'}",
        "",
        "3) Stalled-thread rate delta:",
        (
            f"- Measured stalled-thread rate: {fmt_percent(stalled_rate)} "
            f"({stalled_n}/{inbound_n} non-booking)"
        ),
        (
            f"- Tenacious manual baseline (given): {fmt_percent(float(manual_lo))}"
            f"–{fmt_percent(float(manual_hi))}"
        ),
        (
            "Context: this measurement uses booking_created as a proxy gate. A high stalled rate "
            "here can reflect synthetic volume / calibration mismatch or an overly-strict booking "
            "proxy, not a claim of worse ops."
        ),
        "",
        "4) Competitive-gap outbound performance (synthetic evaluation):",
        f"- Competitive-gap reply rate: {_fmt_rate_value(cg)}",
        f"- Generic reply rate: {_fmt_rate_value(gen)}",
        f"- Reply-rate delta (cg − generic): {fmt_percent(cg_delta)}",
        (
            "- Top-quartile real-world signal-grounded range (benchmark): "
            f"{_fmt_range_percent(top_quartile)}"
        ),
        (
            "Note: 100% reply rates are a synthetic-data artifact in this run; treat as "
            "directional signal only until validated on live outbound."
        ),
        "",
        "5) Annualized dollar impact (segment-based revenue model):",
        *_fmt_revenue_claim(rev_1),
        *_fmt_revenue_claim(rev_2),
        *_fmt_revenue_claim(rev_4),
        "",
        "6) Pilot scope recommendation (30 days):",
        f"- Segment: {pilot['segment']}",
        (
            f"- Lead volume: assume {pilot['discovery_calls_per_week_assumption']} "
            "discovery calls/week booked"
        ),
        f"- Weekly budget cap: {fmt_usd(float(pilot['weekly_budget_usd']))} (assumption)",
        f"- Success criterion: {pilot['success_criterion']}",
    ]

    page2: list[str] = [
        f"Tenacious Conversion Engine — Act V Memo{title_suffix}",
        "Page 2/2 — The Skeptic’s Appendix",
        "",
        (
            "A) Four failure modes τ²-Bench does not capture "
            "(what / why τ² misses / what to add / cost):"
        ),
        "1) Wrong-signal outreach (signal_overclaiming):",
        "   What: agent asserts hiring/AI/funding claims from weak public signal.",
        "   Why τ² misses: τ² retail tasks do not exercise public-signal grounding for real "
        "companies.",
        "   Add: enforce confidence-tier phrasing + abstention when confidence < 0.6; "
        "add probe gates.",
        "   Cost: lower throughput; requires more enrichment checks per prospect.",
        "2) Tone/brand offense (offshore language triggers):",
        "   What: phrasing that reads like low-quality outsourcing spam.",
        "   Why τ² misses: retail benchmark has no brand sensitivity or founder persona risk.",
        "   Add: style-guide rubric + red-flag phrase filters + human review for first 50 sends.",
        "   Cost: review time; false positives can reduce volume.",
        "3) Booking proxy mismatch (booking_created ≠ qualified):",
        "   What: system can get replies but fail the booking proxy due to tooling mismatch.",
        "   Why τ² misses: τ² tasks are closed-form; no real calendar / sales workflow variance.",
        "   Add: align qualification to Tenacious CRM stages; instrument post-reply handoff.",
        "   Cost: HubSpot stage mapping + ops time.",
        "4) Competitive-gap benchmark mismatch:",
        "   What: “top-quartile practice” may be irrelevant or strategically wrong for a prospect.",
        "   Why τ² misses: benchmark is not conditioned on sub-niche strategy constraints.",
        "   Add: ask a calibration question before prescribing; allow ‘deliberate choice’ "
        "escape hatch.",
        "   Cost: longer emails; slightly lower reply rates expected.",
        "",
        "B) Public-signal lossiness (false negatives / false positives):",
        (
            "False negative: quietly sophisticated but silent company → scorer underestimates "
            "readiness → overly basic pitch → lost deal."
        ),
        (
            "False positive: loud but shallow company → scorer overestimates readiness "
            "→ over-technical pitch → brand damage + lower replies."
        ),
        "",
        "C) Gap-analysis risks (when top-quartile is a bad benchmark):",
        (
            "Risk 1: deliberate strategy (e.g., regulated workflow where ‘move fast’ practices are "
            "harmful) → wrong recommendation harms trust."
        ),
        (
            "Risk 2: sub-niche irrelevance (capability gap is not binding constraint) "
            "→ prospect ignores message and categorizes as spam."
        ),
        "",
        "D) Brand-reputation comparison (unit economics):",
        ("Assume 1,000 emails sent; if 5% contain a wrong signal, that's 50 wrong-signal emails."),
        (
            "If each wrong-signal email has an expected reputation cost of $10k in pipeline "
            "suppression, "
            "expected brand cost = $500k."
        ),
        "Compare to expected reply-rate lift in the 7–12% range (vs 1–3% baseline).",
        "",
        "E) One honest unresolved probe (business impact if deployed anyway):",
        "Probe: signal_overclaiming (P-005): assertive Segment 1 opener regardless of confidence "
        "(measured trigger rate 9/9).",
        "Impact: undermines the core ‘grounded research’ value prop; can revert reply rates to "
        "baseline and create viral brand risk.",
        "",
        "F) Kill switch clause (metric / threshold / rollback condition):",
        "Metric: wrong-signal rate on manually audited sample of first 100 sends.",
        (
            "Threshold: pause if wrong-signal rate ≥ 5% or any single high-severity false claim "
            "triggers an executive complaint."
        ),
        (
            "Rollback: revert to generic pitch template + require human approval for "
            "signal-grounded "
            "claims until fixed."
        ),
    ]

    stream1 = _pdf_page_stream(page1)
    stream2 = _pdf_page_stream(page2)

    # Build a minimal 2-page PDF.
    # Objects: catalog, pages, page1, page2, font, content1, content2
    objects: list[bytes] = []

    def obj(data: str | bytes) -> int:
        if isinstance(data, str):
            data_b = data.encode("utf-8")
        else:
            data_b = data
        objects.append(data_b)
        return len(objects)

    font_id = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content1_id = obj(b"<< /Length %d >>\nstream\n" % len(stream1) + stream1 + b"endstream")
    content2_id = obj(b"<< /Length %d >>\nstream\n" % len(stream2) + stream2 + b"endstream")

    page1_id = obj(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
        f"/Contents {content1_id} 0 R >>"
    )
    page2_id = obj(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
        f"/Contents {content2_id} 0 R >>"
    )
    pages_id = obj(f"<< /Type /Pages /Kids [{page1_id} 0 R {page2_id} 0 R] /Count 2 >>")
    catalog_id = obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    # Write xref
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = [0]
    body = bytearray()
    body.extend(header)
    for i, data in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{i} 0 obj\n".encode())
        body.extend(data)
        body.extend(b"\nendobj\n")
    xref_start = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        body.extend(f"{off:010d} 00000 n \n".encode())
    body.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode()
    )
    out_path.write_bytes(bytes(body))
