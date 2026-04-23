from __future__ import annotations

import json
from pathlib import Path

from agent.core.config import settings


def _load_odm() -> list[dict]:
    path = Path(settings.crunchbase_odm_path)
    if not path.exists():
        return []
    with path.open() as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("companies", [])


def _name_match(record: dict, company_name: str) -> bool:
    name = (record.get("name") or record.get("company_name") or "").lower()
    return company_name.lower() in name or name in company_name.lower()


def lookup(company_name: str) -> dict | None:
    for record in _load_odm():
        if _name_match(record, company_name):
            return record
    return None


def recent_funding(company_name: str, days: int = 180) -> list[dict]:
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)
    record = lookup(company_name)
    if not record:
        return []

    rounds: list[dict] = record.get("funding_rounds", []) or []
    result = []
    for r in rounds:
        announced = r.get("announced_on") or r.get("date") or ""
        try:
            dt = datetime.fromisoformat(announced.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            if dt >= cutoff:
                result.append(r)
        except (ValueError, AttributeError):
            pass
    return result


def leadership_changes(company_name: str, days: int = 90) -> list[dict]:
    """Return people with CTO/VP Eng/Head of AI titles who joined within `days`."""
    from datetime import UTC, datetime, timedelta

    LEADERSHIP_KEYWORDS = {
        "cto",
        "vp eng",
        "vp of eng",
        "chief technology",
        "head of ai",
        "chief ai",
    }
    cutoff = datetime.now(UTC) - timedelta(days=days)
    record = lookup(company_name)
    if not record:
        return []

    people: list[dict] = record.get("people", []) or record.get("founders", []) or []
    changes = []
    for person in people:
        title = (person.get("title") or person.get("job_title") or "").lower()
        if not any(kw in title for kw in LEADERSHIP_KEYWORDS):
            continue
        started = person.get("started_on") or person.get("start_date") or ""
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            if dt >= cutoff:
                changes.append({"name": person.get("name"), "title": title, "started_on": started})
        except (ValueError, AttributeError):
            pass
    return changes
