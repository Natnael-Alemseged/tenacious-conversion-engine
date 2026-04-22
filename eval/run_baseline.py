"""Run a tau2-bench baseline using the real `tau2 run` CLI.

This wrapper assumes `tau2-bench` lives as a sibling directory next to
`conversion-engine`, which matches the architecture we agreed on.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import time
from pathlib import Path

EVAL_DIR = Path(__file__).parent
BACKEND_DIR = EVAL_DIR.parent.parent
TAU2_PATH = BACKEND_DIR / "tau2-bench"
SCORE_LOG = EVAL_DIR / "score_log.json"
TRACE_LOG = EVAL_DIR / "trace_log.jsonl"


def _mean_confidence_interval_95(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {
            "mean": 0.0,
            "ci_95_low": 0.0,
            "ci_95_high": 0.0,
            "ci_95_margin": 0.0,
        }

    mean = statistics.mean(samples)
    if len(samples) == 1:
        return {
            "mean": mean,
            "ci_95_low": mean,
            "ci_95_high": mean,
            "ci_95_margin": 0.0,
        }

    sample_stdev = statistics.stdev(samples)
    margin = 1.96 * (sample_stdev / math.sqrt(len(samples)))
    return {
        "mean": mean,
        "ci_95_low": max(0.0, mean - margin),
        "ci_95_high": min(1.0, mean + margin),
        "ci_95_margin": margin,
    }


def _extract_trial_rewards(results_path: Path) -> list[float]:
    data = json.loads(results_path.read_text())
    simulations = data.get("simulations", [])
    return [float(sim.get("reward_info", {}).get("reward") or 0.0) for sim in simulations]


def _model_slug(llm: str) -> str:
    """Short filesystem-safe slug from a model string."""
    return llm.split("/")[-1][:32].replace(":", "-")


def run_trial(
    domain: str,
    agent_llm: str,
    user_llm: str,
    task_split_name: str,
    num_tasks: int | None,
    task_ids: list[str] | None,
    trial_index: int,
) -> dict:
    slug = _model_slug(agent_llm)
    save_to = f"ce-baseline-{domain}-{slug}-t{trial_index}"
    cmd = [
        "uv",
        "run",
        "tau2",
        "run",
        "--domain",
        domain,
        "--agent-llm",
        agent_llm,
        "--user-llm",
        user_llm,
        "--task-split-name",
        task_split_name,
        "--num-trials",
        "1",
        "--save-to",
        save_to,
        "--auto-resume",
    ]
    if task_ids:
        cmd.extend(["--task-ids", *task_ids])
    elif num_tasks is not None:
        cmd.extend(["--num-tasks", str(num_tasks)])

    start = time.time()
    result = subprocess.run(cmd, cwd=TAU2_PATH, capture_output=True, text=True)
    elapsed = time.time() - start
    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    results_path = TAU2_PATH / "data" / "simulations" / save_to / "results.json"
    rewards = _extract_trial_rewards(results_path)
    pass_at_1 = statistics.mean(rewards) if rewards else 0.0

    return {
        "trial_index": trial_index,
        "elapsed_s": elapsed,
        "save_to": save_to,
        "results_path": str(results_path),
        "num_simulations": len(rewards),
        "pass_at_1": pass_at_1,
        "stdout": result.stdout,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="retail")
    parser.add_argument("--agent-llm", default="openrouter/qwen/qwen3-next-80b-a3b-instruct")
    parser.add_argument("--user-llm", default="openrouter/qwen/qwen3-next-80b-a3b-instruct")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--task-split-name", default="train")
    parser.add_argument("--num-tasks", type=int, default=30)
    parser.add_argument("--task-ids", nargs="+")
    args = parser.parse_args()

    results = [
        run_trial(
            domain=args.domain,
            agent_llm=args.agent_llm,
            user_llm=args.user_llm,
            task_split_name=args.task_split_name,
            num_tasks=args.num_tasks,
            task_ids=args.task_ids,
            trial_index=trial_index,
        )
        for trial_index in range(args.trials)
    ]

    pass_scores = [trial["pass_at_1"] for trial in results]
    ci = _mean_confidence_interval_95(pass_scores)
    summary = {
        "domain": args.domain,
        "agent_llm": args.agent_llm,
        "user_llm": args.user_llm,
        "task_split_name": args.task_split_name,
        "num_tasks": args.num_tasks,
        "task_ids": args.task_ids,
        "trials": args.trials,
        "mean_pass_at_1": ci["mean"],
        "ci_95_low": ci["ci_95_low"],
        "ci_95_high": ci["ci_95_high"],
        "ci_95_margin": ci["ci_95_margin"],
        "min_pass_at_1": min(pass_scores) if pass_scores else 0.0,
        "max_pass_at_1": max(pass_scores) if pass_scores else 0.0,
        "results": results,
    }

    existing = json.loads(SCORE_LOG.read_text()) if SCORE_LOG.exists() else []
    existing.append(summary)
    SCORE_LOG.write_text(json.dumps(existing, indent=2))

    with TRACE_LOG.open("a") as trace_file:
        for trial in results:
            trace_file.write(json.dumps(trial) + "\n")

    print(f"Wrote baseline summary to {SCORE_LOG}")


if __name__ == "__main__":
    main()
