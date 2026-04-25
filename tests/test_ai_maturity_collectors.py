from __future__ import annotations

import httpx

from agent.enrichment.ai_maturity_collectors.collectors import collect_exec_commentary


def test_exec_commentary_collector_detects_ai_keyword_with_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/blog"):
            return httpx.Response(
                200, text="Our CEO writes about Artificial Intelligence strategy."
            )
        return httpx.Response(404, text="nope")

    transport = httpx.MockTransport(handler)
    signals, evidence = collect_exec_commentary(company_domain="example.com", transport=transport)
    assert signals["exec_commentary"] is True
    assert evidence and evidence[0].signal == "exec_commentary"
