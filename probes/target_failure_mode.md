# Target Failure Mode

Act III deliverable — the single highest-ROI failure mode to address in Act IV.

---

## Selected Failure Mode: `signal_overclaiming`

**One-line definition:** The agent asserts confident claims about a prospect's hiring velocity, AI maturity, or funding trajectory when the underlying public signal is too weak to support the assertion.

**Primary probes:** P-005, P-006, P-007, P-008
**Highest-frequency probe:** P-005 — assertive Segment 1 opener regardless of confidence (trigger rate **9/9 = 100%, measured 2026-04-24**)
**Trace refs (P-005):** probe-b3388b3c3582, probe-a9b6ee255602, probe-c75fd153a3a8, probe-de53e977f6e4, probe-430cb82a21ec, probe-59e3d410bb4d, probe-1a3c75a37a97, probe-d0352e751055, probe-b7100532eb4f

---

## Business-Cost Derivation

### Step 1 — Frequency estimate

The signal-grounded outreach strategy's value proposition rests on the hiring signal brief producing verifiable, specific claims. Signal overclaiming fires whenever:
- A prospect has < 5 open engineering roles (below Segment 1 qualifying threshold) and the agent asserts growth language
- AI maturity confidence is below 0.5 (`confidence_phrasing()` returns "hedged" or "exploratory") but the agent writes assertive copy
- A funding event is outside the 180-day window but cited as "recent"

In the Crunchbase ODM sample (1,001 companies), roughly 40% of companies that pass initial ICP screening have weak or borderline signals in at least one dimension. On 60 outbound touches/week, an estimated **24 emails/week** carry at least one overclaim when the signal-gating mechanism is not active.

### Step 2 — Reply-rate impact

The entire business case for this system rests on achieving the **7–12% signal-grounded reply rate** (Clay/Smartlead benchmarks) versus the **1–3% cold-email baseline** (LeadIQ 2026). This premium is earned by the recipient thinking "they actually know something about us" — i.e., the signal is verifiable.

When a claim is overclaimed:
- The prospect can immediately verify the signal is wrong (they know their own open roles)
- The "grounded research" framing collapses entirely for that message
- The effective reply rate reverts to or below baseline (1–3%), because an overclaimed email is worse than a generic one — it signals the system is unreliable

**Conservative assumption:** Overclaimed emails convert at 2% (generic baseline). Correctly-hedged emails at 7% (bottom of signal-grounded range). Delta = 5 percentage points per email.

### Step 3 — Pipeline impact per week

```
24 overclaimed emails/week × 5% reply-rate delta = 1.2 additional replies/week if fixed

1.2 replies/week × 52 weeks = 62 additional qualified replies/year

62 replies × 30% discovery-call conversion = 19 additional discovery calls/year

19 discovery calls × 40% proposal conversion = 7.6 proposals/year

7.6 proposals × 25% close rate = 1.9 closed deals/year

1.9 deals × $240K ACV floor (talent outsourcing) = $456K/year in recovered pipeline
```

**Upper bound** (12% reply rate, 50% discovery conversion, 40% close, $480K ACV midpoint):
```
24 × 9% delta = 2.16 replies/week → 112/year → 56 discovery calls → 22 proposals → 9 deals → $4.3M/year
```

**Point estimate used in memo:** $456K–$4.3M/year in recovered pipeline, depending on conversion rates. Midpoint: **~$2.4M/year**.

### Step 4 — Brand-reputation multiplier

The above calculation counts only direct conversion loss. The Tenacious brand risk is a multiplier:

- A CTO who receives an overclaimed email (e.g., "you're scaling aggressively" when they have 3 open roles) may share it as a negative example on LinkedIn or in a Slack community
- Tenacious's primary prospect segment (founders, CTOs, VPs Engineering) is a tightly networked community — a single viral negative post from a well-followed engineering leader reaches 20K–100K followers
- The style guide explicitly warns: "Tenacious-brand risk from a single viral roast of a bad outreach outweighs a week of reply-rate gains"

**Reputation cost estimate:** One viral post → suppressed reply rates on all 60 weekly touches for 4–8 weeks → at 7% expected reply rate, ~17–34 lost replies → at 30% discovery conversion → 5–10 lost calls → at $240K ACV → $1.2M–$2.4M in pipeline suppression.

**Total business cost (direct + reputation):** Conservative estimate $1.5M–$3M/year if not addressed.

---

## Why Signal Overclaiming Outranks Other Failure Modes

### vs. `bench_overcommitment` (second-ranked)

Bench overcommitment (P-009, P-010) is high-severity (broken commitments, contract disputes) but lower frequency. Only fires when a prospect asks a direct capacity question — roughly 30–40% of engaged threads. Signal overclaiming fires on every email composed with weak signals — roughly 40% of outbound at 8/10 trigger rate. **Higher frequency × comparable cost → signal overclaiming wins.**

### vs. `dual_control_coordination / P-023` (stalled threads)

P-023 (no re-engagement after silence) has trigger rate 8/10 and maps directly to the 30–40% stalled-thread rate. Its business cost is real and large. However:
1. The fix for P-023 is a **scheduled background job** (time-based re-engagement trigger), not a model mechanism — it does not require Act IV statistical improvement against a τ²-Bench baseline
2. P-023 affects threads that are already engaged (the prospect replied once). Signal overclaiming damages threads before they start
3. The τ²-Bench benchmark is most directly comparable to signal-confidence-aware phrasing mechanisms — Act IV's Delta A requirement (beat baseline with 95% CI) is more tractable against a mechanism that changes what the agent says, not just when it says it

### vs. `gap_overclaiming` (third-ranked)

Gap overclaiming (P-029, P-030, P-031) has a confirmed issue: `competitor_gap.py` generates briefs from a bundled static sample file rather than real sector peers (P-031: 10/10 measured). Fixing gap overclaiming requires building live competitive research. Signal overclaiming can be fixed independently, in the existing pipeline, today, without any new data sources.

### vs. `icp_misclassification` (fourth-ranked)

ICP misclassification (P-001) is high-severity and medium-frequency. However, the root cause of most ICP misclassification is weak-signal reliance — a correctly grounded classifier would either assign the right segment or abstain. **Signal overclaiming is the upstream failure that feeds ICP misclassification.** Fixing the former partially resolves the latter.

---

## Mechanism Direction for Act IV

The fix is to wire `confidence_phrasing()` (already in `agent/enrichment/ai_maturity.py`) into the outreach generation path as a **phrasing mode gate**:

1. Compute confidence for each signal block (AI maturity, hiring velocity, funding recency)
2. Map confidence to phrasing mode: `direct` (≥ 0.8), `hedged` (0.5–0.8), `exploratory` (< 0.5)
3. Pass phrasing mode as a constraint to the outreach template, not as a soft instruction
4. Gate: if phrasing mode is `exploratory`, the agent **asks rather than asserts** — specific prompt template enforces this

This is a bounded mechanism change (one code path, one new parameter threaded through the orchestrator) with a measurable output (claim strength in generated emails can be scored against the style guide rubric from `style_guide.md`).

**Delta A hypothesis:** Baseline with no confidence gating → signal-overclaiming trigger rate 8/10 on P-005. With confidence gating → target ≤ 1/10. This is a large expected delta, measurable on the 20-task held-out slice.
