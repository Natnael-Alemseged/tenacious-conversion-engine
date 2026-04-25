from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from agent.integrations.openrouter_llm import OpenRouterClient

ReplyIntent = Literal[
    "request_brief",
    "request_scheduling",
    "request_booking",
    "provide_requirements",
    "other",
]


@dataclass(frozen=True)
class ReplyIntentResult:
    intent: ReplyIntent
    confidence: float
    notes: str = ""


_SYSTEM = """You are classifying an inbound prospect email reply for a B2B sales automation system.
Return ONLY valid JSON with keys: intent, confidence, notes.

intents:
- request_brief: asks for the qualification brief / what we found / the writeup / summary.
- request_scheduling: asks for times/options/link to schedule, but does not commit to a
  specific time.
- request_booking: asks to book AND provides a specific proposed time (ISO timestamp may
  be present).
- provide_requirements: provides role counts, seniority, timezone overlap, start date, or
  similar requirements.
- other: anything else.

confidence: 0.0 to 1.0
notes: short string, optional
"""


def _safe_parse_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # Model sometimes wraps JSON in fences; try to recover.
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def classify_reply_intent(
    *, subject: str, body: str, client: OpenRouterClient | None = None
) -> ReplyIntentResult:
    """
    LLM-backed intent classification with safe fallback.
    If the LLM is unavailable or returns malformed output, fall back to 'other'.
    """
    text = f"SUBJECT:\n{subject}\n\nBODY:\n{body}".strip()
    llm = client or OpenRouterClient()
    try:
        content = llm.generate_text(
            system_prompt=_SYSTEM,
            user_prompt=text,
            temperature=0.0,
            max_tokens=120,
            metadata={"task": "reply_intent"},
        )
        payload = _safe_parse_json(content) or {}
        intent = payload.get("intent")
        confidence = payload.get("confidence")
        notes = str(payload.get("notes") or "")[:200]
        if intent not in (
            "request_brief",
            "request_scheduling",
            "request_booking",
            "provide_requirements",
            "other",
        ):
            return ReplyIntentResult(intent="other", confidence=0.0, notes="invalid_intent")
        try:
            conf_f = float(confidence)
        except Exception:
            conf_f = 0.0
        conf_f = max(0.0, min(1.0, conf_f))
        return ReplyIntentResult(intent=intent, confidence=conf_f, notes=notes)
    except Exception:
        return ReplyIntentResult(intent="other", confidence=0.0, notes="llm_unavailable")
