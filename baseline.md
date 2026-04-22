# Baseline

## Model and Scope

**Model:** `openrouter/qwen/qwen3-next-80b-a3b-instruct` (Qwen3-Next-80B-A3B via OpenRouter)
**Domain:** retail (τ²-Bench)
**Task split:** `train` — first 30 tasks (the dev slice; `test` split is sealed and untouched)
**Trials:** 5 scheduled; 3 valid (trials 3 and 4 failed with `infrastructure_error` — see below)

## Command

```bash
uv run python eval/run_baseline.py \
  --domain retail \
  --agent-llm openrouter/qwen/qwen3-next-80b-a3b-instruct \
  --user-llm openrouter/qwen/qwen3-next-80b-a3b-instruct \
  --trials 5 --num-tasks 30 --task-split-name train
```

## Results (3 valid trials)

| Metric | Value |
|--------|-------|
| Mean pass@1 | **0.278** |
| 95% CI | [0.157, 0.399] |
| CI margin (±) | 0.121 |
| Trial scores | 0.400, 0.233, 0.200 |

For reference, τ²-Bench retail ceiling is ~0.42 (published leaderboard, Feb 2026).

Full statistical breakdown is in `eval/score_log.json`. Per-trial references to raw simulation directories are in `eval/trace_log.jsonl`.

## Infrastructure Failures

Trials 3 and 4 terminated with `infrastructure_error` on all 30 simulations each. This is a τ²-Bench internal classification for LLM-provider failures (connection errors, malformed responses, or rate limits from OpenRouter). The agent never ran — the simulator could not reach the model. These trials are recorded in `score_log.json` with `infrastructure_error_trial: true` and are excluded from the valid-trial statistics above.

## Cost Caveat

LiteLLM's pricing table does not map `openrouter/qwen/qwen3-next-80b-a3b-instruct` to a pricing entry. The model alias returned by OpenRouter (`qwen3-next-80b-a3b-instruct-2509`) is also unmapped. All cost fields in the raw simulation results are unreliable and should not be used for cost-per-lead calculations until the model alias is added to LiteLLM's pricing table or OpenRouter returns a recognized string.

## Unexpected Behavior

The infrastructure failures in trials 3 and 4 were not accompanied by explicit rate-limit headers in the tau2 logs. The most likely cause is OpenRouter request queuing under sustained load (5 parallel trial runs hitting the same endpoint). The valid trials were run earlier in the session with lower concurrency.

The 30-task dev slice here maps to the first 30 task IDs in τ²-Bench's `train` split. The program-delivered 30-task partition was not present in the repository; this approximation uses the same split mechanism tau2 exposes and does not touch the `test` split.
