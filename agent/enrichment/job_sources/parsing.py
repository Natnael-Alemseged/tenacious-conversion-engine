from __future__ import annotations

import re

AI_ROLE_PATTERNS = re.compile(
    r"\b(ml|machine learning|ai|llm|applied scientist|nlp|computer vision"
    r"|data (scientist|engineer|platform)|model|inference|mle)\b",
    re.IGNORECASE,
)
ENG_ROLE_PATTERNS = re.compile(
    r"\b(engineer|developer|architect|sre|devops|backend|frontend|fullstack|platform)\b",
    re.IGNORECASE,
)


def extract_role_lines(text: str, *, max_titles: int = 25) -> tuple[int, int, list[str], float]:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    open_roles = sum(1 for ln in lines if ENG_ROLE_PATTERNS.search(ln))
    ai_adjacent = sum(1 for ln in lines if AI_ROLE_PATTERNS.search(ln))

    role_titles: list[str] = []
    seen: set[str] = set()
    for ln in lines:
        if not ENG_ROLE_PATTERNS.search(ln):
            continue
        title = re.sub(r"\s+", " ", ln).strip()
        if len(title) > 90:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        role_titles.append(title)
        if len(role_titles) >= max_titles:
            break

    ai_fraction = round(ai_adjacent / open_roles, 3) if open_roles else 0.0
    return open_roles, ai_adjacent, role_titles, ai_fraction
