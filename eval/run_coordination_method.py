"""Run a tau2-bench evaluation with a coordination-focused prompt override.

This mirrors eval/run_baseline.py but invokes tau2 through a local bootstrap that
patches the default LLMAgent prompt before the run starts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).parent
BACKEND_DIR = EVAL_DIR.parent.parent
TAU2_PATH = BACKEND_DIR / "tau2-bench"
SCORE_LOG = EVAL_DIR / "score_log.json"
TRACE_LOG = EVAL_DIR / "trace_log.jsonl"
RUNS_DIR = EVAL_DIR / "runs"
ENTRYPOINT = EVAL_DIR / "tau2_prompt_entry.py"


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


def _bootstrap_ci_95(
    samples: list[float], *, iters: int = 5000, seed: int = 1337
) -> dict[str, float]:
    if not samples:
        return {"mean": 0.0, "ci_95_low": 0.0, "ci_95_high": 0.0}

    import random

    rng = random.Random(seed)
    n = len(samples)
    mean = statistics.mean(samples)
    if n == 1:
        return {"mean": mean, "ci_95_low": mean, "ci_95_high": mean}

    draws: list[float] = []
    for _ in range(iters):
        resample = [samples[rng.randrange(n)] for _ in range(n)]
        draws.append(statistics.mean(resample))
    draws.sort()
    lo = draws[int(0.025 * iters)]
    hi = draws[int(0.975 * iters)]
    return {"mean": mean, "ci_95_low": max(0.0, lo), "ci_95_high": min(1.0, hi)}


def _extract_trial_rewards(results_path: Path) -> list[float]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    simulations = data.get("simulations", [])
    return [float((sim.get("reward_info") or {}).get("reward") or 0.0) for sim in simulations]


def _write_run_dir(
    *,
    run_dir: Path,
    domain: str,
    agent_llm: str,
    user_llm: str,
    task_split_name: str,
    prompt_profile: str,
    results: list[dict[str, Any]],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_dir.name,
        "domain": domain,
        "agent_llm": agent_llm,
        "user_llm": user_llm,
        "task_split_name": task_split_name,
        "prompt_profile": prompt_profile,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    lines: list[str] = []
    for trial in results:
        trial_idx = int(trial["trial_index"])
        src = Path(trial["results_path"])
        dst = run_dir / f"trial_{trial_idx}_results.json"
        if not src.exists():
            continue
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        payload = json.loads(dst.read_text(encoding="utf-8"))
        for sim in payload.get("simulations", []):
            lines.append(
                json.dumps(
                    {
                        "trace_id": str(sim.get("id", "")),
                        "task_id": str(sim.get("task_id", "")),
                        "reward": float((sim.get("reward_info") or {}).get("reward") or 0.0),
                        "agent_cost_usd": float(sim.get("agent_cost") or 0.0),
                        "duration_s": float(sim.get("duration") or 0.0),
                        "termination_reason": str(sim.get("termination_reason") or ""),
                        "source_results_path": str(dst),
                    }
                )
            )
    (run_dir / "held_out_traces.jsonl").write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )


def _model_slug(llm: str) -> str:
    return llm.split("/")[-1][:32].replace(":", "-")


def run_trial(
    *,
    domain: str,
    agent_llm: str,
    user_llm: str,
    task_split_name: str,
    num_tasks: int | None,
    task_ids: list[str] | None,
    trial_index: int,
    prompt_profile: str,
    agent_llm_args: dict[str, Any] | None,
    user_llm_args: dict[str, Any] | None,
) -> dict[str, Any]:
    slug = _model_slug(agent_llm)
    save_to = (
        f"ce-coord-{domain}-{task_split_name}-{slug}-t{trial_index}-"
        f"{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}"
    )
    cmd = [
        "uv",
        "run",
        "python",
        str(ENTRYPOINT),
        "--profile",
        prompt_profile,
        "--",
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
    if agent_llm_args:
        cmd.extend(["--agent-llm-args", json.dumps(agent_llm_args)])
    if user_llm_args:
        cmd.extend(["--user-llm-args", json.dumps(user_llm_args)])
    if task_ids:
        cmd.extend(["--task-ids", *task_ids])
    elif num_tasks is not None:
        cmd.extend(["--num-tasks", str(num_tasks)])

    start = time.time()
    result = subprocess.run(cmd, cwd=TAU2_PATH, capture_output=True, text=True)
    elapsed = time.time() - start
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

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
        "prompt_profile": prompt_profile,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="retail")
    parser.add_argument("--agent-llm", default="openrouter/qwen/qwen3-next-80b-a3b-instruct")
    parser.add_argument("--user-llm", default="openrouter/qwen/qwen3-next-80b-a3b-instruct")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--task-split-name", default="train")
    parser.add_argument("--num-tasks", type=int, default=30)
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument("--write-run-dir", action="store_true")
    parser.add_argument("--prompt-profile", default="dual_control_v1")
    parser.add_argument("--agent-llm-args", type=json.loads, default={"temperature": 0.0})
    parser.add_argument("--user-llm-args", type=json.loads, default={"temperature": 0.0})
    args = parser.parse_args()

    if args.task_split_name == "test" and os.environ.get("SEALED_EVAL") != "1":
        raise SystemExit(
            "Refusing to run sealed held-out split without SEALED_EVAL=1. "
            "Set SEALED_EVAL=1 explicitly to acknowledge this is the sealed run."
        )

    results = [
        run_trial(
            domain=args.domain,
            agent_llm=args.agent_llm,
            user_llm=args.user_llm,
            task_split_name=args.task_split_name,
            num_tasks=args.num_tasks,
            task_ids=args.task_ids,
            trial_index=trial_index,
            prompt_profile=args.prompt_profile,
            agent_llm_args=args.agent_llm_args,
            user_llm_args=args.user_llm_args,
        )
        for trial_index in range(args.trials)
    ]

    pass_scores = [trial["pass_at_1"] for trial in results]
    ci = _mean_confidence_interval_95(pass_scores)
    boot = _bootstrap_ci_95(pass_scores)
    summary = {
        "domain": args.domain,
        "agent_llm": args.agent_llm,
        "agent_llm_args": args.agent_llm_args,
        "user_llm": args.user_llm,
        "user_llm_args": args.user_llm_args,
        "task_split_name": args.task_split_name,
        "num_tasks": args.num_tasks,
        "task_ids": args.task_ids,
        "trials": args.trials,
        "prompt_profile": args.prompt_profile,
        "mean_pass_at_1": ci["mean"],
        "ci_95_low": ci["ci_95_low"],
        "ci_95_high": ci["ci_95_high"],
        "ci_95_margin": ci["ci_95_margin"],
        "bootstrap_ci_95_low": boot["ci_95_low"],
        "bootstrap_ci_95_high": boot["ci_95_high"],
        "bootstrap_ci_method": "bootstrap_mean_over_trials",
        "bootstrap_ci_iters": 5000,
        "min_pass_at_1": min(pass_scores) if pass_scores else 0.0,
        "max_pass_at_1": max(pass_scores) if pass_scores else 0.0,
        "results": results,
    }

    existing = json.loads(SCORE_LOG.read_text(encoding="utf-8")) if SCORE_LOG.exists() else []
    existing.append(summary)
    SCORE_LOG.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    with TRACE_LOG.open("a", encoding="utf-8") as trace_file:
        for trial in results:
            trace_file.write(json.dumps(trial) + "\n")

    print(f"Wrote coordination-method summary to {SCORE_LOG}")

    if args.write_run_dir:
        run_id = (
            f"{args.domain}-{args.task_split_name}-{args.prompt_profile}-"
            f"{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:8]}"
        )
        bucket = "tau2_sealed" if args.task_split_name == "test" else "tau2_dev"
        run_dir = RUNS_DIR / bucket / run_id
        _write_run_dir(
            run_dir=run_dir,
            domain=args.domain,
            agent_llm=args.agent_llm,
            user_llm=args.user_llm,
            task_split_name=args.task_split_name,
            prompt_profile=args.prompt_profile,
            results=results,
        )
        print(f"Wrote run artifacts to {run_dir}")


if __name__ == "__main__":
    main()
