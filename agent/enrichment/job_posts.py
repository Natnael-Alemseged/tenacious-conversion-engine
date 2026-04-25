from __future__ import annotations

from urllib.parse import urlparse

from agent.enrichment.job_sources import builtin, generic, linkedin, wellfound


def scrape(careers_url: str) -> dict:
    """Fetch a public jobs page and count engineering/AI roles.

    Respects robots.txt via a pre-check. No login logic. No captcha bypass.
    Uses source-specific modules for BuiltIn/Wellfound/LinkedIn, and a
    generic public-page scraper for everything else.
    """
    parsed = urlparse(careers_url)
    host = (parsed.netloc or "").lower()
    if "builtin" in host:
        return builtin.scrape(careers_url)
    if "wellfound" in host or "angel.co" in host:
        return wellfound.scrape(careers_url)
    if "linkedin" in host:
        return linkedin.scrape(careers_url)
    return generic.scrape(careers_url)
