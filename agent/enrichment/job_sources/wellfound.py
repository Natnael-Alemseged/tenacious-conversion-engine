from __future__ import annotations

from datetime import UTC, datetime

from agent.enrichment.job_sources.generic import scrape as _scrape_generic


def scrape(url: str) -> dict:
    """Wellfound job page scrape (public pages only; no login/captcha bypass)."""
    recorded_at = datetime.now(UTC).isoformat()
    base = _scrape_generic(url)
    base["source"] = "wellfound"
    base["recorded_at"] = recorded_at
    return base
