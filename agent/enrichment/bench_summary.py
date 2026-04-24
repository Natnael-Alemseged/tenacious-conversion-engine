from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
    stacks = summary.get("stacks")
    if isinstance(stacks, dict):
        words: set[str] = set()
        for stack_name, payload in stacks.items():
            words.add(str(stack_name).strip().lower())
            if isinstance(payload, dict):
                for item in payload.get("skill_subsets", []) or []:
                    value = str(item).strip().lower()
                    if value:
                        words.add(value)
        return words

    raw = summary.get("keywords") or summary.get("focus_areas") or summary.get("capabilities") or []
    if not isinstance(raw, list):
        return set()
    return {str(x).strip().lower() for x in raw if str(x).strip()}


def available_stack_counts(summary: dict) -> dict[str, int]:
    stacks = summary.get("stacks")
    if not isinstance(stacks, dict):
        return {}
    counts: dict[str, int] = {}
    for stack_name, payload in stacks.items():
        if not isinstance(payload, dict):
            continue
        try:
            counts[str(stack_name).strip().lower()] = int(payload.get("available_engineers") or 0)
        except (TypeError, ValueError):
            counts[str(stack_name).strip().lower()] = 0
    return counts


def stack_skill_map(summary: dict) -> dict[str, set[str]]:
    stacks = summary.get("stacks")
    if not isinstance(stacks, dict):
        return {}
    mapped: dict[str, set[str]] = {}
    for stack_name, payload in stacks.items():
        if not isinstance(payload, dict):
            continue
        key = str(stack_name).strip().lower()
        skills = {key}
        for item in payload.get("skill_subsets", []) or []:
            value = str(item).strip().lower()
            if value:
                skills.add(value)
        mapped[key] = skills
    return mapped


def infer_required_stacks(
    summary: dict,
    *,
    tech_stack: list[str],
    role_titles: list[str],
    categories: list[str],
    ai_score: int = 0,
) -> list[str]:
    haystack_parts = [*tech_stack, *role_titles, *categories]
    haystack = " ".join(str(part).lower() for part in haystack_parts if part).strip()
    if not haystack:
        return ["ml"] if ai_score >= 2 and "ml" in available_stack_counts(summary) else []

    required: list[str] = []
    skill_map = stack_skill_map(summary)
    for stack_name, keywords in skill_map.items():
        if any(keyword and keyword in haystack for keyword in keywords):
            required.append(stack_name)

    if ai_score >= 2 and "ml" in skill_map and "ml" not in required:
        required.append("ml")

    return sorted(set(required))


def bench_match(
    summary: dict,
    *,
    required_stacks: list[str],
) -> dict[str, Any]:
    counts = available_stack_counts(summary)
    unique_required = sorted({stack.strip().lower() for stack in required_stacks if stack.strip()})
    gaps = [stack for stack in unique_required if counts.get(stack, 0) <= 0]
    available = {stack: counts.get(stack, 0) for stack in unique_required}
    return {
        "required_stacks": unique_required,
        "bench_available": not gaps,
        "gaps": gaps,
        "available_counts": available,
    }
