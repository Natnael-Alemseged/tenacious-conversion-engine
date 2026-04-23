from __future__ import annotations

# Weights from challenge spec: High=3, Medium=2, Low=1
_WEIGHTS: dict[str, int] = {
    "ai_roles_fraction": 3,
    "named_ai_leadership": 3,
    "github_activity": 2,
    "exec_commentary": 2,
    "modern_ml_stack": 1,
    "strategic_comms": 1,
}
_MAX_WEIGHT = sum(_WEIGHTS.values())  # 12


def confidence_phrasing(confidence: float) -> str:
    """Map a confidence score to a phrasing style for outreach copy.

    Returns one of 'direct', 'hedged', or 'exploratory'.
    """
    if confidence >= 0.8:
        return "direct"
    if confidence >= 0.5:
        return "hedged"
    return "exploratory"


def score(signals: dict) -> tuple[int, str, float]:
    """Return (0-3 score, justification, confidence 0-1).

    signals keys and expected value types:
      ai_roles_fraction: float 0-1  (AI-adjacent roles / total engineering roles)
      named_ai_leadership: bool     (Head of AI / VP Data / Chief Scientist present)
      github_activity: bool         (recent AI/ML commits in public org)
      exec_commentary: bool         (CEO/CTO AI commentary in last 12 months)
      modern_ml_stack: bool         (dbt/Snowflake/Ray/vLLM signals)
      strategic_comms: bool         (fundraising/IR docs name AI as priority)
    """
    if not signals:
        return 0, "no signals provided", 0.0

    weighted_score = 0.0
    signals_present = 0
    notes: list[str] = []

    ai_frac = signals.get("ai_roles_fraction", 0.0) or 0.0
    if ai_frac >= 0.3:
        weighted_score += _WEIGHTS["ai_roles_fraction"]
        notes.append(f"AI role fraction {ai_frac:.0%} (high)")
    elif ai_frac >= 0.1:
        weighted_score += _WEIGHTS["ai_roles_fraction"] * 0.5
        notes.append(f"AI role fraction {ai_frac:.0%} (moderate)")
    if "ai_roles_fraction" in signals:
        signals_present += 1

    for key in (
        "named_ai_leadership",
        "github_activity",
        "exec_commentary",
        "modern_ml_stack",
        "strategic_comms",
    ):
        val = signals.get(key)
        if val is True:
            weighted_score += _WEIGHTS[key]
            notes.append(key.replace("_", " "))
            signals_present += 1

    confidence = signals_present / len(_WEIGHTS)
    normalized = weighted_score / _MAX_WEIGHT
    raw_score = int(normalized * 3 + 0.5)
    final_score = max(0, min(3, raw_score))
    justification = (
        f"Score {final_score}/3 from {signals_present}/{len(_WEIGHTS)} signal inputs. "
        + (f"Active signals: {', '.join(notes)}." if notes else "No active signals.")
    )
    return final_score, justification, round(confidence, 3)
