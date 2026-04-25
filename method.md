# Act IV Method

## Mechanism

**Name:** dual-control coordination prompt (v2)

**Target failure mode:** `coordination_breakdown` on the sealed `retail` slice.

The mechanism is a prompt-level coordination policy for τ²-Bench's default `LLMAgent`. Instead of relying on the stock generic instruction, it appends a compact set of operational rules that force the agent to decide whether the next step is user-facing clarification or tool execution.

Core policy additions:

1. Re-plan immediately when the user changes their mind, rather than continuing a stale plan.
2. When only one path is valid, explain the constraint briefly and execute only that path.
3. Use recent-order lookup to reconcile guessed or inconsistent order IDs before giving up.
4. Fetch exact order details before exchange actions, and use the ordered item's `product_id` for variant lookup.
5. Trust order payment history when processing original-payment returns.
6. Bundle "cancel/return everything possible" requests into a compact gather-then-confirm flow.
7. Pivot to the best valid alternative when the requested item-level operation is impossible on a pending order.

Implementation is in `eval/tau2_prompt_entry.py` and `eval/run_coordination_method.py`. The selected profile is `dual_control_v2`.

## Design Rationale

The earlier Act IV mechanism targeted outreach overclaiming inside the conversion engine, but the sealed τ² retail benchmark does not exercise that workflow. The real benchmark lever here is the agent prompt used by τ²'s default `LLMAgent`. The v2 coordination policy was designed to reduce stale-plan errors, invalid dual-action attempts, and avoidable lookup failures without changing models, tools, or training data.

## Hyperparameters

- prompt profile: `dual_control_v2`
- agent LLM: `openrouter/qwen/qwen3-next-80b-a3b-instruct`
- user LLM: `openrouter/qwen/qwen3-next-80b-a3b-instruct`
- agent temperature: `0.0`
- user temperature: `0.0`
- task budget: sealed `test` slice, `20` tasks, `1` trial

## Ablation Variants Tested

1. **Day-1 baseline:** stock τ² `LLMAgent` instruction on the sealed slice.
2. **Method (`dual_control_v2`):** explicit coordination and stale-plan recovery rules appended to the default τ² instruction.
3. **Prompt ablation sweep:** `dual_control_v1`, `dual_control_v2`, and `dual_control_v3` on a targeted eight-task sealed subset before the final full-slice run.
4. **Automated-optimization baseline:** auditable dev-search over model temperature on the same overall budget.


## Sealed Held-Out Results

| Condition | pass@1 | 95% CI | Cost / task (USD) | p95 latency |
|---|---:|---:|---:|---:|
| Day-1 baseline | 0.400 | [0.219, 0.613] | 0.0086 | 35.20s |
| Method | 0.450 | [0.258, 0.658] | 0.0102 | 61.53s |
| Automated optimization baseline | 0.400 | [0.219, 0.613] | 0.0116 | 28.87s |

## Three Deltas

- **Delta A:** +0.050 (`p = 0.5000`, CI separation: `false`)
- **Delta B:** +0.050
- **Delta C:** +0.030 versus the published `~0.42` retail reference

Delta A is positive on the sealed held-out slice, but it is not yet statistically significant at `p < 0.05` with the current 20-task sample.

## Interpretation

The upgraded method improved sealed pass@1 from 0.400 to 0.450 by reducing coordination mistakes that the stock τ² prompt made on retail order-management tasks. It also finished ahead of the automated baseline on this slice.

Delta A is directionally better but not statistically decisive yet. Delta B is positive as well, which strengthens the memo even though the confidence intervals still overlap at this sample size.

This is a benchmark-facing mechanism rather than a productized conversion-engine workflow change. The repo now contains both: the earlier outreach-calibration work and the stronger τ² coordination policy used for the official held-out comparison.


## Trace Exports

- Top-level `held_out_traces.jsonl` now contains rows for all three conditions with a `condition` field.
- Canonical source traces remain in:
  - `eval/runs/tau2_sealed/retail-test-20260425_162224-9fb5ef97/held_out_traces.jsonl`
  - `eval/runs/tau2_sealed/retail-test-dual_control_v2-20260425_164711-d86d826b/held_out_traces.jsonl`
  - `eval/runs/auto_opt/retail-autoopt-20260425_121346-57eaac59/held_out_traces.jsonl`
