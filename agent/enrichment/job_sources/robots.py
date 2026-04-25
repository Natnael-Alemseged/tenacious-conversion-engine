from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


def can_fetch(*, url: str, user_agent: str = "*") -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser(robots_url)
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(robots_url)
            rp.parse(resp.text.splitlines())
    except Exception:
        # If robots.txt cannot be fetched, default to allow (common for small sites),
        # but callers still must stay on public pages and avoid login/captcha bypass.
        return True
    return bool(rp.can_fetch(user_agent, url))
