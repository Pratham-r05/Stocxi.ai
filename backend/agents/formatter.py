"""
formatter.py — Output Formatter.

Contract (AGENTS.md §5):
  Input:  VerifiedAnalysis + AnonMap + FetchRequest + node count dict + current price
  Output: AnalysisResult (user-facing) + admin_view dict (internal)

Rules:
  - Pure Python. No LLM. No network I/O.
  - De-anonymization is mechanical token substitution via AnonMap.restore_text().
  - User-facing output has no node_ids, no internal jargon.
  - Admin view carries the full reasoning trace.
  - Disclaimer is mandatory on every output.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any

from backend.schemas.messages import AnalysisResult, FetchRequest, VerifiedAnalysis
from backend.schemas.node import Node
from backend.util.sanitizer import AnonMap, restore_text

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "This analysis is AI-generated from publicly available data as a pattern description "
    "for educational use. Stocxi is not a SEBI-registered investment advisor. "
    "Historical signal patterns are not predictions. "
    "Consult a qualified advisor before investing."
)


def _de_anon_text(text: str, anon_map: AnonMap) -> str:
    """Restore real names in a single text string."""
    return restore_text(text, anon_map)


def _de_anon_claims(claims: list, anon_map: AnonMap) -> list[str]:
    """Convert claim objects → plain-English bullet strings, de-anonymized."""
    result = []
    for c in claims:
        text = _de_anon_text(c.text, anon_map)
        if text.strip():
            result.append(text.strip())
    return result


def _build_data_disclosure(
    node_counts: dict[str, int],
    failed_fetches: list[str] | None = None,
) -> str:
    """
    Build the one-line data transparency statement.
    Example: "Analysis based on 17 technical indicators, 10 financial ratios,
              5 news items, 15 announcements. News fetch was partial today."
    """
    parts = []
    label_map = {
        "technical":    "technical indicator",
        "fundamental":  "financial ratio",
        "news":         "news item",
        "announcement": "announcement",
        "context":      "context node",
    }
    for cat, count in sorted(node_counts.items()):
        if count > 0:
            label = label_map.get(cat, cat)
            plural = "s" if count != 1 else ""
            parts.append(f"{count} {label}{plural}")

    disclosure = "Analysis based on " + ", ".join(parts) + "." if parts else "Analysis based on available data."

    if failed_fetches:
        disclosure += " " + "; ".join(failed_fetches)

    return disclosure


def _build_what_data_suggests_prose(claims: list[str]) -> str:
    """Join de-anonymized what_data_suggests claims into a flowing paragraph."""
    if not claims:
        return "Insufficient data to form a detailed assessment."
    return " ".join(claims)


def format_result(
    *,
    verified: VerifiedAnalysis,
    anon_map: AnonMap,
    request: FetchRequest,
    nodes: list[Node],
    current_price: float | None = None,
    bse_code: str = "",
    nse_symbol: str = "",
    failed_fetches: list[str] | None = None,
    analysis_id: str | None = None,
    latency_ms: int = 0,
    cache_hit: bool = False,
) -> tuple[AnalysisResult, dict[str, Any]]:
    """
    Build user-facing AnalysisResult and admin-view dict from VerifiedAnalysis.

    Returns:
        (AnalysisResult, admin_view) tuple.
        AnalysisResult → returned to API caller.
        admin_view     → stored in audit log, accessible at /admin/analysis/{id}.
    """
    draft = verified.draft
    aid   = analysis_id or str(uuid.uuid4())

    # Node counts per category
    node_counts: dict[str, int] = {}
    for n in nodes:
        cat = n.category.value
        node_counts[cat] = node_counts.get(cat, 0) + 1

    # De-anonymize text
    wds_plain    = _de_anon_claims(draft.what_data_suggests, anon_map)
    favor_plain  = _de_anon_claims(draft.signals_in_favor, anon_map)
    against_plain = _de_anon_claims(draft.signals_against, anon_map)

    what_suggests_prose = _build_what_data_suggests_prose(wds_plain)
    disclosure          = _build_data_disclosure(node_counts, failed_fetches)

    # ── User-facing result ─────────────────────────────────────────────────────
    result = AnalysisResult(
        stock=request.stock.upper(),
        nse_symbol=nse_symbol or request.stock.upper(),
        bse_code=bse_code,
        current_price=current_price,
        price_delayed_minutes=15,
        analysis_date=request.as_of_date,
        profile=request.profile,
        overall_signal=draft.overall_signal,
        calibrated_confidence=None,    # set by calibration job after first backtest
        backtested_accuracy=None,       # set after first backtest run
        data_completeness=node_counts,
        what_data_suggests=what_suggests_prose,
        signals_in_favor=favor_plain,
        signals_against=against_plain,
        data_disclosure=disclosure,
        disclaimer=_DISCLAIMER,
        analysis_id=aid,
        cache_hit=cache_hit,
        latency_ms=latency_ms,
    )

    # ── Admin / internal view ──────────────────────────────────────────────────
    admin_view: dict[str, Any] = {
        "analysis_id":          aid,
        "stock":                request.stock.upper(),
        "profile":              request.profile.model_dump(),
        "as_of_date":           str(request.as_of_date),
        "model_id":             draft.model_id,
        "prompt_version":       draft.prompt_version,
        "weight_version":       draft.weight_version,
        "overall_signal":       draft.overall_signal,
        "raw_confidence":       draft.raw_confidence,
        "stripped_claims":      verified.stripped_claims,
        "low_fidelity":         verified.low_fidelity,
        "verification_method":  verified.verification_method,
        # Full reasoning trace
        "verdicts": {
            cat: {
                "direction":          v.direction,
                "summary":            _de_anon_text(v.summary, anon_map),
                "supporting_node_ids": v.supporting_node_ids,
                "confidence":         v.confidence,
            }
            for cat, v in draft.verdicts.items()
        },
        "agreements": [
            {
                "node_id_a": ag.node_id_a,
                "node_id_b": ag.node_id_b,
                "reason":    _de_anon_text(ag.reason, anon_map),
            }
            for ag in draft.agreements
        ],
        "contradictions": [
            {
                "node_id_positive": ct.node_id_positive,
                "node_id_negative": ct.node_id_negative,
                "resolution":       _de_anon_text(ct.resolution, anon_map),
                "tier_applied":     ct.tier_applied,
            }
            for ct in draft.contradictions
        ],
        # Full annotated claims (with node_ids visible for QA)
        "what_data_suggests_annotated": [
            {"text": _de_anon_text(c.text, anon_map), "node_ids": c.node_ids}
            for c in draft.what_data_suggests
        ],
        "signals_in_favor_annotated": [
            {"text": _de_anon_text(c.text, anon_map), "node_ids": c.node_ids}
            for c in draft.signals_in_favor
        ],
        "signals_against_annotated": [
            {"text": _de_anon_text(c.text, anon_map), "node_ids": c.node_ids}
            for c in draft.signals_against
        ],
        # Anonymization map (dev/staging only — do not expose in production admin)
        "anon_map": {real: placeholder for real, placeholder in anon_map.all_pairs()},
        # Run metadata
        "node_counts":   node_counts,
        "cache_hit":     cache_hit,
        "latency_ms":    latency_ms,
        "failed_fetches": failed_fetches or [],
    }

    logger.info(
        "formatter: %s — overall=%s conf=%.2f favor=%d against=%d stripped=%d",
        request.stock,
        draft.overall_signal,
        draft.raw_confidence,
        len(favor_plain),
        len(against_plain),
        verified.stripped_claims,
    )

    return result, admin_view
