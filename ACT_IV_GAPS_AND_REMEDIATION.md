# Act IV Gaps And Remediation Plan

This file tracks what remained after the Act IV deterministic probe ablation and what has now been closed. The original confidence-gated opener mechanism is still in the repo, but the current benchmark-facing Act IV submission is the `dual_control_v2` coordination prompt for tau2 retail. The strict benchmark artifact gaps are now addressed. Production-hardening work still remains.

## Act IV Completion Gaps

| Gap | Status | Remediation |
|---|---|---|
| Sealed held-out tau2-Bench run is missing | Addressed | Sealed held-out traces now exist and are exported at the repo root. |
| Automated optimization baseline is missing | Addressed | Auto-opt dev-search + sealed evaluation artifacts now exist under `eval/runs/auto_opt/`. |
| True held-out Delta A is missing | Addressed | Delta A is now computed from sealed held-out artifacts and recorded explicitly, including the current positive-but-not-significant result. |
| Delta B and Delta C are missing | Addressed | Delta B and Delta C are now reported in `method.md` and `ablation_results.json`. |
| p95 latency from real tasks is missing | Addressed | p95 latency is now aggregated from the sealed held-out trace exports. |
| Confidence mechanism is wired end-to-end for inbound email | Addressed | `LeadOrchestrator.handle_email()` now runs `agent.enrichment.pipeline.run()`, writes the resulting ICP/confidence fields to HubSpot, and passes `brief.icp_segment`, `brief.segment_confidence`, `brief.signals.ai_maturity.score`, and `brief.signals.bench.data.bench_to_brief_gate_passed` into the confidence-aware email reply path when outbound routing is configured. |

## Known System Gaps From Act III

| Gap | Probe | Status | Remediation |
|---|---|---|---|
| ICP priority bug: funding wins over layoffs | P-001 | Fixed | In `agent/enrichment/pipeline.py`, apply the ICP priority order: restructure/layoff before funding, then leadership, then AI maturity, then abstain. |
| Segment 1 accepts zero open roles | P-004 | Fixed | Require Segment 1 qualifying filters: fresh funding plus enough open engineering roles, or abstain/hedge when hiring signal is weak. |
| Bench overcommitment is not enforced functionally | P-009 through P-012 | Fixed | Add a capacity-check layer that matches requested stack, seniority, engineer count, commitment notes, and deployment lead time before composing replies or booking calls. |
| Static competitor gap benchmark | P-031 | Fixed | Replace the bundled sample benchmark with live/generated sector-peer research, or block Segment 4 gap claims unless real peer evidence exists. |
| Layoff percentage is not computed from headcount | P-027 | Fixed | Add fallback calculation from `laid_off_count / company_headcount` when the percentage field is blank, with confidence metadata. |
| GitHub fork activity can inflate AI maturity | P-028 | Fixed | Track original commits separately from forks, stars, or cloned repositories before setting `github_activity=True`. |
| Long subject lines | P-015 | Fixed | Add subject truncation or alternate short templates for long company names. |

## Documentation Gaps

| Gap | Status | Remediation |
|---|---|---|
| `held_out_traces.jsonl` is a probe-ablation trace summary, not sealed held-out traces | Addressed | The root export is now the merged sealed held-out trace file for all three conditions. |
| `method.md` needs final benchmark results later | Addressed | `method.md` now includes sealed held-out results, confidence intervals, p-value, cost, and latency. |
| README needs final status update after sealed evaluation | Addressed | README now reflects the sealed artifact package. |

## Recommended Order

1. Wire confidence end-to-end into production outreach.
2. Fix ICP priority/order and Segment 1 open-role gating.
3. Add real bench capacity enforcement.
4. Tighten the memo around the positive-but-not-significant Delta A result.
5. Iterate on the coordination method if we want a cleaner significance margin.
