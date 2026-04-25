from __future__ import annotations

from typing import Any


def claim_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["claim_id"]: c for c in evidence.get("claims", [])}


def require_claim(claims: dict[str, dict[str, Any]], claim_id: str) -> dict[str, Any]:
    if claim_id not in claims:
        raise KeyError(f"Missing claim_id={claim_id}")
    return claims[claim_id]


def fmt_percent(x: float) -> str:
    return f"{x * 100:.1f}%"


def fmt_usd(x: float) -> str:
    return f"${x:,.0f}"
