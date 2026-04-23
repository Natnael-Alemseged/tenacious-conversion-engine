from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent.core.config import settings

# layoffs.fyi CSV columns vary across exports; try both known schema variants.
_COMPANY_COLS = ("Company", "company", "company_name")
_DATE_COLS = ("Date", "date", "Date Added", "date_added", "Announced Date")
_COUNT_COLS = ("Laid_Off_Count", "laid_off_count", "Total Laid Off", "# Laid Off")
_PCT_COLS = ("Percentage", "percentage", "Percentage", "% Laid Off")


def _col(row: dict, candidates: tuple[str, ...]) -> str:
    for c in candidates:
        if c in row:
            return row[c] or ""
    return ""


def check(company_name: str, days: int = 120) -> list[dict]:
    path = Path(settings.layoffs_fyi_path)
    if not path.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(days=days)
    matches: list[dict] = []

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = _col(row, _COMPANY_COLS).lower()
            if company_name.lower() not in name and name not in company_name.lower():
                continue
            date_str = _col(row, _DATE_COLS)
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
            except (ValueError, AttributeError):
                dt = None

            if dt is None or dt >= cutoff:
                matches.append(
                    {
                        "company": _col(row, _COMPANY_COLS),
                        "date": date_str,
                        "laid_off_count": _col(row, _COUNT_COLS),
                        "percentage": _col(row, _PCT_COLS),
                    }
                )
    return matches
