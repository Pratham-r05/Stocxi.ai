"""
agent_report.py — Report Agent: converts AnalysisResult → PDF bytes.

Tier mapping (matches existing report_service.py):
  orbiter → 1-page beginner report
  stellar → 2-page standard report
  apex    → 3-page pro report (formerly "Pro tier")

Usage:
    from backend.agents.agent_report import build_report
    pdf_bytes = build_report(result, tier="apex", risk_level="medium")
"""

from __future__ import annotations

import logging
from typing import Any

from backend.schemas.messages import AnalysisResult
from backend.services.report_service import build_stock_report_pdf, _build_minimal_pdf

logger = logging.getLogger(__name__)


# ── Verdict mapping ────────────────────────────────────────────────────────────

_SIGNAL_TO_VERDICT = {
    "bullish": "BUY",
    "bearish": "AVOID",  # SEBI: never write "SELL" in user-facing output (CLAUDE.md Rule 12)
    "neutral": "HOLD",
    "mixed":   "HOLD",
}


def _map_verdict(overall_signal: str) -> str:
    """Map AnalysisResult.overall_signal → PDF verdict string."""
    return _SIGNAL_TO_VERDICT.get(overall_signal.lower(), "HOLD")


def _map_confidence(calibrated_confidence: float | None) -> str:
    """Map numeric confidence → human-readable label."""
    if calibrated_confidence is None:
        return "Medium"
    if calibrated_confidence > 0.7:
        return "High"
    if calibrated_confidence > 0.5:
        return "Medium"
    return "Low"


def _build_investor_fit(result: AnalysisResult) -> str:
    """Build a human-readable investor fit string from the UserProfile."""
    horizon_label = "long-term" if result.profile.horizon.value == "long" else "short-term"
    risk_label = result.profile.risk.value
    return f"Suitable for {horizon_label} {risk_label} risk investors"


# ── report_payload builder ─────────────────────────────────────────────────────

def _build_report_payload(result: AnalysisResult, tier: str) -> dict[str, Any]:
    """
    Construct the report_payload dict from AnalysisResult fields.

    Keys required by build_stock_report_pdf:
      verdict, confidence, investor_fit, executive_summary,
      thesis_points, risk_flags, action_plan,
      fundamental_view, technical_view, news_announcements_view,
      financial_health_view, report_title
    """
    verdict    = _map_verdict(result.overall_signal)
    confidence = _map_confidence(result.calibrated_confidence)

    executive_summary = (result.what_data_suggests or "")[:400]

    thesis_points = list(result.signals_in_favor[:4])
    risk_flags    = list(result.signals_against[:4])

    action_plan = [
        "Verify with your own research before investing.",
        "Define your stop-loss before entry.",
        "Monitor for upcoming corporate announcements.",
    ]

    report_title = f"{result.stock} Analysis Report \u2014 {result.analysis_date}"

    return {
        "verdict":                  verdict,
        "confidence":               confidence,
        "investor_fit":             _build_investor_fit(result),
        "executive_summary":        executive_summary,
        "thesis_points":            thesis_points,
        "risk_flags":               risk_flags,
        "action_plan":              action_plan,
        "fundamental_view":         "",
        "technical_view":           "",
        "news_announcements_view":  "",
        "financial_health_view":    result.data_disclosure or "",
        "report_title":             report_title,
    }


# ── analysis_snapshot builder ──────────────────────────────────────────────────

def _build_minimal_snapshot(result: AnalysisResult) -> dict[str, Any]:
    """
    Build the analysis_snapshot dict from what's available in AnalysisResult.

    AnalysisResult does not carry raw market data, so most sub-fields will be
    None/empty.  build_stock_report_pdf handles None gracefully via _to_text().
    """
    price = result.current_price

    return {
        "key_indicators": {
            "price":          price,
            "change_percent": None,
            "market_cap":     None,
            "pe_ratio":       None,
            "pb_ratio":       None,
            "eps":            None,
            "book_value":     None,
            "dividend_yield": None,
            "roe":            None,
            "roce":           None,
            "week_52_high":   None,
            "week_52_low":    None,
        },
        "technical_indicators": {
            "overall_signal": result.overall_signal,
            "rsi":            None,
            "macd":           None,
            "adx":            None,
            "atr":            None,
            "ema_signal":     None,
            "bb_signal":      None,
            "macd_signal":    None,
        },
        "volume_exchange_price_context": {
            "exchange":       None,
            "volume": {
                "current_volume":       None,
                "volume_sma_20":        None,
                "volume_ratio_vs_20d":  None,
                "signal":               "normal",
            },
            "day_range": {
                "open":  None,
                "high":  None,
                "low":   None,
            },
            "price_movement": {
                "1w":          {"change_pct": None},
                "1mo":         {"change_pct": None},
                "6mo":         {"change_pct": None},
                "1y":          {"change_pct": None},
                "trend_signal": "sideways",
            },
        },
        "important_news":          [],
        "important_announcements": [],
        "financial_statement_snapshot": {
            "quarterly":    {"revenue_change_pct": None, "net_profit_change_pct": None},
            "annual":       {"revenue_change_pct": None, "net_profit_change_pct": None},
            "balance_sheet": {"borrowings_latest": None},
            "cash_flow":    {"operating_cash_flow_latest": None},
            "shareholding": {
                "promoter_pct": None,
                "fii_pct":      None,
                "dii_pct":      None,
                "public_pct":   None,
            },
        },
    }


# ── Public entry point ─────────────────────────────────────────────────────────

def build_report(
    result: AnalysisResult,
    tier: str = "stellar",
    risk_level: str = "medium",
) -> bytes:
    """
    Convert an AnalysisResult into PDF bytes.

    Never raises — on any exception, falls back to _build_minimal_pdf.

    Args:
        result:     The AnalysisResult returned by the orchestrator.
        tier:       Report tier: "orbiter" | "stellar" | "apex".
        risk_level: Investor risk level for PDF header: "low" | "medium" | "high".

    Returns:
        PDF bytes.
    """
    try:
        report_payload    = _build_report_payload(result, tier)
        analysis_snapshot = _build_minimal_snapshot(result)

        # ai_analysis dict in old format — pass minimal compatible stub
        ai_analysis: dict[str, Any] = {
            "final_verdict": report_payload["verdict"],
            "plain_english": result.what_data_suggests or "",
            "fundamentals":  {"summary": ""},
            "technicals":    {"summary": ""},
            "news":          {"summary": ""},
        }

        return build_stock_report_pdf(
            symbol=result.nse_symbol or result.stock,
            company_name=result.stock,
            tier=tier,
            risk_level=risk_level,
            report_payload=report_payload,
            analysis_snapshot=analysis_snapshot,
            ai_analysis=ai_analysis,
        )
    except Exception as exc:
        logger.warning("agent_report.build_report failed for %s: %s", result.stock, exc)
        return _build_minimal_pdf(
            symbol=result.stock,
            company_name=result.stock,
            tier=tier,
            reason=str(exc),
        )
