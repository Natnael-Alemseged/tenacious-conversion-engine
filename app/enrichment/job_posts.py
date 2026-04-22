def scrape(careers_url: str) -> dict:
    # TODO: Playwright headless fetch of careers_url, count engineering roles
    # Respect robots.txt; no login, no captcha bypass
    return {"url": careers_url, "open_roles": 0, "ai_adjacent_roles": 0}
