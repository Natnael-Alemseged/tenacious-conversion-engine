from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from agent.enrichment.job_sources.robots import can_fetch


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    url: str
    fetched_at: str
    status_code: int
    text: str
    error: str


def fetch_text(
    url: str, *, timeout_s: float = 8.0, transport: httpx.BaseTransport | None = None
) -> FetchResult:
    fetched_at = datetime.now(UTC).isoformat()
    if not can_fetch(url=url):
        return FetchResult(
            ok=False,
            url=url,
            fetched_at=fetched_at,
            status_code=0,
            text="",
            error="robots_disallowed",
        )
    try:
        client = httpx.Client(
            timeout=timeout_s,
            follow_redirects=True,
            headers={"User-Agent": "ConversionEngine-signal-crawler/1.0"},
            transport=transport,
        )
        with client:
            r = client.get(url)
            status = r.status_code
            if status >= 400:
                return FetchResult(
                    ok=False,
                    url=url,
                    fetched_at=fetched_at,
                    status_code=status,
                    text="",
                    error="http_error",
                )
            return FetchResult(
                ok=True,
                url=url,
                fetched_at=fetched_at,
                status_code=status,
                text=r.text or "",
                error="",
            )
    except Exception:
        return FetchResult(
            ok=False,
            url=url,
            fetched_at=fetched_at,
            status_code=0,
            text="",
            error="request_failed",
        )
