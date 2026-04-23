from __future__ import annotations

import json
from pathlib import Path


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def extract_keywords(summary: dict) -> set[str]:
    raw = summary.get("keywords") or summary.get("focus_areas") or summary.get("capabilities") or []
    if not isinstance(raw, list):
        return set()
    return {str(x).strip().lower() for x in raw if str(x).strip()}
