"""
messages.py — Typed messages passed between agents.

Every agent communicates using these models — never raw dicts.
Fail fast on schema mismatch at agent boundaries.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

from .node import Node


# ── User Profile ──────────────────────────────────────────────────────────────

class Horizon(str, Enum):
    short = "short"
    long  = "long"


class Risk(str, Enum):
    conservative = "conservative"
    moderate     = "moderate"
    aggressive   = "aggressive"


class UserProfile(BaseModel):
    horizon: Horizon
    risk: Risk
    sector: str = Field(default="", description="Sector preference — affects peer selection only")

    @property
    def bucket(self) -> str:
        """Cache key component. e.g. 'short_moderate'"""
        return f"{self.horizon.value}_{self.risk.value}"


# ── Fetch layer ───────────────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    stock: str
    as_of_date: date
    profile: UserProfile
    request_id: str = Field(description="UUID for end-to-end tracing")


class FetchDomain(str, Enum):
    technical    = "technical"
    fundamental  = "fundamental"
    news         = "news"
    announcement = "announcement"
    context      = "context"


class RawPayload(BaseModel):
    domain: FetchDomain
    source: str                    # source id from sources.yaml
    source_url: str = ""
    fetched_at_ist: datetime
    payload: dict[str, Any]        # source-specific raw data, kept for audit
    request_id: str


class FetchFailure(BaseModel):
    domain: FetchDomain
    source: str
    reason: Literal["timeout", "blocked", "parse_error", "unapproved_source", "empty", "rate_limited"]
    error: str
    request_id: str


# ── Analysis layer ────────────────────────────────────────────────────────────

class Claim(BaseModel):
    """A single sentence in the analysis output, with source citation."""
    text: str
    node_ids: list[str] = Field(description="node_ids that support this claim")
    is_positive: bool | None = None   # None = neutral/descriptive


class Verdict(BaseModel):
    """Summary verdict for one data category (technical/fundamental/news/announcement)."""
    category: str
    direction: Literal["bullish", "bearish", "neutral", "mixed"]
    summary: str
    supporting_node_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class AgreementLink(BaseModel):
    node_id_a: str
    node_id_b: str
    reason: str


class ContradictionLink(BaseModel):
    node_id_positive: str
    node_id_negative: str
    resolution: str          # which won and why (contradiction_tiers from weights.yaml)
    tier_applied: int        # 1–6


class AnalysisDraft(BaseModel):
    """Raw output from Analysis Agent before Verifier pass."""
    what_data_suggests: list[Claim]
    signals_in_favor: list[Claim]
    signals_against: list[Claim]
    verdicts: dict[str, Verdict]        # keyed by category name
    agreements: list[AgreementLink]
    contradictions: list[ContradictionLink]
    overall_signal: Literal["bullish", "bearish", "neutral", "mixed"]
    raw_confidence: float = Field(ge=0.0, le=1.0)

    # Run metadata — stamped by Analysis Agent
    model_id: str
    prompt_version: str
    weight_version: str


class VerifiedAnalysis(BaseModel):
    """AnalysisDraft after Verifier Agent has stripped unsourced claims."""
    draft: AnalysisDraft
    stripped_claims: int = 0
    low_fidelity: bool = False          # True if stripped_claims > threshold
    verification_method: Literal["python", "llm"] = "python"


class AnalysisResult(BaseModel):
    """Final user-facing result returned by the API."""
    # Header
    stock: str
    nse_symbol: str
    bse_code: str | None
    current_price: float | None
    price_delayed_minutes: int = 15
    analysis_date: date
    profile: UserProfile
    overall_signal: str
    calibrated_confidence: float | None = None    # set after calibration job exists
    backtested_accuracy: float | None = None      # set after first backtest run
    data_completeness: dict[str, int]             # {category: node_count}

    # User-facing content (no node_ids, no jargon)
    what_data_suggests: str              # single prose paragraph
    signals_in_favor: list[str]          # plain English bullets
    signals_against: list[str]           # plain English bullets
    data_disclosure: str                 # one-line: "17 indicators, 11 ratios, ..."
    disclaimer: str

    # Internal only — not serialized in API response; populated by orchestrator for in-process use
    _internal_draft: AnalysisDraft | None = PrivateAttr(default=None)
    _verified: VerifiedAnalysis | None = PrivateAttr(default=None)

    # Audit
    analysis_id: str
    cache_hit: bool = False
    latency_ms: int = 0
