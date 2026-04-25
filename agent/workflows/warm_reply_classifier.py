from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from agent.integrations.openrouter_llm import OpenRouterClient

WarmReplyClass = Literal["engaged", "curious", "hard_no", "soft_defer", "objection", "unknown"]


@dataclass(frozen=True)
class WarmReplyClassResult:
    reply_class: WarmReplyClass
    confidence: float
    abstained: bool = False
    notes: str = ""


_SYSTEM = """You are classifying an inbound prospect reply to a cold outbound email.
Return ONLY valid JSON with keys: reply_class, confidence, abstained, notes.

reply_class must be one of:
- engaged: substantive response with a specific question or context.
- curious: "tell me more" / "what do you do" / "send details".
- hard_no: "not interested" / "remove" / "stop emailing" / "unsubscribe".
- soft_defer: "not now" / "reach out in Q3" / "too busy" / "later".
- objection: price / offshore / India / incumbent vendor / already have a team.
- unknown: none of the above.

abstained: true if the class is ambiguous; ambiguous replies route to a human.
confidence: 0.0 to 1.0
notes: short string, optional
"""


def _safe_parse_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
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


def _heuristic_classify(subject: str, body: str) -> WarmReplyClassResult:
    text = f"{subject}\n{body}".lower()
    text = re.sub(r"\s+", " ", text).strip()

    hard_no = (
        "not interested",
        "no thanks",
        "stop emailing",
        "unsubscribe",
        "remove me",
        "remove us",
        "please remove",
        "take me off",
        "do not contact",
    )
    if any(p in text for p in hard_no):
        return WarmReplyClassResult("hard_no", 0.9, abstained=False, notes="heuristic_hard_no")

    soft_defer = (
        "not right now",
        "not now",
        "reach out",
        "q3",
        "next quarter",
        "too busy",
        "later",
    )
    if any(p in text for p in soft_defer):
        return WarmReplyClassResult(
            "soft_defer", 0.7, abstained=False, notes="heuristic_soft_defer"
        )

    objection = (
        "price",
        "pricing",
        "cost",
        "india",
        "offshore",
        "vendor",
        "already have",
        "incumbent",
    )
    if any(p in text for p in objection):
        return WarmReplyClassResult("objection", 0.7, abstained=False, notes="heuristic_objection")

    curious = (
        "tell me more",
        "learn more",
        "what do you do",
        "send details",
        "more info",
        "details?",
    )
    if any(p in text for p in curious) or (len(text) < 180 and "?" in text):
        return WarmReplyClassResult("curious", 0.6, abstained=False, notes="heuristic_curious")

    # Engaged: longer reply with question or context.
    if len(text) >= 180 or ("?" in text and len(text) >= 60):
        return WarmReplyClassResult("engaged", 0.6, abstained=False, notes="heuristic_engaged")

    # Ambiguous.
    return WarmReplyClassResult("unknown", 0.2, abstained=True, notes="heuristic_abstain")


def classify_warm_reply(
    *, subject: str, body: str, client: OpenRouterClient | None = None
) -> WarmReplyClassResult:
    """Classify warm reply type with safe fallback.

    Uses an LLM when available, but never fails open: falls back to heuristics and may abstain.
    """
    text = f"SUBJECT:\n{subject}\n\nBODY:\n{body}".strip()
    llm = client or OpenRouterClient()
    try:
        content = llm.generate_text(
            system_prompt=_SYSTEM,
            user_prompt=text,
            temperature=0.0,
            max_tokens=120,
            metadata={"task": "warm_reply_class"},
        )
        payload = _safe_parse_json(content) or {}
        label = str(payload.get("reply_class") or "").strip()
        abstained = bool(payload.get("abstained") or False)
        try:
            conf = float(payload.get("confidence") or 0.0)
        except Exception:
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        notes = str(payload.get("notes") or "")[:200]
        if label not in ("engaged", "curious", "hard_no", "soft_defer", "objection", "unknown"):
            return _heuristic_classify(subject, body)
        # If the model says "unknown" but doesn't abstain, treat as abstained.
        if label == "unknown" and not abstained:
            abstained = True
        return WarmReplyClassResult(label, conf, abstained=abstained, notes=notes)
    except Exception:
        return _heuristic_classify(subject, body)
