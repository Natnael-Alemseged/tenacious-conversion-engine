from agent.core.config import settings  # noqa: F401


def lookup(company_name: str) -> dict | None:
    # TODO: search crunchbase_odm_path JSON for company_name
    return None


def recent_funding(company_name: str, days: int = 180) -> list[dict]:
    # TODO: filter funding_rounds from lookup() by date
    return []
