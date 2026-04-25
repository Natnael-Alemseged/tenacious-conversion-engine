from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent.core.config import settings

# layoffs.fyi CSV columns vary across exports; try both known schema variants.
_COMPANY_COLS = ("Company", "company", "company_name")
_DATE_COLS = ("Date", "date", "Date Added", "date_added", "Announced Date")
_COUNT_COLS = ("Laid_Off_Count", "laid_off_count", "Total Laid Off", "# Laid Off")
_PCT_COLS = ("Percentage", "percentage", "% Laid Off")

_EMP_ENUM_MIDPOINTS: dict[str, int] = {
    "c_00001_00010": 5,
    "c_00011_00050": 30,
    "c_00051_00100": 75,
    "c_00101_00250": 175,
    "c_00251_00500": 375,
    "c_00501_01000": 750,
    "c_01001_05000": 3000,
    "c_05001_10000": 7500,
    "c_10001_": 10000,
}


def _col(row: dict, candidates: tuple[str, ...]) -> str:
    for c in candidates:
        if c in row:
            return row[c] or ""
    return ""


def _approximate_headcount(employee_count_enum: str | None) -> int | None:
    if not employee_count_enum:
        return None
    return _EMP_ENUM_MIDPOINTS.get(str(employee_count_enum).strip())


def _resolve_percentage(
    *,
    raw_pct: str,
    raw_count: str,
    headcount: int | None,
) -> tuple[str, str]:
    """Return (percentage_str, source) where source is 'reported' or 'computed'."""
    cleaned = raw_pct.strip().lower()
    if cleaned and cleaned not in ("null", "none", "n/a", "—", "-"):
        return raw_pct, "reported"
    if headcount and raw_count:
        try:
            count = int(raw_count)
            pct = round(count / headcount * 100, 1)
            return str(pct), "computed"
        except (ValueError, ZeroDivisionError):
            pass
    return raw_pct, "reported"


def check(
    company_name: str,
    days: int = 120,
    *,
    path: str | None = None,
    employee_count_enum: str | None = None,
) -> list[dict]:
    resolved = Path(path) if path else Path(settings.layoffs_fyi_path)
    if not resolved.exists():
        return []

    headcount = _approximate_headcount(employee_count_enum)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    matches: list[dict] = []

    with resolved.open(newline="", encoding="utf-8-sig") as f:
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
                raw_pct = _col(row, _PCT_COLS)
                raw_count = _col(row, _COUNT_COLS)
                pct, pct_source = _resolve_percentage(
                    raw_pct=raw_pct,
                    raw_count=raw_count,
                    headcount=headcount,
                )
                matches.append(
                    {
                        "company": _col(row, _COMPANY_COLS),
                        "date": date_str,
                        "laid_off_count": raw_count,
                        "percentage": pct,
                        "percentage_source": pct_source,
                    }
                )
    return matches
