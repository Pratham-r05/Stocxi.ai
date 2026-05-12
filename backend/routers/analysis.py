"""
routers/analysis.py — AI-powered stock analysis endpoint.

Endpoint:
  GET /api/v1/analysis/{symbol}?risk_level=medium

Flow:
  1. Fetch price + fundamentals (required)
  2. Fetch screener ratios (optional, enriches fundamentals)
  3. Fetch technicals (optional, enriches analysis)
  4. Fetch news (optional, informs sentiment)
  5. Run all fetches concurrently via asyncio.gather()
  6. Call AI service with merged data
  7. Cache result 6 hours

Cache TTL: 21600s (6 hrs) — from AI_CONTEXT.md TTL_ANALYSIS
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from cache.redis_client import cache_get, cache_set, TTL_ANALYSIS_RESULT as TTL_ANALYSIS
from services.yfinance_service import get_price_and_fundamentals, get_history
from services.screener_service import get_financials
from services.technicals_service import calculate_technicals
from services.news_service import get_news
from services.announcements_service import get_announcements
from services.symbol_service import canonicalize_symbol
from services.ai_service import analyse, generate_report_payload
from services.report_service import build_stock_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["AI Analysis"])

def _safe_float(value: Any) -> float | None:
    """Convert arbitrary value to float for safe numeric operations."""
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _pct_change(latest: float | None, previous: float | None) -> float | None:
    """Compute percentage change between two numbers with zero guards."""
    if latest is None or previous is None or previous == 0:
        return None
    return round(((latest - previous) / abs(previous)) * 100, 2)


def _extract_row_values(table: dict, label_hints: list[str]) -> list[float]:
    """Return numeric values for the first row whose label matches any hint."""
    rows = (table or {}).get("rows", []) if isinstance(table, dict) else []
    for row in rows:
        label = str((row or {}).get("label", "")).lower()
        if any(hint in label for hint in label_hints):
            values = (row or {}).get("values", [])
            cleaned: list[float] = []
            for value in values:
                num = _safe_float(value)
                if num is not None:
                    cleaned.append(num)
            return cleaned
    return []


def _latest_previous(values: list[float]) -> tuple[float | None, float | None]:
    """Return latest and previous values from Screener row values."""
    latest = values[0] if len(values) >= 1 else None
    previous = values[1] if len(values) >= 2 else None
    return latest, previous


def _build_financial_snapshot(screener_data: dict) -> dict:
    """Build concise financial highlights from Screener tables for AI context."""
    quarterly = screener_data.get("quarterly_results", {}) if isinstance(screener_data, dict) else {}
    annual = screener_data.get("annual_results", {}) if isinstance(screener_data, dict) else {}
    balance_sheet = screener_data.get("balance_sheet", {}) if isinstance(screener_data, dict) else {}
    cash_flow = screener_data.get("cash_flow", {}) if isinstance(screener_data, dict) else {}
    shareholding = screener_data.get("shareholding", {}) if isinstance(screener_data, dict) else {}

    q_revenue_vals = _extract_row_values(quarterly, ["sales", "revenue"])
    q_profit_vals = _extract_row_values(quarterly, ["net profit", "profit after tax", "pat"])
    a_revenue_vals = _extract_row_values(annual, ["sales", "revenue"])
    a_profit_vals = _extract_row_values(annual, ["net profit", "profit after tax", "pat"])

    q_revenue_latest, q_revenue_prev = _latest_previous(q_revenue_vals)
    q_profit_latest, q_profit_prev = _latest_previous(q_profit_vals)
    a_revenue_latest, a_revenue_prev = _latest_previous(a_revenue_vals)
    a_profit_latest, a_profit_prev = _latest_previous(a_profit_vals)

    borrowings_vals = _extract_row_values(balance_sheet, ["borrowings", "debt"])
    op_cash_vals = _extract_row_values(cash_flow, ["cash from operating", "operating activities"])

    promoter_vals = _extract_row_values(shareholding, ["promoters"])
    fii_vals = _extract_row_values(shareholding, ["fii", "foreign institutions"])
    dii_vals = _extract_row_values(shareholding, ["dii", "domestic institutions"])
    public_vals = _extract_row_values(shareholding, ["public"])

    promoter_latest = promoter_vals[0] if promoter_vals else None
    fii_latest = fii_vals[0] if fii_vals else None
    dii_latest = dii_vals[0] if dii_vals else None
    public_latest = public_vals[0] if public_vals else None

    return {
        "quarterly": {
            "revenue_latest": q_revenue_latest,
            "revenue_previous": q_revenue_prev,
            "revenue_change_pct": _pct_change(q_revenue_latest, q_revenue_prev),
            "net_profit_latest": q_profit_latest,
            "net_profit_previous": q_profit_prev,
            "net_profit_change_pct": _pct_change(q_profit_latest, q_profit_prev),
        },
        "annual": {
            "revenue_latest": a_revenue_latest,
            "revenue_previous": a_revenue_prev,
            "revenue_change_pct": _pct_change(a_revenue_latest, a_revenue_prev),
            "net_profit_latest": a_profit_latest,
            "net_profit_previous": a_profit_prev,
            "net_profit_change_pct": _pct_change(a_profit_latest, a_profit_prev),
        },
        "balance_sheet": {
            "borrowings_latest": borrowings_vals[0] if borrowings_vals else None,
        },
        "cash_flow": {
            "operating_cash_flow_latest": op_cash_vals[0] if op_cash_vals else None,
        },
        "shareholding": {
            "promoter_pct": promoter_latest,
            "fii_pct": fii_latest,
            "dii_pct": dii_latest,
            "public_pct": public_latest,
        },
    }


def _build_price_movement_snapshot(history_data: dict[str, dict]) -> dict:
    """Build period-wise price movement summary from history endpoint payloads."""
    out: dict[str, Any] = {}
    trend_score = 0

    for period, payload in history_data.items():
        closes_raw = payload.get("closes", []) if isinstance(payload, dict) else []
        closes = [c for c in closes_raw if isinstance(c, dict) and _safe_float(c.get("close")) is not None]
        if len(closes) < 2:
            out[period] = {"change_pct": None, "high": None, "low": None, "latest": None}
            continue

        start = _safe_float(closes[0].get("close"))
        end = _safe_float(closes[-1].get("close"))
        values = [_safe_float(c.get("close")) for c in closes]
        valid_values = [v for v in values if v is not None]

        change = _pct_change(end, start)
        if change is not None:
            if change > 2:
                trend_score += 1
            elif change < -2:
                trend_score -= 1

        out[period] = {
            "change_pct": change,
            "high": round(max(valid_values), 2) if valid_values else None,
            "low": round(min(valid_values), 2) if valid_values else None,
            "latest": round(end, 2) if end is not None else None,
        }

    if trend_score >= 2:
        trend_signal = "uptrend"
    elif trend_score <= -2:
        trend_signal = "downtrend"
    else:
        trend_signal = "sideways"

    out["trend_signal"] = trend_signal
    return out


def _build_volume_context(current_volume: Any, volume_sma_20: Any) -> dict:
    """Build simple volume confirmation context for AI interpretation."""
    current = _safe_float(current_volume)
    sma = _safe_float(volume_sma_20)

    ratio = None
    signal = "normal"
    if current is not None and sma is not None and sma > 0:
        ratio = round(current / sma, 2)
        if ratio >= 1.5:
            signal = "high"
        elif ratio < 0.7:
            signal = "low"

    return {
        "current_volume": int(current) if current is not None else None,
        "volume_sma_20": round(sma, 2) if sma is not None else None,
        "volume_ratio_vs_20d": ratio,
        "signal": signal,
    }


def _compact_news(news: list[dict], limit: int = 5) -> list[dict]:
    """Keep only key fields from top news headlines for AI prompt grounding."""
    compact = []
    for item in news[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        compact.append(
            {
                "title": title,
                "source": item.get("source"),
                "published": item.get("published"),
            }
        )
    return compact


def _compact_announcements(items: list[dict], limit: int = 5) -> list[dict]:
    """Keep key announcement fields so AI can reference important corporate updates."""
    compact = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or item.get("title") or "").strip()
        if not subject:
            continue
        compact.append(
            {
                "subject": subject,
                "category": item.get("category"),
                "date": item.get("date"),
                "source": item.get("source"),
            }
        )
    return compact


def _resolve_symbol(symbol: str) -> tuple[str, str]:
    """Resolve requested symbol to canonical symbol for provider compatibility."""
    requested = symbol.upper().strip()
    canonical = canonicalize_symbol(requested)
    return requested, canonical


async def _collect_analysis_inputs(symbol: str) -> dict[str, Any]:
    """Collect and normalize all core analysis data for AI and report generation."""
    price_data = await get_price_and_fundamentals(symbol)

    screener_task = get_financials(symbol)
    technicals_task = calculate_technicals(symbol)
    news_task = get_news(symbol, price_data.get("company_name"))
    announcements_task = get_announcements(symbol, limit=8)
    history_periods = ["1w", "1mo", "6mo", "1y"]
    history_tasks = [get_history(symbol, p) for p in history_periods]

    (
        screener_result,
        technicals_result,
        news_result,
        announcements_result,
        *history_results,
    ) = await asyncio.gather(
        screener_task,
        technicals_task,
        news_task,
        announcements_task,
        *history_tasks,
        return_exceptions=True,
    )

    screener_ratios = {}
    if isinstance(screener_result, dict):
        screener_ratios = screener_result.get("ratios", {})
    else:
        logger.warning(f"Screener failed for {symbol}: {screener_result}")

    technicals = {}
    if isinstance(technicals_result, dict):
        technicals = technicals_result
    else:
        logger.warning(f"Technicals failed for {symbol}: {technicals_result}")

    news = []
    if isinstance(news_result, list):
        news = news_result
    else:
        logger.warning(f"News failed for {symbol}: {news_result}")

    announcements = []
    if isinstance(announcements_result, list):
        announcements = announcements_result
    else:
        logger.warning(f"Announcements failed for {symbol}: {announcements_result}")

    history_map: dict[str, dict] = {}
    for period, result in zip(history_periods, history_results):
        if isinstance(result, dict):
            history_map[period] = result
        else:
            logger.warning(f"History failed for {symbol} period={period}: {result}")

    def fill(primary_val, screener_key):
        """Use Screener fallback value when primary source is missing."""
        return primary_val if primary_val is not None else screener_ratios.get(screener_key)

    fundamentals_for_ai = {
        "price": price_data.get("price"),
        "pe_ratio": fill(price_data.get("pe_ratio"), "pe_ratio"),
        "market_cap": fill(price_data.get("market_cap"), "market_cap"),
        "book_value": fill(price_data.get("book_value"), "book_value"),
        "week_52_high": price_data.get("week_52_high"),
        "week_52_low": price_data.get("week_52_low"),
        "dividend_yield": fill(price_data.get("dividend_yield"), "dividend_yield"),
        "roce": screener_ratios.get("roce"),
        "roe": screener_ratios.get("roe"),
        "eps": fill(price_data.get("eps"), "eps"),
        "beta": price_data.get("beta"),
        "change_percent": price_data.get("change_percent"),
        "exchange": price_data.get("exchange"),
        "sector": fill(price_data.get("sector"), "sector"),
        "industry": fill(price_data.get("industry"), "industry"),
        "volume": price_data.get("volume"),
        "open": price_data.get("open"),
        "day_high": price_data.get("day_high"),
        "day_low": price_data.get("day_low"),
        "face_value": screener_ratios.get("face_value"),
        "pb_ratio": fill(price_data.get("pb_ratio"), "pb_ratio"),
    }

    financial_snapshot = _build_financial_snapshot(screener_result if isinstance(screener_result, dict) else {})
    price_movement = _build_price_movement_snapshot(history_map)
    volume_context = _build_volume_context(price_data.get("volume"), technicals.get("volume_sma_20"))

    analysis_snapshot = {
        "company_profile": {
            "symbol": symbol,
            "company_name": price_data.get("company_name") or symbol,
            "exchange": price_data.get("exchange"),
            "sector": fill(price_data.get("sector"), "sector"),
            "industry": fill(price_data.get("industry"), "industry"),
        },
        "key_indicators": {
            "price": price_data.get("price"),
            "change_percent": price_data.get("change_percent"),
            "market_cap": fill(price_data.get("market_cap"), "market_cap"),
            "pe_ratio": fill(price_data.get("pe_ratio"), "pe_ratio"),
            "pb_ratio": fill(price_data.get("pb_ratio"), "pb_ratio"),
            "eps": fill(price_data.get("eps"), "eps"),
            "book_value": fill(price_data.get("book_value"), "book_value"),
            "dividend_yield": fill(price_data.get("dividend_yield"), "dividend_yield"),
            "roe": screener_ratios.get("roe"),
            "roce": screener_ratios.get("roce"),
            "week_52_high": price_data.get("week_52_high"),
            "week_52_low": price_data.get("week_52_low"),
        },
        "volume_exchange_price_context": {
            "exchange": price_data.get("exchange"),
            "volume": volume_context,
            "day_range": {
                "open": price_data.get("open"),
                "high": price_data.get("day_high"),
                "low": price_data.get("day_low"),
            },
            "price_movement": price_movement,
        },
        "technical_indicators": technicals,
        "important_news": _compact_news(news, limit=5),
        "important_announcements": _compact_announcements(announcements, limit=5),
        "financial_statement_snapshot": financial_snapshot,
    }

    return {
        "price_data": price_data,
        "technicals": technicals,
        "news": news,
        "announcements": announcements,
        "fundamentals_for_ai": fundamentals_for_ai,
        "analysis_snapshot": analysis_snapshot,
    }


def _build_quick_ai_stub(
    *,
    symbol: str,
    risk_level: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic analysis stub when cached AI analysis is unavailable."""
    technicals = context.get("technicals") or {}
    fundamentals = context.get("fundamentals_for_ai") or {}
    news_items = context.get("news") or []

    overall_signal = str(technicals.get("overall_signal") or "neutral").lower()
    change_percent = _safe_float((context.get("price_data") or {}).get("change_percent"))

    if overall_signal == "bullish":
        verdict = "BUY"
    elif overall_signal == "bearish":
        verdict = "AVOID"
    else:
        verdict = "HOLD"

    if risk_level == "low" and verdict == "BUY" and (change_percent is None or change_percent < 0):
        verdict = "HOLD"

    top_news = ""
    for item in news_items:
        if isinstance(item, dict) and item.get("title"):
            top_news = str(item.get("title"))
            break

    summary = (
        f"For a {risk_level} risk investor, the current setup is {overall_signal or 'mixed'} "
        f"with 1D change around {change_percent if change_percent is not None else 'N/A'}%. "
        f"Top recent cue: {top_news or 'No major headline available.'}"
    )

    return {
        "symbol": symbol,
        "risk_level": risk_level,
        "fundamentals": {
            "verdict": "Neutral",
            "summary": "Quick fallback summary used for report generation.",
        },
        "technicals": {
            "verdict": "Mixed",
            "summary": f"Overall technical signal: {technicals.get('overall_signal', 'Unknown')}",
        },
        "news": {
            "verdict": "Neutral",
            "summary": top_news or "No major headline available.",
        },
        "social": {
            "verdict": "Neutral",
            "summary": "Social data not used in quick fallback.",
        },
        "final_verdict": verdict,
        "plain_english": summary,
        "risk_match": verdict != "AVOID",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "This analysis is AI-generated and for informational purposes only. "
            "It is NOT financial advice. Please consult a SEBI-registered advisor "
            "before making investment decisions."
        ),
        "context_for_report": {
            "price": fundamentals.get("price"),
            "overall_signal": technicals.get("overall_signal"),
            "change_percent": change_percent,
        },
    }


@router.get("/{symbol}")
async def get_analysis(
    symbol: str,
    risk_level: str = Query(
        default="medium",
        pattern="^(low|medium|high)$",
        description="Investor risk profile: low | medium | high",
    ),
):
    """
    AI-powered stock analysis for the given symbol and risk level.

    Returns structured assessment:
      - fundamentals verdict (Strong / Weak / Neutral)
      - technicals verdict (Bullish / Bearish / Mixed)
      - news sentiment (Positive / Negative / Neutral)
      - final_verdict (BUY / HOLD / AVOID)
      - plain_english summary tailored to risk level
      - risk_match (bool — does this stock suit the investor's risk profile?)
      - SEBI disclaimer

    Cached 6 hours per symbol+risk_level combination.
    """
    requested_symbol, symbol = _resolve_symbol(symbol)
    risk_level = risk_level.lower().strip()
    cache_key  = f"analysis:v4:{requested_symbol}:{symbol}:{risk_level}"

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = await cache_get(cache_key)
    if cached:
        logger.info(f"Cache hit: {cache_key}")
        return JSONResponse(content=cached)

    try:
        context = await _collect_analysis_inputs(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis data collection failed for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Analysis data unavailable: {e}")

    # ── Step 5: AI analysis ───────────────────────────────────────────────────
    ai_result = await analyse(
        symbol=symbol,
        fundamentals=context["fundamentals_for_ai"],
        technicals=context["technicals"],
        news=context["news"],
        risk_level=risk_level,
        analysis_snapshot=context["analysis_snapshot"],
    )

    # ── Step 6: Enrich response with source data ──────────────────────────────
    response = {
        **ai_result,
        "symbol": requested_symbol,
        "canonical_symbol": symbol,
        "company_name": context["price_data"].get("company_name") or requested_symbol,
        "exchange": context["price_data"].get("exchange"),
        "current_price": context["price_data"].get("price"),
        "change_percent": context["price_data"].get("change_percent"),
        "overall_technical_signal": context["technicals"].get("overall_signal", "Unknown"),
    }

    # Cache normal AI output for 6h; cache fallback output for 30m to reduce repeated provider failures.
    cache_ttl = TTL_ANALYSIS if not ai_result.get("error") else 1800
    await cache_set(cache_key, response, cache_ttl)

    return JSONResponse(content=response)


@router.get("/{symbol}/report")
async def download_analysis_report(
    symbol: str,
    tier: str = Query(
        default="stellar",
        pattern="^(orbiter|stellar|apex)$",
        description="Report audience tier: orbiter | stellar | apex",
    ),
    risk_level: str = Query(
        default="medium",
        pattern="^(low|medium|high)$",
        description="Investor risk profile used by report AI",
    ),
):
    """Generate and download a one-page AI PDF report for the selected stock."""
    requested_symbol, canonical_symbol = _resolve_symbol(symbol)
    tier = tier.lower().strip()
    risk_level = risk_level.lower().strip()
    cache_key = f"analysis:report:v1:{requested_symbol}:{tier}:{risk_level}"

    cached = await cache_get(cache_key)
    if isinstance(cached, dict):
        report_payload = cached.get("report_payload") or {}
        ai_result = cached.get("ai_result") or {}
        analysis_snapshot = cached.get("analysis_snapshot") or {}
        company_name = cached.get("company_name") or requested_symbol
    else:
        try:
            context = await _collect_analysis_inputs(canonical_symbol)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Report data collection failed for {canonical_symbol}: {e}")
            raise HTTPException(status_code=503, detail=f"Report data unavailable: {e}")

        analysis_cache_key = f"analysis:v3:{requested_symbol}:{risk_level}"
        cached_analysis = await cache_get(analysis_cache_key)
        if isinstance(cached_analysis, dict):
            ai_result = cached_analysis
        else:
            ai_result = _build_quick_ai_stub(
                symbol=requested_symbol,
                risk_level=risk_level,
                context=context,
            )

        report_payload = await generate_report_payload(
            symbol=requested_symbol,
            company_name=context["price_data"].get("company_name") or requested_symbol,
            tier=tier,
            risk_level=risk_level,
            fundamentals=context["fundamentals_for_ai"],
            technicals=context["technicals"],
            news=context["news"],
            announcements=context["announcements"],
            analysis_snapshot=context["analysis_snapshot"],
            ai_analysis=ai_result,
        )

        analysis_snapshot = context["analysis_snapshot"]
        company_name = context["price_data"].get("company_name") or requested_symbol

        await cache_set(
            cache_key,
            {
                "report_payload": report_payload,
                "ai_result": ai_result,
                "analysis_snapshot": analysis_snapshot,
                "company_name": company_name,
                "canonical_symbol": canonical_symbol,
                "generated_at": report_payload.get("generated_at"),
            },
            TTL_ANALYSIS,
        )

    pdf_bytes = build_stock_report_pdf(
        symbol=requested_symbol,
        company_name=company_name,
        tier=tier,
        risk_level=risk_level,
        report_payload=report_payload,
        analysis_snapshot=analysis_snapshot,
        ai_analysis=ai_result,
    )

    safe_symbol = "".join(ch for ch in requested_symbol if ch.isalnum() or ch in {"-", "_"}) or "STOCK"
    filename = f"{safe_symbol}_{tier}_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
