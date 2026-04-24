from __future__ import annotations

import json
from pathlib import Path

from agent.enrichment.pipeline import run
from agent.enrichment.public_briefs import to_public_hiring_signal_brief
from agent.enrichment.schemas import HiringSignalBrief


def write_hiring_signal_brief(
    *,
    company_name: str,
    careers_url: str = "",
    path: str = "artifacts/hiring_signal_brief.json",
) -> HiringSignalBrief:
    result = run(company_name=company_name, careers_url=careers_url)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(to_public_hiring_signal_brief(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
