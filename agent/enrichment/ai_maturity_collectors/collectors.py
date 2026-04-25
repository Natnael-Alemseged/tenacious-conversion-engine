from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from agent.enrichment.ai_maturity_collectors.fetch import fetch_text


@dataclass(frozen=True)
class EvidenceItem:
    signal: str
    source_url: str
    fetched_at: str
    snippet: str


def _domain_root(domain: str) -> str:
    host = (domain or "").strip().lower()
    if not host:
        return ""
    host = host.split("/", 1)[0]
    host = host.split(":", 1)[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


_AI_KEYWORDS = re.compile(r"\b(ai|artificial intelligence|machine learning|ml|llm)\b", re.I)
_STACK_KEYWORDS = re.compile(r"\b(dbt|snowflake|databricks|ray|vllm|mlops)\b", re.I)


def collect_github_activity(
    *,
    company_domain: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    root = _domain_root(company_domain)
    if not root:
        return {}, []
    org = root.replace("-", "").replace("_", "")
    org_url = f"https://github.com/{org}"
    repo_search_url = f"https://github.com/{org}?tab=repositories&q=ml&type=&language="

    evidence: list[EvidenceItem] = []
    org_page = fetch_text(org_url, transport=transport)
    if not org_page.ok:
        return {"github_activity": False}, []

    search_page = fetch_text(repo_search_url, transport=transport)
    if search_page.ok and ("repo-list" in search_page.text or "Repositories" in search_page.text):
        # Heuristic: if search page contains any AI/ML keyword, count as activity.
        if _AI_KEYWORDS.search(search_page.text):
            evidence.append(
                EvidenceItem(
                    signal="github_activity",
                    source_url=repo_search_url,
                    fetched_at=search_page.fetched_at,
                    snippet=(
                        "Found AI/ML-related repository search results on public GitHub org page."
                    ),
                )
            )
            return {"github_activity": True, "github_fork_only": False}, evidence

    return {"github_activity": False}, evidence


def collect_exec_commentary(
    *,
    company_domain: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    root = (company_domain or "").strip()
    if not root:
        return {}, []
    candidates = [
        f"https://{root}/blog",
        f"https://{root}/news",
        f"https://{root}/press",
        f"https://{root}/insights",
    ]
    for url in candidates:
        page = fetch_text(url, transport=transport)
        if not page.ok:
            continue
        match = _AI_KEYWORDS.search(page.text)
        if match:
            start = max(0, match.start() - 80)
            end = min(len(page.text), match.end() + 120)
            snippet = re.sub(r"\s+", " ", page.text[start:end]).strip()
            return (
                {"exec_commentary": True},
                [
                    EvidenceItem(
                        signal="exec_commentary",
                        source_url=url,
                        fetched_at=page.fetched_at,
                        snippet=snippet[:240],
                    )
                ],
            )
    return {"exec_commentary": False}, []


def collect_strategic_comms(
    *,
    company_domain: str,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    root = (company_domain or "").strip()
    if not root:
        return {}, []
    candidates = [
        f"https://{root}/investors",
        f"https://{root}/about",
        f"https://{root}/company",
        f"https://{root}/press",
    ]
    for url in candidates:
        page = fetch_text(url, transport=transport)
        if not page.ok:
            continue
        if re.search(r"\b(ai-first|ai strategy|ai roadmap|ai-powered)\b", page.text, re.I):
            return (
                {"strategic_comms": True},
                [
                    EvidenceItem(
                        signal="strategic_comms",
                        source_url=url,
                        fetched_at=page.fetched_at,
                        snippet="Public comms page references AI strategy/prioritization.",
                    )
                ],
            )
    return {"strategic_comms": False}, []


def collect_modern_ml_stack(
    *,
    tech_stack: list[str],
    job_role_titles: list[str],
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    haystack = " ".join([*(tech_stack or []), *(job_role_titles or [])])
    if _STACK_KEYWORDS.search(haystack):
        return (
            {"modern_ml_stack": True},
            [
                EvidenceItem(
                    signal="modern_ml_stack",
                    source_url="",
                    fetched_at="",
                    snippet=(
                        "Detected modern data/ML stack keywords in inferred tech stack "
                        "or job titles."
                    ),
                )
            ],
        )
    return {"modern_ml_stack": False}, []


def collect_all_ai_maturity_signals(
    *,
    company_domain: str,
    tech_stack: list[str],
    job_role_titles: list[str],
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]], float]:
    signals: dict[str, Any] = {}
    evidence: list[EvidenceItem] = []

    github_signals, github_ev = collect_github_activity(
        company_domain=company_domain, transport=transport
    )
    signals.update(github_signals)
    evidence.extend(github_ev)

    comm_signals, comm_ev = collect_exec_commentary(
        company_domain=company_domain, transport=transport
    )
    signals.update(comm_signals)
    evidence.extend(comm_ev)

    strat_signals, strat_ev = collect_strategic_comms(
        company_domain=company_domain, transport=transport
    )
    signals.update(strat_signals)
    evidence.extend(strat_ev)

    stack_signals, stack_ev = collect_modern_ml_stack(
        tech_stack=tech_stack, job_role_titles=job_role_titles
    )
    signals.update(stack_signals)
    evidence.extend(stack_ev)

    evidence_payload = [
        {
            "signal": item.signal,
            "source_url": item.source_url,
            "fetched_at": item.fetched_at,
            "snippet": item.snippet,
        }
        for item in evidence
    ]
    strength = min(1.0, len(evidence_payload) / 4.0)
    return signals, evidence_payload, round(strength, 3)
