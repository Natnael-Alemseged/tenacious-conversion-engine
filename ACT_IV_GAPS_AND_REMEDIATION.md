# Act IV Gaps And Remediation Plan

This file tracks what remains after the Act IV deterministic probe ablation. The confidence-gated opener mechanism is implemented and reduced `P-005` from 9/9 failures to 0/9, but the strict challenge benchmark work and several production-hardening gaps remain.

## Act IV Completion Gaps

| Gap | Status | Remediation |
|---|---|---|
| Sealed held-out tau2-Bench run is missing | Missing | Run the sealed held-out evaluation only when final-ready, then generate real `held_out_traces.jsonl` from the sealed split. |
| Automated optimization baseline is missing | Missing | Run or document a GEPA/AutoAgent-equivalent baseline on the same compute budget for Delta B. |
| True held-out Delta A is missing | Missing | Compare Day-1 baseline vs Act IV method on sealed held-out with 95% CI separation and p < 0.05. |
| Delta B and Delta C are missing | Missing | Report method vs automated baseline and method vs the published tau2-Bench reference. |
| p95 latency from real tasks is missing | Missing | Aggregate p95 latency from real held-out traces rather than deterministic probes. |
| Confidence mechanism is not wired end-to-end | Resolved | Add a production path that runs `agent.enrichment.pipeline.run()` and passes `brief.icp_segment`, `brief.segment_confidence`, `brief.signals.ai_maturity.score`, and `brief.signals.bench.data.bench_to_brief_gate_passed` into `LeadOrchestrator.send_outbound_email()`. |

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
| `held_out_traces.jsonl` is a probe-ablation trace summary, not sealed held-out traces | Present and caveated | Keep the caveat until final evaluation, or rename to `probe_ablation_traces.jsonl` and reserve `held_out_traces.jsonl` for the sealed run. |
| `method.md` needs final benchmark results later | Pending | After sealed evaluation, add real held-out results, confidence intervals, p-value, cost, and latency. |
| README needs final status update after sealed evaluation | Pending | Change status from deterministic probe ablation complete to Act IV benchmark evaluation complete after final evaluation. |

## Recommended Order

1. Wire confidence end-to-end into production outreach.
2. Fix ICP priority/order and Segment 1 open-role gating.
3. Add real bench capacity enforcement.
4. Update Act IV docs after those fixes.
5. Run sealed held-out evaluation only when the system is stable.
