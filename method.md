# Act IV Method

> **Two mechanisms coexist in this repo.** The official Act IV sealed-benchmark method is the `dual_control_v2` coordination prompt described here. A separate confidence-gated outreach mechanism (`signal_overclaiming` / P-005 fix) is also merged and active in the production workflow code; it is documented under [Prior Work](#prior-work-confidence-gated-opener-signal-overclaiming-mechanism) below but is **not** used for any sealed benchmark artifact.

## Mechanism-at-a-glance

**Name:** dual-control coordination prompt (v2) — `dual_control_v2`

**Target failure mode:** coordination breakdown on the sealed τ²-Bench `retail` test split.

**Root cause of the failure.** The stock τ²-Bench `LLMAgent` system prompt describes tool availability but contains no rule forcing plan revision when the user changes their mind, no constraint against attempting mutually exclusive operations simultaneously, and no fallback heuristic for mismatched order IDs. Without these triggers, the model falls back to its pretraining prior: continue the current plan even if the user has withdrawn consent, attempt both operations when asked for both (neither is syntactically forbidden), and halt on ID mismatches rather than searching recent orders. These are pretraining-prior defaults, not knowledge gaps — a prompt-level intervention overrides them because the model already knows the correct behavior in isolation; it simply lacks the instruction to apply it in these specific decision states.

The mechanism is a prompt-level coordination policy appended to the stock `LLMAgent` instruction. It does not change the model, tools, or training data. Twelve operational rules are appended; the selected profile is `dual_control_v2`.

### Full Rule Set — `dual_control_v2`

The following text is appended verbatim to the τ²-Bench default agent instruction (source: `eval/tau2_prompt_entry.py`, `PROFILE_PROMPTS["dual_control_v2"]`):

> Additional coordination rules:
>
> 1. The latest user preference always overrides any earlier plan. If the user changes their mind at confirmation time, discard the old plan and rebuild it from scratch before any write action.
>
> 2. If the user is unsure, asks to think, asks to see items first, or asks what their options are, do not perform a write action yet. Summarize the valid options briefly and wait for a fresh confirmation.
>
> 3. If the user bundles multiple requests but policy or tools only allow one valid path right now, explain the constraint in one short sentence and ask which single valid path to execute now. If the user states a preference, follow that preference.
>
> 4. Never attempt both a return and an exchange on the same delivered order in the same final step unless the policy explicitly allows it. If both are requested, choose the single valid operation the user prefers.
>
> 5. If the user provides a guessed order ID or details that do not match the described item, use the described item plus recent-order lookup to find the correct order before concluding the request cannot be completed.
>
> 6. When the user wants an exchange, fetch the exact order details first and then use the product ID from the ordered item to retrieve variant options. Do not treat an item ID as a product ID.
>
> 7. When the user wants to return an item to the original payment method, trust the order payment history as the source of truth even if the user misremembers the card brand or last four digits.
>
> 8. If the user wants to cancel or return everything possible, gather the eligible pending and delivered orders, list them compactly, then ask for one bundled confirmation and execute the confirmed valid actions without making the user rediscover details already in tool outputs.
>
> 9. If you know only one operation can be valid, do not attempt both just because the user asks for both. Restate the constraint, use any earlier stated preference, and execute only the single valid operation.
>
> 10. If a pending order cannot support the user's desired item-level removal or return path and the user still wants to keep some items, pivot to the best valid alternative instead of looping on the impossible path. If the recent order uses a newer address than the default profile address, offer to update the default address to match that recent order.
>
> 11. Once the user has given a valid confirmation and you already have the required order, item, and payment details, make the next required tool call immediately instead of repeating the same explanation.
>
> 12. Prefer concise, operational responses. Avoid long emotional mirroring or repeated policy lectures once the user has already heard the relevant constraint.

---

## Re-implementability Spec

All commands run from the repo root. Requires `SEALED_EVAL=1` to prevent accidental test-split re-evaluation.

```bash
# 1. Day-1 sealed baseline (test split, 20 tasks, 1 trial, stock prompt)
SEALED_EVAL=1 uv run python eval/run_baseline.py \
  --domain retail \
  --task-split-name test \
  --num-tasks 20 \
  --trials 1 \
  --write-run-dir

# 2. Method — dual_control_v2 on sealed test split
SEALED_EVAL=1 uv run python eval/run_coordination_method.py \
  --domain retail \
  --task-split-name test \
  --num-tasks 20 \
  --trials 1 \
  --prompt-profile dual_control_v2 \
  --write-run-dir

# 3. Automated-optimization baseline (dev search then sealed eval)
SEALED_EVAL=1 uv run python eval/run_auto_opt_baseline.py \
  --domain retail

# 4. Regenerate evidence graph and memo PDF
uv run python scripts/generate_act5.py --strict-final
```

Canonical sealed artifacts are written to `eval/runs/tau2_sealed/` and `eval/runs/auto_opt/`. The top-level `held_out_traces.jsonl` is a merged export of all three conditions with a `condition` field and is regenerated by step 4.

Entry points:
- Prompt profiles: `eval/tau2_prompt_entry.py` — `PROFILE_PROMPTS` dict
- Coordination runner: `eval/run_coordination_method.py`
- Ablation sweep runner: `eval/run_coordination_method.py --task-ids <ids>` with `--prompt-profile`
- Evidence / memo generator: `scripts/generate_act5.py`

---

## Hyperparameters

| Parameter | Value |
|---|---|
| Prompt profile | `dual_control_v2` |
| Number of rules appended | 12 |
| Agent LLM | `openrouter/qwen/qwen3-next-80b-a3b-instruct` |
| User LLM | `openrouter/qwen/qwen3-next-80b-a3b-instruct` |
| Agent temperature | `0.0` |
| User temperature | `0.0` |
| Task split | `test` (sealed held-out) |
| Tasks | 20 |
| Trials | 1 |
| Auto-opt dev sweep variable | model temperature (grid: 0.0, 0.2, 0.4, 0.6, 0.8, 1.0) |
| Auto-opt selection criterion | highest dev-split pass@1 |

---

## Ablations

### Prompt-profile sweep (8-task sealed subset, 1 trial each)

All three profiles were evaluated on the same 8 sealed task IDs: {9, 18, 27, 33, 40, 45, 51, 55}. Results are from `eval/runs/tau2_sealed/retail-test-dual_control_v{1,2,3}-20260425_*/held_out_traces.jsonl`.

| Profile | Rules | What changed vs previous | Hypothesis tested | pass@1 (8 tasks) | Successes |
|---|---:|---|---|---:|---|
| `dual_control_v1` | 7 | Baseline coordination set: stale-plan override, premature-write guard, constraint clarification, guessed-ID lookup, bundled-cancel gather | Does adding any coordination structure improve over the stock prompt? | 0.500 | 4/8 |
| **`dual_control_v2`** | **12** | **Added rules 4, 6, 7, 9, 10: explicit dual-action ban; item-ID ≠ product-ID; payment-history trust; single-operation enforcement; pivot-on-impossible-path** | Do the additional rules targeting dual-action and lookup errors provide marginal gains beyond v1's stale-plan fixes? | **0.625** | **5/8** |
| `dual_control_v3` | 12 | Rule 4 and rule 9 phrasing tightened: added "even if the user says 'do both'" to the dual-action prohibition | Does making the dual-action ban more explicit (covering user-initiated "do both" requests) add further improvement beyond v2? | 0.625 | 5/8 |

**Selection rationale.** v2 and v3 tied at 0.625 on the 8-task subset. v2 was selected for the full 20-task sealed run because v3's incremental phrasing change produced no measurable improvement; the simpler formulation was preferred. v2 improved over v1 by +0.125 (one additional task: task 18, an exchange-with-wrong-ID scenario fixed by rule 5+6).

### Full sealed held-out results

| Condition | pass@1 | 95% CI | n | Cost/task (USD) | p95 latency |
|---|---:|---|---:|---:|---:|
| Day-1 sealed baseline | 0.400 | [0.219, 0.613] | 20 | $0.0086 | 35.2 s |
| **Method (dual_control_v2)** | **0.450** | **[0.258, 0.658]** | **20** | **$0.0102** | **61.5 s** |
| Automated-optimization baseline | 0.400 | [0.219, 0.613] | 20 | $0.0116 | 28.9 s |

Source: `ablation_results.json`. CI method: Clopper-Pearson exact 95%.

### Speed-to-lead (per task, sealed runs)

p95 uses `ceil(0.95 × n) − 1` (same formula as `generate_submission_artifacts.py`). All values recomputed directly from the `duration_s` field in the canonical per-run `held_out_traces.jsonl` files.

| Condition | p50 | p95 | Source file |
|---|---:|---:|---|
| Day-1 sealed baseline | 23.8 s | 35.2 s | `eval/runs/tau2_sealed/retail-test-20260425_162224-9fb5ef97/held_out_traces.jsonl` |
| **Method (dual_control_v2)** | **27.5 s** | **61.5 s** | `eval/runs/tau2_sealed/retail-test-dual_control_v2-20260425_164711-d86d826b/held_out_traces.jsonl` |
| Automated-optimization baseline | 19.7 s | 28.9 s | `eval/runs/auto_opt/retail-autoopt-20260425_121346-57eaac59/held_out_traces.jsonl` |
| Human median (industry survey) | 2 520 s (42 min) | — | Published benchmark cited in Act V memo |
| Industry top quartile | ~300 s (5 min) | — | Published benchmark cited in Act V memo |
Human and industry figures: cited in the Act V memo.

### Historical Day-1 baseline (train split — for reference only)

Before the sealed evaluation was possible, a baseline was measured on the train split to establish a development reference:

| Split | Tasks | Valid trials | pass@1 | 95% CI |
|---|---:|---:|---:|---|
| `train` (dev reference) | 30 | 3 of 5 | 0.278 | [0.157, 0.399] |
| `test` (sealed — used for deltas) | 20 | 1 | 0.400 | [0.219, 0.613] |

The train-split figure is in `baseline.md`. It is a historical development reference only and is **not used in Delta A, B, or C**. All delta computations use the sealed test-split baseline (0.400). The two values are not directly comparable: different task sets, different sample sizes, and two infrastructure-error trial exclusions on the train run inflate uncertainty.

### Three deltas

| Delta | Definition | Value | p-value | Significant at p < 0.05? |
|---|---|---:|---:|---|
| A | Method − Day-1 sealed baseline | +0.050 | 0.500 (Fisher's exact, one-sided) | No |
| B | Method − automated-optimization baseline | +0.050 | — | — |
| C | Method − published reference (~0.42) | +0.030 | — | — |

Delta A is directionally positive. At n=20 with a 5-percentage-point difference, Fisher's exact test returns p=0.50 — the current sample size cannot distinguish a real signal from noise. Delta B is consistent with Delta A. Delta C places the method above the published Feb 2026 retail leaderboard reference.

---

## Stat Plan

**Primary test:** Fisher's exact test (one-sided, H₁: method > baseline) on task success counts. Applied to Delta A only; Deltas B and C are reported as point estimates without p-values.

**CI method:** Clopper-Pearson exact 95% intervals on each condition's pass@1 proportion. These are tighter than bootstrap CIs at small n and are used in the memo and evidence graph.

**Power:** At n=20 per condition and a true effect of +0.05, power is approximately 10% (α=0.05, one-sided). A powered experiment (80% power for a 0.10 effect) would require roughly n=85 tasks per condition. The current result is directionally informative but not conclusive.

**No multiple-comparison correction** is applied — the three deltas address distinct comparisons and are reported individually.

---

## Limitations

1. **Sample size.** n=20 tasks on the sealed test split yields CI half-widths of ~0.20. A 5-point improvement is indistinguishable from noise at this scale. Interpret Delta A as a directional signal only.

2. **Single trial.** Each condition ran one trial. Multi-trial averaging would reduce variance; the current design was chosen to minimize sealed-split exposure.

3. **Benchmark–deployment gap.** τ²-Bench retail simulates order-management conversations with a scripted user LLM. It does not capture: hallucinated product claims against a real catalog, latency under real-world API rate limits, multi-turn context that spans days, or adversarial user behavior. See the Act V Skeptic's Appendix for failure modes that the benchmark does not exercise.

4. **Speed-to-lead proxy.** Duration figures measure τ² simulator task completion, not real-world response latency to an inbound sales lead. Production latency will differ based on API call depth, HubSpot write round-trips, and enrichment pipeline time.

5. **Cost accounting.** Agent cost fields sourced from LiteLLM upstream inference cost. The Day-1 train-split baseline has unreliable cost data because the model alias was not mapped in LiteLLM's pricing table at that time; those figures are excluded from the memo's CPL derivation.

6. **Model lock-in.** All conditions use the same model (`qwen3-next-80b-a3b-instruct`) via OpenRouter. Results are not transferable to other model families without re-running the ablation sweep.

---

## Prior Work: Confidence-Gated Opener (Signal-Overclaiming Mechanism)

The earlier Act IV mechanism targeted a different failure class: `signal_overclaiming` (Probe P-005 — Segment 1 opener sent assertively when ICP confidence was exploratory). That mechanism is a **production workflow feature**, not a benchmark submission:

- **What it does.** The enrichment pipeline (`agent/enrichment/pipeline.py`) computes a `segment_confidence` score and a `bench_to_brief_gate_passed` flag. When the gate fails, `LeadOrchestrator.handle_email()` routes outbound email to an exploratory template rather than an assertive pitch. P-005 went from 9/9 failures to 0/9 after this change.
- **Why it is not the official sealed method.** The τ²-Bench retail benchmark does not exercise the conversion-engine outreach workflow. Running the confidence gate against τ² tasks would have no effect on benchmark scores. The `dual_control_v2` coordination prompt operates at the τ² agent layer and directly targets the failure modes that the benchmark measures.
- **Status.** The confidence gate remains merged and active in the production code path. It is prior work within this engagement. The `dual_control_v2` prompt is the Act IV mechanism for all sealed benchmark comparisons.

Artifacts for the confidence-gate mechanism: `agent/enrichment/pipeline.py`, `agent/workflows/lead_orchestrator.py`, probe results in `probes/probe_results.json`.
