from __future__ import annotations

from datetime import UTC, datetime

from agent.enrichment.job_sources.parsing import extract_role_lines
from agent.enrichment.job_sources.robots import can_fetch


def scrape(url: str) -> dict:
    """Generic public-page scrape via Playwright (best-effort)."""
    recorded_at = datetime.now(UTC).isoformat()
    if not can_fetch(url=url):
        return {
            "url": url,
            "source": "generic",
            "recorded_at": recorded_at,
            "open_roles": 0,
            "ai_adjacent_roles": 0,
            "ai_roles_fraction": 0.0,
            "role_titles": [],
            "error": "robots_disallowed",
        }

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {
            "url": url,
            "source": "generic",
            "recorded_at": recorded_at,
            "open_roles": 0,
            "ai_adjacent_roles": 0,
            "ai_roles_fraction": 0.0,
            "role_titles": [],
            "error": "playwright_unavailable",
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "ConversionEngine-signal-crawler/1.0"})
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            text = page.inner_text("body")
            browser.close()
    except Exception:
        return {
            "url": url,
            "source": "generic",
            "recorded_at": recorded_at,
            "open_roles": 0,
            "ai_adjacent_roles": 0,
            "ai_roles_fraction": 0.0,
            "role_titles": [],
            "error": "fetch_failed",
        }

    open_roles, ai_adjacent, role_titles, ai_fraction = extract_role_lines(text)
    return {
        "url": url,
        "source": "generic",
        "recorded_at": recorded_at,
        "open_roles": open_roles,
        "ai_adjacent_roles": ai_adjacent,
        "ai_roles_fraction": ai_fraction,
        "role_titles": role_titles,
    }
