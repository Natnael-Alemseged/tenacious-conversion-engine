# Act IV Method

## Mechanism

**Name:** Signal-confidence-gated opener calibration

**Target failure mode:** `signal_overclaiming`, selected in `probes/target_failure_mode.md`.

The Act III probe suite found that the Segment 1 opener stayed assertive even when the underlying signal confidence was low. In particular, `P-005` triggered on 9/9 trials because a prospect with confidence below 0.5 still received: "Congratulations on the recent funding — {company} is clearly in growth mode."

The mechanism changes the outbound email opener from a static segment template to a confidence-calibrated template:

| Confidence | Phrasing mode | Behavior |
|---:|---|---|
| `>= 0.8` | `direct` | Keep direct segment-specific claim. |
| `>= 0.5 and < 0.8` | `hedged` | Use "suggests/may" language. |
| `< 0.5` | `exploratory` | Ask rather than assert. |

Implementation:

- `agent.enrichment.ai_maturity.confidence_phrasing()` remains the threshold function.
- `agent.workflows.lead_orchestrator._segment_opener()` now maps `(segment, phrasing)` to calibrated opener copy.
- `LeadOrchestrator.send_outbound_email()` computes phrasing before composing the opener and signal line.
- Low-confidence Segment 1 copy now says: "I saw a recent funding signal for {company}, but I do not want to over-read it. Is scaling engineering capacity actually a current priority?"

## Rationale

The business cost of `signal_overclaiming` comes from collapsing the "grounded research" premise. When the agent asserts a claim the prospect can falsify, reply-rate lift disappears and Tenacious takes brand risk. The safest fix is not a new model call; it is a deterministic language gate tied to the confidence score already produced by enrichment.

## Ablations

1. **Day-1 baseline:** Static segment opener. Confidence only changes the signal summary line, not the opener.
2. **Method:** Confidence-gated opener plus the existing confidence-gated signal line.
3. **No-segment generic fallback:** Always use Segment 0 generic opener when confidence is below 0.5. This is safer but discards useful context.
4. **Automated-optimization baseline:** Not run in this local pass. GEPA/AutoAgent comparison remains pending because the sealed held-out slice should not be touched before final evaluation.

## Results

The deterministic Act III probe ablation shows the targeted failure moved from **9/9 failures** to **0/9 failures** on `P-005`.

Measured current probe suite:

- `P-005`: 0/9 failures after the mechanism.
- `signal_overclaiming` measured category: 0/39 failures after the mechanism.
- Overall deterministic probe trigger rate: 91/182 (50%), down from 100/182 (55%).

Statistical test for targeted probe:

- Baseline pass rate on `P-005`: 0/9.
- Method pass rate on `P-005`: 9/9.
- Delta A on targeted probe pass rate: +1.00.
- Fisher exact test, one-sided: p approximately 0.00002.

This satisfies the targeted-probe improvement criterion. It does **not** claim sealed τ²-Bench held-out improvement yet; that run is intentionally deferred to final evaluation.

## Cost And Latency

The mechanism adds no LLM calls and no external API calls. Runtime cost and latency impact are effectively zero relative to the Day-1 baseline.

## Residual Risk

This mechanism fixes the highest-ROI signal-overclaiming opener failure, but it does not address all Act III failures. Bench overcommitment, ICP priority ordering, signal reliability, and static competitor-gap benchmark use remain visible in the probe suite and should be considered for later acts or production hardening.
