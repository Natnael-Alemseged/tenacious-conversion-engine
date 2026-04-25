from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConfidenceTier = Literal["high", "medium", "low", "none"]


def tier_from_score(score: float) -> ConfidenceTier:
    if score >= 0.75:
        return "high"
    if score >= 0.35:
        return "medium"
    if score > 0.0:
        return "low"
    return "none"


class ConfidenceMeta(BaseModel):
    """Granular confidence: tier plus optional factor contributions (0–1 each)."""

    model_config = ConfigDict(frozen=True)

    tier: ConfidenceTier
    factors: dict[str, float] = Field(default_factory=dict)
    rationale_codes: tuple[str, ...] = Field(default_factory=tuple)


class CrunchbaseBriefData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uuid: str | None = None
    employee_count: Any = None
    country: str | None = None
    categories: list[str] = Field(default_factory=list)


class BenchSignalData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keywords: list[str] = Field(default_factory=list)
    hits: list[str] = Field(default_factory=list)
    bench_to_brief_gate_passed: bool = False
    required_stacks: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    available_counts: dict[str, int] = Field(default_factory=dict)


class AiMaturitySignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int = 0
    justification: str = ""
    confidence: float = Field(0.0, ge=0, le=1)
    confidence_meta: ConfidenceMeta | None = None
    evidence_strength: float = Field(0.0, ge=0, le=1)
    evidence: list[dict[str, str]] = Field(default_factory=list)


class CrunchbaseSignal(BaseModel):
    data: CrunchbaseBriefData
    confidence: float = Field(ge=0, le=1)
    confidence_meta: ConfidenceMeta


class FundingSignal(BaseModel):
    data: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    confidence_meta: ConfidenceMeta


class LayoffsSignal(BaseModel):
    data: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    confidence_meta: ConfidenceMeta


class LeadershipSignal(BaseModel):
    data: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    confidence_meta: ConfidenceMeta


class JobPostsSignal(BaseModel):
    data: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    confidence_meta: ConfidenceMeta


class BenchSignal(BaseModel):
    data: BenchSignalData
    confidence: float = Field(ge=0, le=1)
    confidence_meta: ConfidenceMeta


class EnrichmentSignals(BaseModel):
    crunchbase: CrunchbaseSignal
    funding: FundingSignal
    layoffs: LayoffsSignal
    leadership_change: LeadershipSignal
    job_posts: JobPostsSignal
    ai_maturity: AiMaturitySignal
    bench: BenchSignal


class HiringSignalBrief(BaseModel):
    """Typed result of the signal enrichment pipeline (`pipeline.run`)."""

    model_config = ConfigDict(extra="ignore")

    company_name: str
    company_domain: str = ""
    generated_at: str = ""
    icp_segment: int = Field(
        0,
        ge=0,
        le=4,
        description="0 = general; 1–4 = dominant buying-signal bucket from the brief.",
    )
    segment_confidence: float = Field(0.0, ge=0, le=1)
    overall_confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Mean of per-signal confidence blocks (crunchbase, funding, layoffs, "
        "leadership, job_posts).",
    )
    overall_confidence_weighted: float = Field(
        ...,
        ge=0,
        le=1,
        description="Weighted blend emphasizing firmographics + live job-page evidence.",
    )
    signals: EnrichmentSignals
    tech_stack: list[str] = Field(default_factory=list)
    data_sources_checked: list[dict[str, Any]] = Field(default_factory=list)
    honesty_flags: list[str] = Field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-serializable dict matching the historical pipeline shape (+ weighted overall)."""
        return self.model_dump(mode="json")
