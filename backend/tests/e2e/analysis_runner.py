"""
analysis_runner.py — Shared engine for the deep end-to-end analysis test suite.

Role:
  Provides all logic shared by short_term_test.py, medium_term_test.py, and
  long_term_test.py.  Each script supplies a stock list + time-horizon label;
  this module handles data collection, AI analysis, knowledge-graph rendering,
  output formatting, and file persistence.

Pipeline per stock:
  1. Collect: price/fundamentals, screener, technicals, news, announcements,
              price history (parallel)
  2. Analyse: custom deep-analysis prompt → structured AI JSON
  3. Graph:   text knowledge-graph built from collected nodes
  4. Format:  structured text report (company → fundamentals → technicals →
              news/announcements/financials → takeaway → graph)
  5. Write:   append to a single timestamped results file

Usage (called by individual test scripts — never run directly):
  from analysis_runner import run_full_test
  run_full_test(stocks=["TCS", "WIPRO"], time_horizon="short_term",
                horizon_label="Short Term (1 Day – 3 Months)")
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── sys.path bootstrap ────────────────────────────────────────────────────────
# Allow this file to be run from any working directory by ensuring that both
# the repo root and backend/ are importable.
_E2E_DIR     = Path(__file__).resolve().parent
_TESTS_DIR   = _E2E_DIR.parent
_BACKEND_DIR = _TESTS_DIR.parent
_REPO_ROOT   = _BACKEND_DIR.parent

for _p in (_REPO_ROOT, _BACKEND_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,          # suppress noisy service INFO logs during tests
    format="%(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("e2e.runner")

# ── Service imports (deferred until after sys.path is set) ────────────────────
from services.yfinance_service import get_price_and_fundamentals, get_history  # noqa: E402
from services.screener_service import get_financials                            # noqa: E402
from services.technicals_service import calculate_technicals                    # noqa: E402
from services.news_service import get_news                                      # noqa: E402
from fetchers.nse_client import fetch_announcements as _nse_fetch_announcements # noqa: E402
from services.ai_service import _get_vertex_client                             # noqa: E402
from config import settings                                                     # noqa: E402
from graph.knowledge_graph import render_3d_html                               # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
_RESULTS_DIR  = _E2E_DIR / "results"
_HISTORY_PERIODS = ["1w", "1mo", "6mo", "1y"]


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  Data collection
# ═══════════════════════════════════════════════════════════════════════════════

async def _collect(symbol: str) -> dict[str, Any]:
    """
    Gather all data sources for a single symbol in parallel.

    Returns a dict with keys: price_data, screener_data, technicals,
    news, announcements, history_map.  Any source failure is logged but
    does NOT abort; its value defaults to {} / [].
    """
    company_name_placeholder = symbol  # filled after price_data resolves

    price_data = await get_price_and_fundamentals(symbol)
    company_name = price_data.get("company_name") or symbol

    (
        screener_result,
        technicals_result,
        news_result,
        announcements_raw_result,
        *history_results,
    ) = await asyncio.gather(
        get_financials(symbol),
        calculate_technicals(symbol),
        get_news(symbol, company_name),
        _nse_fetch_announcements(symbol, limit=8),
        *[get_history(symbol, p) for p in _HISTORY_PERIODS],
        return_exceptions=True,
    )

    def _safe(result, default):
        if isinstance(result, Exception):
            logger.warning("Source failed for %s: %s", symbol, result)
            return default
        return result

    screener_data = _safe(screener_result, {})
    technicals    = _safe(technicals_result, {})
    news          = _safe(news_result, [])

    # nse_client.fetch_announcements returns {"items": [...]} — normalise to flat list
    ann_raw   = _safe(announcements_raw_result, {})
    announcements: list[dict] = ann_raw.get("items", []) if isinstance(ann_raw, dict) else []

    history_map: dict[str, dict] = {}
    for period, result in zip(_HISTORY_PERIODS, history_results):
        if isinstance(result, dict):
            history_map[period] = result
        else:
            logger.warning("History(%s) failed for %s: %s", period, symbol, result)

    return {
        "price_data":    price_data,
        "screener_data": screener_data,
        "technicals":    technicals,
        "news":          news,
        "announcements": announcements,
        "history_map":   history_map,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Deep AI analysis
# ═══════════════════════════════════════════════════════════════════════════════

_DEEP_SYSTEM_PROMPT = """You are a senior SEBI-aware Indian equity analyst.
Your task is to produce a structured, evidence-backed stock analysis.

Rules:
- Respond ONLY with valid JSON — no markdown, no backticks, no commentary.
- Every point must cite a number or data fact when available.
- Do NOT use words "BUY", "SELL", "RECOMMEND", or "ADVICE" in any field.
- Keep language plain and accessible to retail investors.
- Always include a disclaimer reminder in the takeaway.
- Use ₹ symbol for rupee values.
- Verdict in takeaway must be BULLISH, BEARISH or NEUTRAL for the given time horizon."""


def _build_deep_prompt(
    symbol: str,
    time_horizon: str,
    horizon_label: str,
    data: dict[str, Any],
) -> str:
    """
    Build the comprehensive deep-analysis prompt from collected data.

    Args:
        symbol:        NSE ticker (e.g. "NESTLEIND")
        time_horizon:  machine label (e.g. "short_term")
        horizon_label: display label (e.g. "Short Term (1 Day – 3 Months)")
        data:          output of _collect()

    Returns:
        Prompt string to send to the AI model.
    """
    pd  = data["price_data"]
    sc  = data["screener_data"]
    tc  = data["technicals"]
    ratios = sc.get("ratios", {}) if isinstance(sc, dict) else {}

    # ── Fundamental block ─────────────────────────────────────────────────────
    def _v(primary, fallback_key, fmt=None):
        val = primary if primary is not None else ratios.get(fallback_key)
        if val is None:
            return "N/A"
        return fmt.format(val) if fmt else str(val)

    fund_lines = [
        f"Company Name   : {pd.get('company_name') or symbol}",
        f"Exchange       : {pd.get('exchange', 'N/A')}",
        f"Sector         : {_v(pd.get('sector'), 'sector')}",
        f"Industry       : {_v(pd.get('industry'), 'industry')}",
        f"Current Price  : ₹{pd.get('price', 'N/A')}",
        f"1-Day Change   : {pd.get('change_percent', 'N/A')}%",
        f"Market Cap     : ₹{_v(pd.get('market_cap'), 'market_cap')} Cr",
        f"P/E Ratio      : {_v(pd.get('pe_ratio'), 'pe_ratio')}",
        f"P/B Ratio      : {_v(pd.get('pb_ratio'), 'pb_ratio')}",
        f"EPS            : ₹{_v(pd.get('eps'), 'eps')}",
        f"Book Value     : ₹{_v(pd.get('book_value'), 'book_value')}",
        f"ROE            : {ratios.get('roe', 'N/A')}%",
        f"ROCE           : {ratios.get('roce', 'N/A')}%",
        f"Dividend Yield : {_v(pd.get('dividend_yield'), 'dividend_yield')}%",
        f"52W High/Low   : ₹{pd.get('week_52_high', 'N/A')} / ₹{pd.get('week_52_low', 'N/A')}",
        f"Beta           : {pd.get('beta', 'N/A')}",
        f"Volume         : {pd.get('volume', 'N/A')}",
        f"Face Value     : ₹{ratios.get('face_value', 'N/A')}",
    ]

    # ── Technicals block ──────────────────────────────────────────────────────
    tech_lines = [
        f"RSI(14)        : {tc.get('rsi', 'N/A')} → {tc.get('rsi_signal', 'N/A')}",
        f"MACD           : {tc.get('macd', 'N/A')} → {tc.get('macd_signal', 'N/A')}",
        f"MACD Signal    : {tc.get('macd_signal_line', 'N/A')}",
        f"ADX(14)        : {tc.get('adx', 'N/A')} → {tc.get('adx_signal', 'N/A')}",
        f"EMA 20         : {tc.get('ema_20', 'N/A')}",
        f"EMA 50         : {tc.get('ema_50', 'N/A')}",
        f"EMA 200        : {tc.get('ema_200', 'N/A')}",
        f"EMA Signal     : {tc.get('ema_signal', 'N/A')}",
        f"BB Upper       : {tc.get('bb_upper', 'N/A')}",
        f"BB Lower       : {tc.get('bb_lower', 'N/A')}",
        f"BB Signal      : {tc.get('bb_signal', 'N/A')}",
        f"Volume SMA 20  : {tc.get('volume_sma_20', 'N/A')}",
        f"Overall Signal : {tc.get('overall_signal', 'N/A')}",
    ]

    # ── News block ────────────────────────────────────────────────────────────
    news_lines = []
    for i, item in enumerate(data["news"][:6], 1):
        if isinstance(item, dict) and item.get("title"):
            news_lines.append(
                f"{i}. {item['title']} "
                f"[{item.get('source', 'N/A')} | {item.get('published', 'N/A')}]"
            )
    if not news_lines:
        news_lines = ["No recent news available."]

    # ── Announcements block ───────────────────────────────────────────────────
    ann_lines = []
    for i, item in enumerate(data["announcements"][:6], 1):
        if isinstance(item, dict):
            subject = item.get("subject") or item.get("title") or ""
            if subject:
                ann_lines.append(
                    f"{i}. {subject} "
                    f"[{item.get('category', '')} | {item.get('date', 'N/A')}]"
                )
    if not ann_lines:
        ann_lines = ["No recent corporate announcements available."]

    # ── Financials block ──────────────────────────────────────────────────────
    def _q(key, subkey):
        v = ((sc.get("quarterly_results") or {}) if isinstance(sc, dict) else {})
        return "N/A"  # placeholder; raw Screener structure varies

    q = sc.get("quarterly_results") if isinstance(sc, dict) else {}
    a = sc.get("annual_results") if isinstance(sc, dict) else {}
    bs = sc.get("balance_sheet") if isinstance(sc, dict) else {}
    cf = sc.get("cash_flow") if isinstance(sc, dict) else {}
    sh = sc.get("shareholding") if isinstance(sc, dict) else {}

    fin_lines = [
        f"Quarterly Results table: {'available' if q else 'not available'}",
        f"Annual Results table   : {'available' if a else 'not available'}",
        f"Balance Sheet          : {'available' if bs else 'not available'}",
        f"Cash Flow              : {'available' if cf else 'not available'}",
        f"Shareholding Pattern   : {'available' if sh else 'not available'}",
    ]
    # Add any ratios available from screener
    for key in ["revenue_growth", "profit_growth", "debt_to_equity", "current_ratio",
                "sales_growth_3yr", "profit_growth_3yr", "peg_ratio"]:
        val = ratios.get(key)
        if val is not None:
            fin_lines.append(f"  {key}: {val}")

    # ── Price movement block ──────────────────────────────────────────────────
    movement_lines = []
    for period in _HISTORY_PERIODS:
        hdata = data["history_map"].get(period)
        if isinstance(hdata, dict):
            closes_raw = hdata.get("closes", [])
            closes = [c for c in closes_raw if isinstance(c, dict) and c.get("close")]
            if len(closes) >= 2:
                start = float(closes[0]["close"])
                end   = float(closes[-1]["close"])
                pct   = round(((end - start) / abs(start)) * 100, 2) if start else 0
                movement_lines.append(f"  {period}: {pct:+.2f}% (from ₹{start:.2f} to ₹{end:.2f})")
    if not movement_lines:
        movement_lines = ["  Price history data unavailable."]

    return f"""Perform a comprehensive deep stock analysis for {symbol}.

Time Horizon: {horizon_label}

--- FUNDAMENTAL DATA ---
{chr(10).join(fund_lines)}

--- TECHNICAL INDICATORS ---
{chr(10).join(tech_lines)}

--- PRICE MOVEMENT (historical) ---
{chr(10).join(movement_lines)}

--- RECENT NEWS (latest 6) ---
{chr(10).join(news_lines)}

--- CORPORATE ANNOUNCEMENTS (latest 6) ---
{chr(10).join(ann_lines)}

--- FINANCIAL STATEMENTS AVAILABILITY ---
{chr(10).join(fin_lines)}

Return ONLY this JSON (no markdown):
{{
  "company_description": "3-4 sentences: company full name, which sector/industry, what products/services, founded/listed since when, any key business facts a retail investor should know first",
  "fundamental_analysis": [
    "Point 1: mention the exact indicator name and number, then explain what it means for the {time_horizon} investor",
    "Point 2: ...",
    "Point 3: ...",
    "Point 4: ...",
    "Point 5: ..."
  ],
  "technical_analysis": [
    "Point 1: RSI(14) = X → interpretation for {time_horizon}",
    "Point 2: MACD = X → ...",
    "Point 3: ADX(14) = X → ...",
    "Point 4: EMA 20/50/200 = X/X/X → ...",
    "Point 5: Bollinger Bands = upper X / lower X → ..."
  ],
  "news_announcements_analysis": [
    "Point 1: specific headline/announcement and its likely market impact",
    "Point 2: ...",
    "Point 3: ..."
  ],
  "financial_statements_analysis": [
    "Point 1: quarterly/annual revenue, profit trends with numbers",
    "Point 2: balance sheet health indicator",
    "Point 3: cash flow observation",
    "Point 4: shareholding pattern note"
  ],
  "takeaway": "4-6 sentences. State clearly whether this stock looks BULLISH, BEARISH or NEUTRAL for {horizon_label} investors. Back it with 2-3 specific data points from the analysis above. End with: This is NOT financial advice — consult a SEBI-registered advisor."
}}"""


def _call_deep_ai(symbol: str, prompt: str) -> dict[str, Any]:
    """
    Synchronous call to Gemini for deep analysis JSON.
    Retries up to 3 times with exponential backoff on transient errors.

    Args:
        symbol: ticker for logging
        prompt: full prompt string

    Returns:
        Parsed dict from AI response.

    Raises:
        RuntimeError: if all retries fail.
    """
    from openai import RateLimitError, APIStatusError

    client = _get_vertex_client()
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=settings.google_model,
                messages=[
                    {"role": "system", "content": _DEEP_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0,
                max_tokens=8192,
            )
            raw = (response.choices[0].message.content or "").strip()
            # Strip markdown fences if model wraps response
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)

        except (RateLimitError, APIStatusError) as exc:
            wait = 2 ** attempt
            logger.warning("Gemini transient error for %s (attempt %d/3), retry in %ds: %s",
                           symbol, attempt + 1, wait, exc)
            time.sleep(wait)
            last_error = exc

        except json.JSONDecodeError as exc:
            wait = 2 ** attempt
            logger.warning("Gemini invalid JSON for %s (attempt %d/3), retry in %ds: %s",
                           symbol, attempt + 1, wait, exc)
            time.sleep(wait)
            last_error = exc

        except Exception as exc:
            logger.error("Gemini unexpected error for %s: %s", symbol, exc)
            raise

    raise RuntimeError(f"Deep AI analysis failed for {symbol} after 3 attempts") from last_error


async def _analyse_deep(
    symbol: str,
    time_horizon: str,
    horizon_label: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Async wrapper: builds prompt and calls AI in thread pool.

    Returns AI analysis dict on success, or error-fallback dict on failure.
    """
    prompt = _build_deep_prompt(symbol, time_horizon, horizon_label, data)
    loop   = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _call_deep_ai, symbol, prompt)
    except Exception as exc:
        logger.error("Deep analysis failed for %s: %s", symbol, exc)
        return {
            "company_description": f"Data collection succeeded but AI analysis failed: {exc}",
            "fundamental_analysis": ["AI analysis unavailable — check service credentials."],
            "technical_analysis":   ["AI analysis unavailable."],
            "news_announcements_analysis": ["AI analysis unavailable."],
            "financial_statements_analysis": ["AI analysis unavailable."],
            "takeaway": "Unable to generate takeaway — AI provider error. This is NOT financial advice.",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  Knowledge graph (text representation)
# ═══════════════════════════════════════════════════════════════════════════════

def _signal_badge(signal: str | None) -> str:
    """Convert a signal string to an uppercase badge for display."""
    s = str(signal or "").strip().upper()
    if not s:
        return "[N/A]"
    return f"[{s}]"


def _build_knowledge_graph_text(
    symbol: str,
    data: dict[str, Any],
    ai_result: dict[str, Any],
) -> str:
    """
    Build a human-readable ASCII knowledge graph for the stock.

    Nodes: Company → Price, Fundamentals, Technicals, News,
                     Announcements, Financials, Verdict
    Edges: labelled with signal direction

    Args:
        symbol:    ticker
        data:      output of _collect()
        ai_result: output of _analyse_deep()

    Returns:
        Multi-line string representing the graph.
    """
    pd   = data["price_data"]
    tc   = data["technicals"]
    news = data["news"]
    anns = data["announcements"]
    sc   = data["screener_data"]
    ratios = sc.get("ratios", {}) if isinstance(sc, dict) else {}

    company_name = pd.get("company_name") or symbol
    price        = pd.get("price", "N/A")
    change_pct   = pd.get("change_percent", "N/A")
    exchange     = pd.get("exchange", "N/A")
    sector       = pd.get("sector") or ratios.get("sector", "N/A")

    overall_tech = _signal_badge(tc.get("overall_signal"))
    rsi_sig  = _signal_badge(tc.get("rsi_signal"))
    macd_sig = _signal_badge(tc.get("macd_signal"))
    ema_sig  = _signal_badge(tc.get("ema_signal"))
    bb_sig   = _signal_badge(tc.get("bb_signal"))
    adx_sig  = _signal_badge(tc.get("adx_signal"))

    pe   = pd.get("pe_ratio") or ratios.get("pe_ratio", "N/A")
    roe  = ratios.get("roe", "N/A")
    roce = ratios.get("roce", "N/A")
    mktcap = pd.get("market_cap") or ratios.get("market_cap", "N/A")
    eps  = pd.get("eps") or ratios.get("eps", "N/A")
    pb   = pd.get("pb_ratio") or ratios.get("pb_ratio", "N/A")

    news_count = len([n for n in news if isinstance(n, dict) and n.get("title")])
    ann_count  = len([a for a in anns if isinstance(a, dict) and (a.get("subject") or a.get("title"))])

    fin_avail = []
    for key in ["quarterly_results", "annual_results", "balance_sheet", "cash_flow", "shareholding"]:
        if isinstance(sc, dict) and sc.get(key):
            fin_avail.append(key.replace("_", " ").title())

    price_1d = f"{change_pct:+.2f}%" if isinstance(change_pct, (int, float)) else f"{change_pct}%"

    # ── Price movement summary ────────────────────────────────────────────────
    movement_parts = []
    for period in _HISTORY_PERIODS:
        hdata = data["history_map"].get(period)
        if isinstance(hdata, dict):
            closes_raw = hdata.get("closes", [])
            closes = [c for c in closes_raw if isinstance(c, dict) and c.get("close")]
            if len(closes) >= 2:
                start = float(closes[0]["close"])
                end   = float(closes[-1]["close"])
                pct   = round(((end - start) / abs(start)) * 100, 2) if start else 0
                movement_parts.append(f"{period}: {pct:+.2f}%")
    movement_str = "  |  ".join(movement_parts) if movement_parts else "N/A"

    lines = [
        "╔══════════════════════════════════════════════════════════════════════╗",
        f"║  KNOWLEDGE GRAPH — {symbol:<50}║",
        "╚══════════════════════════════════════════════════════════════════════╝",
        "",
        f"  ┌─────────────────────────────────────────┐",
        f"  │  COMPANY: {company_name[:40]:<40}│",
        f"  │  Symbol:  {symbol:<12}  Exchange: {exchange:<10}       │",
        f"  │  Sector:  {str(sector)[:40]:<40}│",
        f"  └─────────────────────────────────────────┘",
        "                         │",
        "       ┌─────────────────┼──────────────────┐",
        "       │                 │                  │",
        "       ▼                 ▼                  ▼",
        "",
        "  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐",
        f"  │  PRICE NODE  │  │  FUND. NODE  │  │  TECHNICALS NODE     │",
        f"  │──────────────│  │──────────────│  │──────────────────────│",
        f"  │ ₹{str(price)[:8]:<8}      │  │ P/E   : {str(pe)[:6]:<6}   │  │ RSI(14): {str(tc.get('rsi','N/A'))[:6]:<6} {rsi_sig:<12}│",
        f"  │ 1D: {price_1d:<9} │  │ P/B   : {str(pb)[:6]:<6}   │  │ MACD  : {str(tc.get('macd','N/A'))[:6]:<6} {macd_sig:<12}│",
        f"  │              │  │ ROE   : {str(roe)[:5]:<5}%  │  │ ADX   : {str(tc.get('adx','N/A'))[:6]:<6} {adx_sig:<12}│",
        f"  │              │  │ ROCE  : {str(roce)[:5]:<5}%  │  │ EMA   :        {ema_sig:<12}│",
        f"  │              │  │ EPS   : {str(eps)[:6]:<6}   │  │ BB    :        {bb_sig:<12}│",
        f"  │              │  │ MCap  : {str(mktcap)[:8]:<8} │  │ Signal:   {overall_tech:<14}│",
        "  └──────────────┘  └──────────────┘  └──────────────────────┘",
        "",
        "       ┌─────────────────┼──────────────────┐",
        "       │                 │                  │",
        "       ▼                 ▼                  ▼",
        "",
        f"  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐",
        f"  │  NEWS NODE   │  │  ANNOUNCE.   │  │  FINANCIALS NODE     │",
        f"  │──────────────│  │  NODE        │  │──────────────────────│",
        f"  │ {news_count} headlines│  │──────────────│  │ Tables available:    │",
        f"  │              │  │ {ann_count} items     │  │ {', '.join(fin_avail[:2]):<20} │",
        f"  │              │  │              │  │ {', '.join(fin_avail[2:4]):<20} │",
        f"  │              │  │              │  │ {(fin_avail[4] if len(fin_avail) > 4 else ''):<20} │",
        "  └──────────────┘  └──────────────┘  └──────────────────────┘",
        "",
        "  Price Movement Summary:",
        f"  {movement_str}",
        "",
        "  Edge Legend:",
        "  ── Agreement (signals aligned)   ~~~ Contradiction (signals conflict)",
        "  === Neutral / Inconclusive        *** Data unavailable",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  Report formatting
# ═══════════════════════════════════════════════════════════════════════════════

_DIVIDER   = "═" * 72
_SUBDIV    = "─" * 72
_SECTION   = "▶"


def _fmt_list(items: list | None, prefix: str = "  • ") -> str:
    """
    Format a list of strings (or dicts with a 'point' key) into bullet points.

    Handles cases where the model returns structured objects instead of plain strings.
    """
    if not items:
        return f"{prefix}No data available."
    lines = []
    for item in items:
        if isinstance(item, dict):
            # Extract the most useful key: point > text > description > summary > str()
            text = (
                item.get("point")
                or item.get("text")
                or item.get("description")
                or item.get("summary")
                or str(item)
            )
        else:
            text = str(item)
        lines.append(f"{prefix}{text}")
    return "\n".join(lines)


def _format_stock_section(
    idx: int,
    symbol: str,
    time_horizon: str,
    horizon_label: str,
    data: dict[str, Any],
    ai_result: dict[str, Any],
) -> str:
    """
    Format the full analysis section for one stock.

    Structure (mirrors the frontend AI analysis page):
      3.1.1  Company Description
      3.1.2  Key Fundamental Indicators
      3.1.3  Technical Indicators
      3.1.4  News, Announcements & Financial Statements
      3.1.5  AI Takeaway
      4.     Knowledge Graph

    Args:
        idx:           1-based stock index within the script
        symbol:        NSE ticker
        time_horizon:  machine label
        horizon_label: display label
        data:          output of _collect()
        ai_result:     output of _analyse_deep()

    Returns:
        Formatted multi-line string for this stock.
    """
    pd          = data["price_data"]
    company_name = pd.get("company_name") or symbol
    generated   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    graph_text = _build_knowledge_graph_text(symbol, data, ai_result)

    parts = [
        _DIVIDER,
        f"STOCK {idx}  |  {symbol}  |  {horizon_label}",
        f"Generated: {generated}",
        _DIVIDER,
        "",
        f"{_SECTION} 3.1.1  COMPANY DESCRIPTION",
        _SUBDIV,
        ai_result.get("company_description", "Description unavailable."),
        "",
        f"{_SECTION} 3.1.2  KEY FUNDAMENTAL INDICATORS",
        _SUBDIV,
        _fmt_list(ai_result.get("fundamental_analysis")),
        "",
        f"{_SECTION} 3.1.3  TECHNICAL INDICATORS",
        _SUBDIV,
        _fmt_list(ai_result.get("technical_analysis")),
        "",
        f"{_SECTION} 3.1.4  NEWS, ANNOUNCEMENTS & FINANCIAL STATEMENTS",
        _SUBDIV,
        _fmt_list(ai_result.get("news_announcements_analysis")),
        "",
        "  Financial Statements:",
        _fmt_list(ai_result.get("financial_statements_analysis"), prefix="    → "),
        "",
        f"{_SECTION} 3.1.5  AI TAKEAWAY ({horizon_label.upper()})",
        _SUBDIV,
        ai_result.get("takeaway", "Takeaway unavailable."),
        "",
        f"{_SECTION} 4.     KNOWLEDGE GRAPH",
        _SUBDIV,
        graph_text,
        "",
    ]

    return "\n".join(parts)


def _format_file_header(
    time_horizon: str,
    horizon_label: str,
    stocks: list[str],
) -> str:
    """Build the file-level header block."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return "\n".join([
        "╔" + "═" * 70 + "╗",
        f"║  STOCXI  —  DEEP END-TO-END ANALYSIS TEST REPORT" + " " * 20 + "║",
        f"║  Time Horizon : {horizon_label:<53}║",
        f"║  Stocks       : {', '.join(stocks):<53}║",
        f"║  Run Time     : {now:<53}║",
        f"║  AI Model     : {settings.google_model:<53}║",
        "╚" + "═" * 70 + "╝",
        "",
        "DISCLAIMER: All analysis in this file is AI-generated for testing",
        "purposes only. It is NOT financial advice. Do NOT make investment",
        "decisions based on this output. Consult a SEBI-registered advisor.",
        "",
        "═" * 72,
        "",
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  Main orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_single_stock(
    idx: int,
    symbol: str,
    time_horizon: str,
    horizon_label: str,
) -> str:
    """
    Full pipeline for a single stock: collect → analyse → format.

    Args:
        idx:           1-based index within batch
        symbol:        NSE ticker
        time_horizon:  machine label (e.g. "short_term")
        horizon_label: display label

    Returns:
        Formatted text section for this stock.
    """
    print(f"  [{idx}] Collecting data for {symbol} ...", flush=True)
    t0   = time.perf_counter()
    data = await _collect(symbol)
    t1   = time.perf_counter()
    print(f"       Data collected in {t1 - t0:.1f}s", flush=True)

    print(f"  [{idx}] Running AI deep analysis for {symbol} ...", flush=True)
    ai_result = await _analyse_deep(symbol, time_horizon, horizon_label, data)
    t2 = time.perf_counter()
    print(f"       AI analysis done in {t2 - t1:.1f}s", flush=True)

    return _format_stock_section(idx, symbol, time_horizon, horizon_label, data, ai_result)


async def _run_all_stocks(
    stocks: list[str],
    time_horizon: str,
    horizon_label: str,
) -> list[str]:
    """
    Run analysis for all stocks sequentially (avoids rate-limit bursts).

    Returns list of formatted sections in order.
    """
    sections = []
    for idx, symbol in enumerate(stocks, 1):
        section = await _run_single_stock(idx, symbol, time_horizon, horizon_label)
        sections.append(section)
        print(f"  ✓ {symbol} done.\n", flush=True)
    return sections


def run_full_test(
    stocks: list[str],
    time_horizon: str,
    horizon_label: str,
) -> Path:
    """
    Entry point called by each test script.

    Runs the full pipeline for all stocks, writes results to a timestamped
    file in tests/e2e/results/, and prints the output path.

    Args:
        stocks:        list of NSE symbols to analyse
        time_horizon:  machine label (e.g. "short_term", "medium_term", "long_term")
        horizon_label: human-readable label (e.g. "Short Term (1 Day – 3 Months)")

    Returns:
        Path to the written results file.
    """
    print(f"\n{'═' * 60}", flush=True)
    print(f"  STOCXI E2E TEST  —  {horizon_label}", flush=True)
    print(f"  Stocks: {', '.join(stocks)}", flush=True)
    print(f"{'═' * 60}\n", flush=True)

    header = _format_file_header(time_horizon, horizon_label, stocks)

    t_start = time.perf_counter()
    sections = asyncio.run(_run_all_stocks(stocks, time_horizon, horizon_label))
    t_total  = time.perf_counter() - t_start

    footer = "\n".join([
        "═" * 72,
        f"END OF REPORT  |  Total run time: {t_total:.1f}s",
        "═" * 72,
    ])

    full_report = header + "\n\n".join(sections) + "\n" + footer + "\n"

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = _RESULTS_DIR / f"{time_horizon}_analysis_{timestamp}.txt"
    output_path.write_text(full_report, encoding="utf-8")

    print(f"\n{'═' * 60}", flush=True)
    print(f"  ✅ Report saved to:", flush=True)
    print(f"     {output_path}", flush=True)
    print(f"  Total run time: {t_total:.1f}s", flush=True)
    print(f"{'═' * 60}\n", flush=True)

    return output_path
