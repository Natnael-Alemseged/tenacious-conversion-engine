from agent.enrichment import ai_maturity, crunchbase, job_posts, layoffs


def run(company_name: str, careers_url: str = "") -> dict:
    """
    Returns hiring_signal_brief dict ready to inject into LLM context.
    Merges: Crunchbase firmographics, funding, layoffs, job posts, AI maturity.
    """
    cb = crunchbase.lookup(company_name) or {}
    funding = crunchbase.recent_funding(company_name)
    layoff_events = layoffs.check(company_name)
    jobs = job_posts.scrape(careers_url) if careers_url else {}
    ai_score, ai_justification = ai_maturity.score({})

    # TODO: classify into ICP segment (1-4) based on signals
    return {
        "company_name": company_name,
        "crunchbase_id": cb.get("uuid"),
        "employee_count": cb.get("num_employees_enum"),
        "recent_funding": funding,
        "recent_layoffs": layoff_events,
        "job_posts": jobs,
        "ai_maturity_score": ai_score,
        "ai_maturity_justification": ai_justification,
        "icp_segment": None,
        "confidence": 0.0,
    }
