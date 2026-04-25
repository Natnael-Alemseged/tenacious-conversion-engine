from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Claim:
    claim_id: str
    label: str
    value: object
    unit: str
    sources: list[dict[str, Any]]
    derivation: str
    recompute: dict[str, Any]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _bootstrap_ci_95(
    values: list[float], *, iters: int = 5000, seed: int = 1337
) -> tuple[float, float]:
    import random

    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    if n == 1:
        return values[0], values[0]
    draws: list[float] = []
    for _ in range(iters):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        draws.append(statistics.mean(resample))
    draws.sort()
    return draws[int(0.025 * iters)], draws[int(0.975 * iters)]


def _clopper_pearson_95(k: int, n: int) -> tuple[float, float]:
    # Minimal implementation via inverse regularized incomplete beta.
    # Avoid external deps: use scipy if present would be nicer, but we keep core minimal.
    if n <= 0:
        return 0.0, 0.0
    if k <= 0:
        return 0.0, 1.0 - (0.05 ** (1 / n))
    if k >= n:
        return (0.05 ** (1 / n)), 1.0

    # Use a simple binary search on CDF of beta via math.lgamma.
    def beta_cdf(x: float, a: float, b: float, steps: int = 4000) -> float:
        # Numeric integration (Simpson-ish) — slow but deterministic and dependency-free.
        # Good enough for our n scale (tens to hundreds).
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0

        def log_beta(p: float, q: float) -> float:
            return math.lgamma(p) + math.lgamma(q) - math.lgamma(p + q)

        lb = log_beta(a, b)
        h = x / steps
        total = 0.0
        for i in range(steps + 1):
            t = i * h
            if t == 0.0 or t == 1.0:
                fx = 0.0
            else:
                fx = math.exp((a - 1) * math.log(t) + (b - 1) * math.log(1 - t) - lb)
            weight = 4 if i % 2 == 1 else 2
            if i == 0 or i == steps:
                weight = 1
            total += weight * fx
        return total * h / 3.0

    alpha = 0.05
    a = k
    b = n - k + 1
    # lower bound: BetaInv(alpha/2; k, n-k+1)
    target_lo = alpha / 2
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) > target_lo:
            hi = mid
        else:
            lo = mid
    lower = (lo + hi) / 2

    a2 = k + 1
    b2 = n - k
    target_hi = 1 - alpha / 2
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a2, b2) > target_hi:
            hi = mid
        else:
            lo = mid
    upper = (lo + hi) / 2
    return lower, upper


def build_claims(*, strict_final: bool) -> list[Claim]:
    claims: list[Claim] = []

    # τ² sealed held-out (required)
    sealed_dir = sorted(Path("eval/runs/tau2_sealed").glob("*"))
    if not sealed_dir:
        if strict_final:
            raise RuntimeError("Missing eval/runs/tau2_sealed/* (required for strict-final).")
        return claims
    sealed_run = sealed_dir[-1]
    sealed_traces = _load_jsonl(sealed_run / "held_out_traces.jsonl")
    rewards = [float(r["reward"]) for r in sealed_traces]
    pass_at_1 = statistics.mean(rewards) if rewards else 0.0
    ci_lo, ci_hi = _bootstrap_ci_95(rewards)
    claims.append(
        Claim(
            claim_id="tau2_sealed_pass_at_1",
            label="τ²-Bench retail pass@1 (sealed held-out)",
            value={"mean": pass_at_1, "ci_95": [ci_lo, ci_hi], "n": len(rewards)},
            unit="proportion",
            sources=[
                {"kind": "trace", "path": str(sealed_run / "held_out_traces.jsonl")},
                {"kind": "trace", "path": str(sealed_run / "run_meta.json")},
            ],
            derivation=(
                "Mean reward over sealed held-out simulations; CI via deterministic bootstrap "
                "over simulation rewards."
            ),
            recompute={"command": "uv run python scripts/generate_act5.py --strict-final"},
        )
    )

    # Auto-opt sealed baseline (required)
    auto_dirs = sorted(Path("eval/runs/auto_opt").glob("*"))
    if not auto_dirs:
        if strict_final:
            raise RuntimeError("Missing eval/runs/auto_opt/* (required for Delta B strict-final).")
        return claims
    auto_run = auto_dirs[-1]
    auto_summary = _load_json(auto_run / "summary.json")
    claims.append(
        Claim(
            claim_id="tau2_auto_opt_sealed_pass_at_1",
            label="Automated-optimization baseline pass@1 (sealed held-out)",
            value=float(auto_summary.get("sealed_pass_at_1") or 0.0),
            unit="proportion",
            sources=[
                {"kind": "trace", "path": str(auto_run / "held_out_traces.jsonl")},
                {"kind": "trace", "path": str(auto_run / "run_meta.json")},
            ],
            derivation=(
                "Automated baseline selects best dev config from a fixed sweep, then evaluates "
                "that config on sealed held-out."
            ),
            recompute={
                "command": (
                    "SEALED_EVAL=1 uv run python eval/run_auto_opt_baseline.py --domain retail"
                )
            },
        )
    )

    # Invoice rollup (required for CPL numerator)
    inv = _load_json(Path("eval/runs/invoice_summary.json"))
    claims.append(
        Claim(
            claim_id="total_cost_usd",
            label="Total measured cost (USD) for Act V rollup window",
            value=float(inv.get("total_cost_usd") or 0.0),
            unit="usd",
            sources=[{"kind": "trace", "path": "eval/runs/invoice_summary.json"}],
            derivation="Rollup total_cost_usd from the invoice summary.",
            recompute={
                "command": "uv run python scripts/build_invoice_rollup.py --include-auto-opt"
            },
        )
    )

    return claims
