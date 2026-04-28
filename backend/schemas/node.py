"""
node.py — Universal Node schema. Every piece of data in Stocxi is a Node.

This is the single source of truth for node shape (ARCHITECTURE.md §3).
Any code that produces or consumes nodes must use this model — never raw dicts.

node_id is deterministic: "{stock}|{category}|{name}|{as_of_date}"
Collision on the same (stock, category, name, date) = idempotent overwrite.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class NodeCategory(str, Enum):
    technical    = "technical"
    fundamental  = "fundamental"
    news         = "news"
    announcement = "announcement"
    context      = "context"       # market regime, sector, peers, completeness


class NodeSignal(str, Enum):
    positive = "positive"
    negative = "negative"
    neutral  = "neutral"


class HorizonRelevance(str, Enum):
    short = "short"
    long  = "long"
    both  = "both"


class Node(BaseModel):
    # ── Identity ──────────────────────────────────────────────────────────────
    node_id: str = Field(
        description="Deterministic key: {stock}|{category}|{name}|{as_of_date}"
    )
    stock: str = Field(description="NSE ticker, e.g. RELIANCE")
    category: NodeCategory
    name: str = Field(description="Indicator/metric name, e.g. RSI, Revenue_Growth")

    # ── Value ─────────────────────────────────────────────────────────────────
    value: str = Field(description="Human-readable display value")
    value_raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Original source payload — kept for audit, never sent to LLM",
    )
    context: str = Field(
        default="",
        description=(
            "Gemini-generated context string — what this signal means for the "
            "investor's chosen horizon. Generated at fetch time by context_generator.py. "
            "Horizon-aware: same node gets different context for SHORT vs LONG."
        ),
    )

    # ── Signal ────────────────────────────────────────────────────────────────
    signal: NodeSignal
    confidence: float = Field(ge=0.0, le=1.0, description="Raw (uncalibrated) confidence")

    # ── Source ────────────────────────────────────────────────────────────────
    source: str = Field(description="Source id from sources.yaml, e.g. yfinance")
    source_url: str = Field(default="", description="Exact URL fetched (empty for libraries)")

    # ── Time ──────────────────────────────────────────────────────────────────
    as_of_date: date = Field(
        description="Point-in-time date — data known as of this date. Critical for backtest."
    )
    fetched_at_ist: datetime = Field(description="When this node was fetched, in IST")

    # ── Weight + relevance ────────────────────────────────────────────────────
    horizon_relevance: HorizonRelevance = HorizonRelevance.both
    weight: float = Field(
        default=0.0,
        description="Pulled from weights.yaml at normalization time",
    )
    weight_version: str = Field(default="", description="Stamped from versions.yaml")

    # ── Quality flags ─────────────────────────────────────────────────────────
    schema_version: int = Field(default=1)
    sanitized: bool = Field(
        default=False,
        description="Must be True before node enters any LLM prompt",
    )

    @model_validator(mode="before")
    @classmethod
    def build_node_id(cls, data: dict) -> dict:
        """Auto-build node_id if not provided."""
        if not data.get("node_id"):
            stock    = str(data.get("stock", "")).upper()
            cat      = data.get("category", "")
            category = cat.value if hasattr(cat, "value") else str(cat)
            name     = str(data.get("name", ""))
            as_of    = str(data.get("as_of_date", ""))
            data["node_id"] = f"{stock}|{category}|{name}|{as_of}"
        return data

    def anonymized_value(self) -> str:
        """Alias for value — full anonymization is applied by the orchestrator
        via sanitizer.py before any node reaches the LLM."""
        return self.value

    def prompt_repr(self) -> dict:
        """Compact dict safe to include in the LLM prompt.
        Never includes value_raw, source_url, fetched_at, or schema internals."""
        rep = {
            "id":       self.node_id,
            "name":     self.name,
            "value":    self.value,       # sanitizer has already scrubbed this
            "signal":   self.signal.value,
            "weight":   round(self.weight, 4),
            "horizon":  self.horizon_relevance.value,
            "source":   self.source,
            "date":     self.as_of_date.isoformat(),
        }
        if self.context:
            rep["context"] = self.context
        return rep

    class Config:
        use_enum_values = False
