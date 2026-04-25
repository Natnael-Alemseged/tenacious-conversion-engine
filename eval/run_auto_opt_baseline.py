"""Act V automated-optimization baseline runner (Delta B).

This repo does not vendor GEPA/AutoAgent. Instead, we implement an explicit,
auditable automated baseline that uses a small, pre-registered configuration
search on the dev split (train) and then evaluates the selected config on the
sealed held-out split (test).

Strictness goals:
- Produces canonical artifacts under eval/runs/auto_opt/<run_id>/
- Produces invoice_summary.json with USD budget accounting from tau2 logs
- Requires SEALED_EVAL=1 when touching the sealed split
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).parent
BACKEND_DIR = EVAL_DIR.parent.parent
TAU2_PATH = BACKEND_DIR / "tau2-bench"
RUNS_DIR = EVAL_DIR / "runs"


def _now_utc_compact() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.gmtime())


def _unique_save_to(*, domain: str, split: str, label: str) -> str:
    return f"ce-autoopt-{domain}-{split}-{label}-{_now_utc_compact()}-{uuid.uuid4().hex[:8]}"


def _run_tau2(
    *,
    domain: str,
    agent_llm: str,
    agent_llm_args: dict[str, Any],
    user_llm: str,
    user_llm_args: dict[str, Any],
    task_split_name: str,
    num_tasks: int,
    seed: int,
    label: str,
) -> Path:
    save_to = _unique_save_to(domain=domain, split=task_split_name, label=label)
    cmd = [
        "uv",
        "run",
        "tau2",
        "run",
        "--domain",
        domain,
        "--agent-llm",
        agent_llm,
        "--agent-llm-args",
        json.dumps(agent_llm_args),
        "--user-llm",
        user_llm,
        "--user-llm-args",
        json.dumps(user_llm_args),
        "--task-split-name",
        task_split_name,
        "--num-trials",
        "1",
        "--num-tasks",
        str(num_tasks),
        "--seed",
        str(seed),
        "--save-to",
        save_to,
        "--auto-resume",
    ]
    result = subprocess.run(cmd, cwd=TAU2_PATH, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return TAU2_PATH / "data" / "simulations" / save_to / "results.json"


def _walk_numbers(obj: Any) -> list[float]:
    numbers: list[float] = []
    if isinstance(obj, dict):
        for value in obj.values():
            numbers.extend(_walk_numbers(value))
    elif isinstance(obj, list):
        for value in obj:
            numbers.extend(_walk_numbers(value))
    elif isinstance(obj, (int, float)):
        numbers.append(float(obj))
    return numbers


def _sum_upstream_inference_cost(payload: Any) -> float:
    """Sum all occurrences of cost_details.upstream_inference_cost in a results.json payload."""
    total = 0.0
    if isinstance(payload, dict):
        if "cost_details" in payload and isinstance(payload["cost_details"], dict):
            c = payload["cost_details"].get("upstream_inference_cost")
            if isinstance(c, (int, float)):
                total += float(c)
        for v in payload.values():
            total += _sum_upstream_inference_cost(v)
    elif isinstance(payload, list):
        for v in payload:
            total += _sum_upstream_inference_cost(v)
    return total


def _extract_sim_rows(
    results_json: dict[str, Any], *, source_results_path: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sim in results_json.get("simulations", []):
        rows.append(
            {
                "trace_id": str(sim.get("id", "")),
                "task_id": str(sim.get("task_id", "")),
                "reward": float((sim.get("reward_info") or {}).get("reward") or 0.0),
                "agent_cost_usd": float(sim.get("agent_cost") or 0.0),
                "duration_s": float(sim.get("duration") or 0.0),
                "termination_reason": str(sim.get("termination_reason") or ""),
                "source_results_path": source_results_path,
            }
        )
    return rows


def _pass_at_1(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return statistics.mean([float(r["reward"]) for r in rows])


@dataclass(frozen=True)
class Candidate:
    label: str
    agent_llm: str
    agent_llm_args: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="retail")
    parser.add_argument("--dev-split", default="train")
    parser.add_argument("--sealed-split", default="test")
    parser.add_argument("--dev-num-tasks", type=int, default=10)
    parser.add_argument("--sealed-num-tasks", type=int, default=20)
    parser.add_argument("--seed", type=int, default=300)
    parser.add_argument(
        "--budget-usd",
        type=float,
        default=12.0,
        help="USD budget cap for the automated baseline search + sealed eval.",
    )
    args = parser.parse_args()

    user_llm = "openrouter/qwen/qwen3-next-80b-a3b-instruct"
    user_llm_args: dict[str, Any] = {"temperature": 0.0}

    # Minimal, auditable search space. This is not meant to beat SOTA; it is a
    # deterministic automated baseline for Delta B.
    candidates = [
        Candidate(
            label="temp0",
            agent_llm="openrouter/qwen/qwen3-next-80b-a3b-instruct",
            agent_llm_args={"temperature": 0.0},
        ),
        Candidate(
            label="temp0_2",
            agent_llm="openrouter/qwen/qwen3-next-80b-a3b-instruct",
            agent_llm_args={"temperature": 0.2},
        ),
    ]

    # Phase 1: dev search
    spent = 0.0
    dev_scores: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for cand in candidates:
        results_path = _run_tau2(
            domain=args.domain,
            agent_llm=cand.agent_llm,
            agent_llm_args=cand.agent_llm_args,
            user_llm=user_llm,
            user_llm_args=user_llm_args,
            task_split_name=args.dev_split,
            num_tasks=args.dev_num_tasks,
            seed=args.seed,
            label=f"dev-{cand.label}",
        )
        payload = json.loads(results_path.read_text(encoding="utf-8"))
        cost = _sum_upstream_inference_cost(payload)
        spent += cost
        rows = _extract_sim_rows(payload, source_results_path=str(results_path))
        score = _pass_at_1(rows)
        entry = {
            "label": cand.label,
            "agent_llm": cand.agent_llm,
            "agent_llm_args": cand.agent_llm_args,
            "dev_results_path": str(results_path),
            "dev_pass_at_1": score,
            "dev_cost_usd": cost,
        }
        dev_scores.append(entry)
        if (
            best is None
            or score > float(best["dev_pass_at_1"])
            or (score == float(best["dev_pass_at_1"]) and cost < float(best["dev_cost_usd"]))
        ):
            best = entry
        if spent >= args.budget_usd:
            break

    if best is None:
        raise SystemExit("No candidates evaluated; cannot produce automated baseline.")

    # Phase 2: sealed eval with best dev config
    if os.environ.get("SEALED_EVAL") != "1":
        raise SystemExit(
            "Refusing to run sealed split without SEALED_EVAL=1. "
            "Set SEALED_EVAL=1 explicitly to acknowledge this is the sealed run."
        )

    sealed_results_path = _run_tau2(
        domain=args.domain,
        agent_llm=str(best["agent_llm"]),
        agent_llm_args=dict(best["agent_llm_args"]),
        user_llm=user_llm,
        user_llm_args=user_llm_args,
        task_split_name=args.sealed_split,
        num_tasks=args.sealed_num_tasks,
        seed=args.seed,
        label=f"sealed-{best['label']}",
    )
    sealed_payload = json.loads(sealed_results_path.read_text(encoding="utf-8"))
    sealed_cost = _sum_upstream_inference_cost(sealed_payload)
    sealed_rows = _extract_sim_rows(sealed_payload, source_results_path=str(sealed_results_path))
    sealed_pass = _pass_at_1(sealed_rows)

    run_id = f"{args.domain}-autoopt-{_now_utc_compact()}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / "auto_opt" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "run_id": run_id,
        "domain": args.domain,
        "auto_opt_method": "auto_opt_model_arg_sweep",
        "budget_usd": args.budget_usd,
        "dev_split": args.dev_split,
        "sealed_split": args.sealed_split,
        "user_llm": user_llm,
        "user_llm_args": user_llm_args,
        "selected": {
            "label": best["label"],
            "agent_llm": best["agent_llm"],
            "agent_llm_args": best["agent_llm_args"],
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paths": {
            "sealed_results_path": str(sealed_results_path),
            "dev_results_paths": [str(d["dev_results_path"]) for d in dev_scores],
        },
    }
    (run_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    (run_dir / "dev_search.json").write_text(
        json.dumps(dev_scores, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "held_out_traces.jsonl").write_text(
        "\n".join(json.dumps(r) for r in sealed_rows) + ("\n" if sealed_rows else ""),
        encoding="utf-8",
    )

    invoice = {
        "currency": "USD",
        "window": {"kind": "single_run", "run_id": run_id},
        "line_items": [
            {
                "kind": "llm_upstream_inference",
                "provider": "litellm/openrouter",
                "amount_usd": sealed_cost + sum(float(d["dev_cost_usd"]) for d in dev_scores),
                "detail": (
                    "Sum of cost_details.upstream_inference_cost across tau2 results.json payloads."
                ),
            }
        ],
        "total_cost_usd": sealed_cost + sum(float(d["dev_cost_usd"]) for d in dev_scores),
    }
    (run_dir / "invoice_summary.json").write_text(
        json.dumps(invoice, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "sealed_pass_at_1": sealed_pass,
        "sealed_cost_usd": sealed_cost,
        "dev_spent_usd": sum(float(d["dev_cost_usd"]) for d in dev_scores),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"run_dir": str(run_dir), **summary}, indent=2))


if __name__ == "__main__":
    main()
