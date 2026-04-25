from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AutoResponderResult:
    is_autoresponder: bool
    matched_on: str
    matched_pattern: str


DEFAULT_HEURISTICS_PATH = Path(__file__).with_name("autoresponder_heuristics.json")


def load_heuristics(path: Path | str | None = None) -> dict:
    p = Path(path) if path is not None else DEFAULT_HEURISTICS_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def classify_autoresponder(*, subject: str, body: str, heuristics: dict) -> AutoResponderResult:
    subject = subject or ""
    body = body or ""
    for pattern in heuristics.get("subject_regexes", []):
        if re.search(pattern, subject) is not None:
            return AutoResponderResult(True, "subject", pattern)
    for pattern in heuristics.get("body_regexes", []):
        if re.search(pattern, body) is not None:
            return AutoResponderResult(True, "body", pattern)
    return AutoResponderResult(False, "", "")
