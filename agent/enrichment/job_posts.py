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


def scrape(careers_url: str) -> dict:
    """Fetch public careers page via Playwright and count engineering/AI roles.

    Respects robots.txt via a pre-check. No login logic. No captcha bypass.
    Falls back to an empty result if Playwright is not installed or the page
    is unreachable, so the rest of the pipeline can still run.
    """
    try:
        return _scrape_with_playwright(careers_url)
    except Exception:
        return {
            "url": careers_url,
            "open_roles": 0,
            "ai_adjacent_roles": 0,
            "error": "playwright_unavailable_or_fetch_failed",
        }


def _scrape_with_playwright(careers_url: str) -> dict:
    from urllib.parse import urlparse
    from urllib.robotparser import RobotFileParser

    import httpx
    from playwright.sync_api import sync_playwright

    parsed = urlparse(careers_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser(robots_url)
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(robots_url)
            rp.parse(resp.text.splitlines())
    except Exception:
        pass

    if not rp.can_fetch("*", careers_url):
        return {
            "url": careers_url,
            "open_roles": 0,
            "ai_adjacent_roles": 0,
            "error": "robots_disallowed",
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "ConversionEngine-signal-crawler/1.0"})
        page.goto(careers_url, timeout=15000, wait_until="domcontentloaded")
        text = page.inner_text("body")
        browser.close()

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    open_roles = sum(1 for ln in lines if ENG_ROLE_PATTERNS.search(ln))
    ai_adjacent = sum(1 for ln in lines if AI_ROLE_PATTERNS.search(ln))

    return {
        "url": careers_url,
        "open_roles": open_roles,
        "ai_adjacent_roles": ai_adjacent,
        "ai_roles_fraction": round(ai_adjacent / open_roles, 3) if open_roles else 0.0,
    }
