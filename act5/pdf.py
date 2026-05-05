from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from act5.memo_graph import claim_map, fmt_percent, fmt_usd, require_claim

# (kind, text) — kind in: title | h2 | body | note | blank | rule
RenderItem = tuple[str, str]

_BODY_WRAP = 105  # chars at 8.5pt Helvetica on 504pt column
_NOTE_WRAP = 118  # chars at 7.5pt


def _escape(text: str) -> str:
    return (
        text.replace("τ", "tau")
        .replace("²", "2")
        .replace("'", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("—", "-")
        .replace("–", "-")
        .replace("→", "->")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("≈", "~")
        .replace("±", "+/-")
        .replace("×", "x")
        .replace("Δ", "Delta")
        .replace("α", "alpha")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width) or [""]


def _build_stream(items: list[RenderItem]) -> bytes:
    """Render a page as a minimal PDF content stream.

    Uses two fonts from /Resources: F1=Helvetica, F2=Helvetica-Bold.
    Graphics (rules) are emitted outside BT/ET blocks.
    """
    MARGIN_L = 54
    MARGIN_R = 54
    PAGE_W = 612
    y = 752.0
    parts: list[str] = []

    def text_op(font: str, size: float, x: float, ypos: float, text: str) -> str:
        return f"BT /{font} {size} Tf 1 0 0 1 {x:.1f} {ypos:.1f} Tm ({_escape(text)}) Tj ET"

    for kind, payload in items:
        if kind == "blank":
            y -= 6
        elif kind == "rule":
            parts.append(f"q 0.35 w {MARGIN_L} {y + 2:.1f} m {PAGE_W - MARGIN_R} {y + 2:.1f} l S Q")
            y -= 9
        elif kind == "title":
            parts.append(text_op("F2", 12, MARGIN_L, y, payload))
            y -= 20
        elif kind == "h2":
            parts.append(text_op("F2", 8.5, MARGIN_L, y, payload))
            y -= 13
        elif kind == "body":
            for i, line in enumerate(_wrap(payload, _BODY_WRAP)):
                indent = 10.0 if i > 0 and payload.startswith("- ") else 0.0
                parts.append(text_op("F1", 8.5, MARGIN_L + indent, y, line))
                y -= 12
        elif kind == "note":
            for line in _wrap(payload, _NOTE_WRAP):
                parts.append(text_op("F1", 7.5, MARGIN_L + 6, y, line))
                y -= 11

    return ("\n".join(parts) + "\n").encode("utf-8")


def render_memo_pdf(*, evidence: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    claims = claim_map(evidence)
    is_draft = bool(evidence.get("draft", True))
    draft_tag = " [DRAFT]" if is_draft else ""

    # ── pull claims ──────────────────────────────────────────────────────────
    sealed = require_claim(claims, "tau2_sealed_pass_at_1")["value"]
    day1 = require_claim(claims, "day1_sealed_baseline_pass_at_1")["value"]
    auto = require_claim(claims, "tau2_auto_opt_sealed_pass_at_1")["value"]
    published_ref = require_claim(claims, "tau2_published_reference_pass_at_1")["value"]
    task_dur = require_claim(claims, "tau2_task_duration_p50_seconds")["value"]
    delta_a = require_claim(claims, "delta_a")["value"]
    delta_a_value = float(delta_a["delta_a"])

    if "delta_a_fisher_exact_one_sided" in claims:
        da_test = require_claim(claims, "delta_a_fisher_exact_one_sided")["value"]
        sig_line = (
            f"- Delta A significance (Fisher one-sided): p={float(da_test['p_value']):.3f} "
            f"(sig<0.05? {bool(da_test['significant_at_p_lt_0_05'])})."
        )
    else:
        status = require_claim(claims, "delta_a_significance_status")["value"]
        m_n = int(status["method_total_n"])
        b_n = int(status["baseline_total_n"])
        req_n = int(status["minimum_n_required"])
        sig_line = (
            f"- Insufficient sample for significance. Preliminary Delta A={delta_a_value:+.3f} "
            f"(method n={m_n}, baseline n={b_n}; min required={req_n})."
        )

    total_cost = float(require_claim(claims, "total_cost_usd")["value"])
    cost_inputs = require_claim(claims, "cost_inputs_breakdown")["value"]
    cpl_claim = require_claim(claims, "cost_per_qualified_lead")["value"]
    cpl = (
        float(cpl_claim["cpl_usd"])
        if isinstance(cpl_claim, dict) and cpl_claim.get("cpl_usd")
        else None
    )
    qualified_n = int(cpl_claim["denominator_qualified_n"]) if isinstance(cpl_claim, dict) else 0
    booked_n = qualified_n

    stalled = require_claim(claims, "stalled_thread_rate")["value"]
    manual_stalled = require_claim(claims, "tenacious_manual_stalled_thread_baseline")["value"]
    stalled_rate = float(stalled["stalled_rate"])
    stalled_n = int(stalled["stalled_n"])
    inbound_n = int(stalled["inbound_n"])
    manual_lo, manual_hi = manual_stalled["range"]

    cg = require_claim(claims, "competitive_gap_reply_rate")["value"]
    gen = require_claim(claims, "generic_reply_rate")["value"]
    cg_delta = float(require_claim(claims, "competitive_gap_reply_rate_delta")["value"])
    top_q = require_claim(claims, "top_quartile_signal_grounded_reply_rate_range")["value"]

    rev_1 = require_claim(claims, "annualized_revenue_impact_one_segment")["value"]
    rev_2 = require_claim(claims, "annualized_revenue_impact_two_segments")["value"]
    rev_4 = require_claim(claims, "annualized_revenue_impact_all_four_segments")["value"]
    pilot = require_claim(claims, "pilot_recommendation")["value"]

    method_mean = float(sealed["mean"])
    baseline_mean = float(day1["mean"])

    # ── helpers ──────────────────────────────────────────────────────────────
    def _usd(x: float) -> str:
        return f"${x:,.2f}" if abs(x) < 100 else fmt_usd(x)

    def _rate(v: dict[str, Any]) -> str:
        pct = fmt_percent(float(v["reply_rate"]))
        return f"{pct} ({int(v['replied_n'])}/{int(v['outbound_n'])})"

    def _rev_line(v: dict[str, Any]) -> str:
        comp = v["computed"]
        lo, hi = comp["annual_revenue_range_usd"]
        segs = ", ".join(v["segments_included"])
        calls = v["assumptions"]["discovery_calls_per_week"]
        return f"- {segs}: {calls} calls/wk -> {fmt_usd(float(lo))}-{fmt_usd(float(hi))}/yr"

    # CPL vs target (baseline_numbers.md: target <= $5, penalty >= $8)
    CPL_TARGET = 5.0
    CPL_PENALTY = 8.0
    if cpl is not None:
        if cpl <= CPL_TARGET:
            cpl_vs_target = f"{_usd(cpl)} — within target (<= $5.00)"
        elif cpl <= CPL_PENALTY:
            cpl_vs_target = f"{_usd(cpl)} — above $5 target; below $8 penalty threshold"
        else:
            cpl_vs_target = f"{_usd(cpl)} — above $8 penalty threshold"
    else:
        cpl_vs_target = "n/a (no qualified leads recorded)"

    rig_cat = cost_inputs["categories"]["rig_usage"]
    api_cat = cost_inputs["categories"]["other_apis"]
    llm_amt = _usd(float(cost_inputs["categories"]["llm_upstream_inference"]["amount_usd"]))
    rig_amt = (
        _usd(float(rig_cat["amount_usd"]))
        if rig_cat.get("metered") and rig_cat.get("amount_usd") is not None
        else "unmetered"
    )
    api_amt = (
        _usd(float(api_cat["amount_usd"]))
        if api_cat.get("metered") and api_cat.get("amount_usd") is not None
        else "unmetered"
    )

    top_lo, top_hi = top_q["range"]

    # ── PAGE 1 ───────────────────────────────────────────────────────────────
    B: list[RenderItem] = []

    def t(text: str) -> None:
        B.append(("title", text))

    def h(text: str) -> None:
        B.append(("h2", text))

    def b(text: str) -> None:
        B.append(("body", text))

    def n(text: str) -> None:
        B.append(("note", text))

    def sp() -> None:
        B.append(("blank", ""))

    def rule() -> None:
        B.append(("rule", ""))

    t(f"Tenacious Conversion Engine — Act V Decision Memo{draft_tag}")
    b("Page 1 of 2")
    rule()

    h("Executive Summary")
    b("Build: signal-grounded outbound pipeline; measure reply rate, stalled-thread rate, and CPL.")
    b(
        f"Result: tau2 pass@1 {method_mean:.3f} vs baseline {baseline_mean:.3f}"
        f" (Delta A={delta_a_value:+.3f})."
    )
    b(
        f"Recommendation: 30-day Segment 2 pilot, {int(pilot['lead_volume_per_week'])} leads/week, "
        f"{_usd(float(pilot['weekly_budget_usd']))}/week cap, kill-switch at >= 5% wrong-signal."
    )
    rule()

    h("1) Benchmark Performance")
    b(
        f"- Method vs baseline (sealed tau2): {method_mean:.3f} vs {baseline_mean:.3f}"
        f" (Delta A={delta_a_value:+.3f})."
    )
    b(sig_line)
    m_lo, m_hi = sealed["ci_95"]
    b_lo, b_hi = day1["ci_95"]
    b(f"- 95% CIs: method [{m_lo:.3f}, {m_hi:.3f}]; baseline [{b_lo:.3f}, {b_hi:.3f}].")
    b(f"- Auto-opt baseline: {float(auto):.3f}. Published reference: {float(published_ref):.2f}.")
    b(f"- tau2 runtime (not email latency): p50={task_dur['p50_s']}s, p95={task_dur['p95_s']}s.")
    sp()

    h("2) Cost per Qualified Lead (CPL)")
    b("- Qualified lead: booking_created == true (non-autoresponder inbound replies).")
    b(f"- Cost inputs: LLM={llm_amt}; rig={rig_amt}; APIs={api_amt}. Total={_usd(total_cost)}.")
    b(f"- Denominator: {qualified_n} qualified leads (booked={booked_n}).")
    b(f"- Derived CPL: {_usd(total_cost)} / {qualified_n} = {cpl_vs_target}.")
    b("- Target envelope (Tenacious internal, baseline_numbers.md): <= $5.00; penalty >= $8.00.")
    n(
        "Caching note: LLM routes via OpenRouter -> qwen/qwen3-235b-a22b; prefix caching "
        "unverified for this route — LLM cost is an upper bound. Reduction options: shorter "
        "prompts, smaller model, deterministic rules for simple classifications."
    )
    sp()

    h("3) Stalled-Thread Rate")
    b("- Definition: stalled = booking_created is false (14-day no-booking proxy).")
    sr = fmt_percent(stalled_rate)
    b(f"- Measured: {sr} ({stalled_n}/{inbound_n} non-booking; booked={booked_n}).")
    ml = fmt_percent(float(manual_lo))
    mh = fmt_percent(float(manual_hi))
    b(f"- Tenacious manual baseline (given): {ml}-{mh}.")
    n("Caveat: synthetic traces + booking proxy; production calibration required.")
    sp()

    h("4) Reply-Rate Delta (signal-grounded vs generic)")
    b(f"- Competitive-gap variant: {_rate(cg)}")
    b(f"- Generic variant: {_rate(gen)}")
    tq_lo = fmt_percent(float(top_lo))
    tq_hi = fmt_percent(float(top_hi))
    b(
        f"- Delta (cg - generic): {fmt_percent(cg_delta)} pp."
        f" Top-quartile benchmark: {tq_lo}-{tq_hi}."
    )
    n("Caveat: 100% reply rates are a synthetic artifact; treat delta as directional only.")
    sp()

    h("5) Annualized Revenue Impact")
    b(_rev_line(rev_1))
    b(_rev_line(rev_2))
    b(_rev_line(rev_4))
    sp()

    h("6) Pilot Recommendation (30 days)")
    b(f"- Segment: {pilot['segment']}. Justification: cost-pressure buyers; fastest CFO sign-off.")
    vol = int(pilot["lead_volume_per_week"])
    cap = _usd(float(pilot["weekly_budget_usd"]))
    b(f"- Volume: {vol} leads/week. Budget cap: {cap}/week.")
    b(f"- Success criterion: {pilot['success_criterion']}")

    page1_items = list(B)

    # ── PAGE 2 ───────────────────────────────────────────────────────────────
    B.clear()

    t(f"Tenacious Conversion Engine — Act V Decision Memo{draft_tag}")
    b("Page 2 of 2 — Skeptic's Appendix")
    rule()

    h("A) Four Failure Modes tau2 Does Not Capture")
    b("1) Wrong-signal outreach: weak signal -> confident claim -> brand + reply-rate collapse.")
    n("   Fix: confidence-tier phrasing + abstain threshold. Cost: more checks, lower volume.")
    b("2) Tone offense: offshore/spam language triggers hiring managers.")
    n("   Fix: style rubric + pre-send review.")
    b("3) Proxy mismatch: booking_created != qualified in Tenacious CRM.")
    n("   Fix: explicit stage mapping before pilot launch.")
    b("4) Bad benchmark fit: top-quartile practice wrong for specific sub-niche.")
    n("   Fix: calibrate benchmark to niche before prescribing gap.")
    sp()

    h("B) Public-Signal Lossiness")
    b("- False negative: silent company -> underestimated readiness -> weak pitch -> lost deal.")
    b("- False positive: loud company -> overestimated readiness -> technical pitch -> brand hit.")
    b("- FN agent shape: pitches generic, misses Segment 4 gap -> wasted touch + lower replies.")
    b("- FP agent shape: pitches advanced gap to low-readiness prospect -> credibility + spam hit.")
    sp()

    h("C) Gap-Analysis Risks (when top-quartile is a bad benchmark)")
    b("- Risk 1: deliberate strategy (e.g. regulated workflow) -> move-fast rec harms trust.")
    b("- Risk 2: sub-niche irrelevance (gap not the binding constraint) -> message flagged spam.")
    sp()

    h("D) Brand-Reputation Unit Economics")
    b("- Assume 1,000 sends; 5% wrong-signal rate = 50 wrong-signal emails.")
    b("- Expected brand cost at $10k pipeline suppression/wrong-signal email = $500k.")
    b("- Compare to reply-rate lift: 7-12% (signal-grounded) vs 1-3% (generic baseline).")
    sp()

    h("E) Unresolved Probe — signal_overclaiming (P-005)")
    b("- Trigger rate: 9/9 in probe suite. Impact: undermines 'grounded research' value prop.")
    b("- If deployed at scale: can revert reply rates to baseline + create viral brand risk.")
    b("- Unit economics: 5% wrong-signal on 1,000 sends -> ~$500k expected brand cost (see D).")
    sp()

    h("F) Kill-Switch Clause")
    b("- Metric: wrong-signal rate on manually audited first 100 sends.")
    b("- Threshold: pause if wrong-signal >= 5% OR any high-severity exec complaint received.")
    b("- Rollback: revert to generic template + require human approval for signal-grounded claims.")

    page2_items = list(B)

    # ── BUILD PDF ────────────────────────────────────────────────────────────
    stream1 = _build_stream(page1_items)
    stream2 = _build_stream(page2_items)

    objects: list[bytes] = []

    def obj(data: str | bytes) -> int:
        objects.append(data.encode() if isinstance(data, str) else data)
        return len(objects)

    font1_id = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font2_id = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    content1_id = obj(b"<< /Length %d >>\nstream\n" % len(stream1) + stream1 + b"endstream")
    content2_id = obj(b"<< /Length %d >>\nstream\n" % len(stream2) + stream2 + b"endstream")

    resources = f"<< /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >>"
    page1_id = obj(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources {resources} /Contents {content1_id} 0 R >>"
    )
    page2_id = obj(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources {resources} /Contents {content2_id} 0 R >>"
    )
    pages_id = obj(f"<< /Type /Pages /Kids [{page1_id} 0 R {page2_id} 0 R] /Count 2 >>")
    catalog_id = obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = [0]
    body = bytearray(header)
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
