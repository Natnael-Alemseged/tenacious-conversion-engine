from __future__ import annotations

from typing import Any

_COMMITMENT_KEYWORDS = ("committed", "limited availability", "not available", "on hold")
_SENIORITY_KEYS = {
    "junior": "junior_0_2_yrs",
    "mid": "mid_2_4_yrs",
    "senior": "senior_4_plus_yrs",
}


def check_capacity(
    bench: dict[str, Any],
    *,
    stack: str,
    requested_count: int,
    seniority: str | None = None,
    lead_days: int | None = None,
) -> dict[str, Any]:
    """Return capacity feasibility for a given stack request.

    Returns a dict with keys:
      feasible: bool
      reason: str
      available: int           (total available engineers)
      available_seniority: int (available at requested seniority, or -1 if not checked)
    """
    stacks = bench.get("stacks") or {}
    stack_key = stack.strip().lower()
    stack_data = stacks.get(stack_key)
    if stack_data is None:
        return {
            "feasible": False,
            "reason": f"Stack '{stack}' is not present in the bench.",
            "available": 0,
            "available_seniority": -1,
        }
    available = int(stack_data.get("available_engineers") or 0)
    note = str(stack_data.get("note") or "").lower()
    time_to_deploy = int(stack_data.get("time_to_deploy_days") or 0)

    # Check commitment note first (P-010)
    if any(kw in note for kw in _COMMITMENT_KEYWORDS):
        return {
            "feasible": False,
            "reason": f"Stack '{stack}' has a commitment note: {stack_data.get('note', '')!r}",
            "available": available,
            "available_seniority": -1,
        }

    # Check count (P-009)
    if available < requested_count:
        return {
            "feasible": False,
            "reason": (
                f"Stack '{stack}' has {available} available engineers, "
                f"but {requested_count} were requested."
            ),
            "available": available,
            "available_seniority": -1,
        }

    # Check seniority (P-011)
    if seniority:
        seniority_key = _SENIORITY_KEYS.get(seniority.lower())
        if seniority_key is None:
            return {
                "feasible": False,
                "reason": (
                    f"Seniority level '{seniority}' is not recognised. "
                    f"Known levels: {list(_SENIORITY_KEYS)}."
                ),
                "available": available,
                "available_seniority": -1,
            }
        seniority_mix = stack_data.get("seniority_mix") or {}
        avail_seniority = int(seniority_mix.get(seniority_key) or 0)
        if avail_seniority < requested_count:
            return {
                "feasible": False,
                "reason": (
                    f"Stack '{stack}' has {avail_seniority} {seniority} engineers, "
                    f"but {requested_count} were requested."
                ),
                "available": available,
                "available_seniority": avail_seniority,
            }

    # Check lead time (P-012)
    if lead_days is not None and time_to_deploy > lead_days:
        return {
            "feasible": False,
            "reason": (
                f"Stack '{stack}' requires {time_to_deploy} days to deploy, "
                f"but only {lead_days} days were requested."
            ),
            "available": available,
            "available_seniority": -1,
        }

    return {
        "feasible": True,
        "reason": f"Stack '{stack}' has {available} engineers available.",
        "available": available,
        "available_seniority": -1,
    }
