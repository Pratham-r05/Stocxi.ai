"""
fetch_phase1_data.py — Phase 1 master data fetch for Stocxi.

Usage: python fetch_phase1_data.py [SYMBOL] [HORIZON]   (defaults: RELIANCE, long)

Output: data/{SYMBOL}_data.json

JSON structure:
  fundamentals          — name → {value, context, sentiment}
  technical_indicators  — name → {value, context, sentiment}
  announcements         — [{date, title, full_text, summary, sentiment}, ...]  top-10
  news                  — [{date, headline, source, url, summary, sentiment}, ...]  top-10
  balance_sheet         — metric → {years_data, yoy_change, comparison_summary}
  profit_loss           — metric → {years_data, yoy_change, comparison_summary}
  cash_flow             — metric → {years_data, yoy_change, comparison_summary}
  quarterly_results     — metric → {quarters_data, qoq_change, yoy_change, comparison_summary}
  shareholding_pattern  — category → {periods_data, change, comparison_summary}
  market_context        — name → {value, context, sentiment}

comparison_summary is rule-based (CAGR, trend direction, momentum) — no LLM required.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

SYMBOL  = sys.argv[1].upper() if len(sys.argv) > 1 else "RELIANCE"
HORIZON = sys.argv[2].lower() if len(sys.argv) > 2 else "long"

_SECTOR_MAP = {
    "RELIANCE": "energy",      "ONGC": "energy",        "IOC": "energy",
    "TCS": "technology",       "INFY": "technology",    "WIPRO": "technology",  "HCLTECH": "technology",
    "HDFCBANK": "banking",     "ICICIBANK": "banking",  "AXISBANK": "banking",  "KOTAKBANK": "banking",
    "ASIANPAINT": "paints",    "BERGERPAINTS": "paints",
    "MARUTI": "automobiles",   "TATAMOTORS": "automobiles", "BAJAJ-AUTO": "automobiles",
    "SUNPHARMA": "pharma",     "DRREDDY": "pharma",     "CIPLA": "pharma",
    "ITC": "fmcg",             "HINDUNILVR": "fmcg",    "NESTLEIND": "fmcg",
    "LT": "infrastructure",    "ADANIPORTS": "infrastructure",
    "SBIN": "banking",         "BAJFINANCE": "nbfc",    "BAJAJFINSV": "nbfc",
    "NYKAA": "retail",         "ZOMATO": "food_delivery",
}
SECTOR = _SECTOR_MAP.get(SYMBOL, "diversified")

print(f"\n{'='*60}")
print(f"  STOCXI — Phase 1 Data Fetch")
print(f"  Stock: {SYMBOL} | Horizon: {HORIZON}")
print(f"  Date:  {datetime.date.today()}")
print(f"{'='*60}\n")


# ── 1. Setup ──────────────────────────────────────────────────────────────────
print("[1/6] Loading config...")
from backend.schemas.messages import FetchRequest, FetchFailure, UserProfile

profile = UserProfile(horizon=HORIZON, risk="moderate", sector=SECTOR)
request = FetchRequest(
    stock=SYMBOL,
    profile=profile,
    as_of_date=datetime.date.today(),
    request_id=str(uuid.uuid4()),
)
print(f"      request_id : {request.request_id}")
print("  [OK] Config loaded\n")


# ── 2. Data agents (parallel) ─────────────────────────────────────────────────
print("[2/6] Running data agents in parallel...")
_AGENT_MODS = [
    ("technical",    "backend.agents.agent_technical"),
    ("fundamental",  "backend.agents.agent_fundamental"),
    ("news",         "backend.agents.agent_news"),
    ("announcement", "backend.agents.agent_announcement"),
    ("context",      "backend.agents.agent_context"),
]


async def _run_agent(name: str, mod_path: str, req: FetchRequest) -> tuple[str, list]:
    """Run a single agent module and return (name, nodes)."""
    try:
        mod    = importlib.import_module(mod_path)
        t0     = time.monotonic()
        result = await asyncio.wait_for(mod.run(req), timeout=180.0)
        ms     = int((time.monotonic() - t0) * 1000)
        if isinstance(result, FetchFailure):
            print(f"      [{name:12s}]   0 nodes  FETCH_FAILURE: {result.reason}  [WARN]")
            return name, []
        print(f"      [{name:12s}] {len(result):>3} nodes  {ms:>5}ms  [OK]")
        return name, result
    except asyncio.TimeoutError:
        print(f"      [{name:12s}]   0 nodes  TIMEOUT  [WARN]")
        return name, []
    except Exception as exc:
        print(f"      [{name:12s}]   0 nodes  ERROR: {exc}  [WARN]")
        return name, []


async def _run_all_agents() -> list:
    return await asyncio.gather(*[_run_agent(n, m, request) for n, m in _AGENT_MODS])

agent_results = asyncio.run(_run_all_agents())
cat_nodes: dict[str, list] = {name: nodes for name, nodes in agent_results}
all_nodes = [n for nodes in cat_nodes.values() for n in nodes]
print(f"\n      Total nodes fetched: {len(all_nodes)}")
print("  [OK] Agents complete\n")


# ── 3. Raw financial tables from Screener ─────────────────────────────────────
print("[3/6] Fetching raw financial tables from Screener.in...")
from backend.fetchers import screener_client

raw_financials: dict = {}
try:
    async def _fetch_screener() -> dict:
        return await screener_client.fetch_financials(SYMBOL)
    raw_financials = asyncio.run(_fetch_screener())
    found = [k for k in ("quarterly_results", "annual_results", "balance_sheet",
                          "cash_flow", "shareholding", "ratios") if raw_financials.get(k)]
    print(f"      Keys: {found}  [OK]")
except Exception as exc:
    print(f"      Screener fetch failed: {exc}  [WARN]")
print("  [OK] Raw financials done\n")


# ── 4. Pure-computation helpers ───────────────────────────────────────────────
print("[4/6] Building structured output...")


def _to_float(v: Any) -> float | None:
    """Parse a raw Screener value string to float, stripping commas and %."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _pct_change(new: float | None, old: float | None) -> str:
    """Return a ▲/▼/→ percent-change string."""
    if new is None or old is None or old == 0:
        return "N/A"
    pct = ((new - old) / abs(old)) * 100
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "→")
    return f"{arrow} {abs(pct):.1f}%"


def _signal_to_sentiment(signal: Any) -> str:
    """Map NodeSignal (positive/negative/neutral) to bullish/bearish/neutral."""
    s = str(signal.value) if hasattr(signal, "value") else str(signal)
    return {"positive": "bullish", "negative": "bearish", "neutral": "neutral"}.get(s, "neutral")


def _annual_summary(metric: str, values_dict: dict, yoy_str: str) -> str:
    """Rule-based 2-3 sentence trend summary for annual/balance-sheet data.

    Args:
        metric: Human-readable metric name.
        values_dict: Ordered dict newest-first {period_label: raw_value_string}.
        yoy_str: Pre-computed YoY change string (e.g. "▲ 12.1%").

    Returns:
        2-3 sentence plain-English trend summary.
    """
    numeric = [(k, _to_float(v)) for k, v in values_dict.items()]
    numeric = [(k, f) for k, f in numeric if f is not None]
    if not numeric:
        return "No numeric data available for trend analysis."
    if len(numeric) == 1:
        return f"Only one period of data available ({numeric[0][0]}). Trend analysis requires at least 2 periods."

    newest_period, newest_val = numeric[0]
    oldest_period, oldest_val = numeric[-1]
    n = len(numeric)

    # Overall direction label
    if oldest_val != 0:
        total_pct = ((newest_val - oldest_val) / abs(oldest_val)) * 100
        if   total_pct >  50: trend = "strong growth"
        elif total_pct >  15: trend = "steady growth"
        elif total_pct >   3: trend = "modest growth"
        elif total_pct >  -3: trend = "broadly stable"
        elif total_pct > -15: trend = "mild decline"
        elif total_pct > -50: trend = "consistent decline"
        else:                 trend = "significant decline"
    else:
        trend = "expansion from a near-zero base"

    # CAGR suffix (only when ≥3 positive points)
    if n >= 3 and oldest_val and oldest_val > 0 and newest_val > 0:
        try:
            cagr = (((newest_val / oldest_val) ** (1 / (n - 1))) - 1) * 100
            cagr_str = f" at a CAGR of {cagr:+.1f}% over {n} years"
        except Exception:
            cagr_str = f" over {n} years"
    else:
        cagr_str = f" from {oldest_period} to {newest_period}"

    s1 = f"{metric} shows {trend}{cagr_str}."
    s2 = f"Latest YoY change: {yoy_str}." if yoy_str not in ("N/A", "") else ""

    # Momentum direction from the last 3 data points
    if len(numeric) >= 3:
        d1 = numeric[0][1] - numeric[1][1]
        d2 = numeric[1][1] - numeric[2][1]
        scale = abs(newest_val) if newest_val else 1
        if abs(d1) < 0.02 * scale:
            s3 = "The metric has stabilized in recent periods."
        elif d1 * d2 > 0:
            s3 = ("Growth momentum is accelerating in the latest period."
                  if abs(d1) > abs(d2) * 1.2
                  else "The trend has remained consistent across recent periods.")
        else:
            s3 = "Trend direction reversed in the latest period — monitor for sustained change."
    else:
        s3 = ""

    return " ".join(s for s in [s1, s2, s3] if s)


def _quarterly_summary(metric: str, values_dict: dict, qoq_str: str, yoy_str: str) -> str:
    """Rule-based 2-3 sentence trend summary for quarterly data.

    Args:
        metric: Human-readable metric name.
        values_dict: Ordered dict newest-first {quarter_label: raw_value_string}.
        qoq_str: Pre-computed QoQ change string.
        yoy_str: Pre-computed YoY change string.

    Returns:
        2-3 sentence plain-English trend summary.
    """
    numeric = [(k, _to_float(v)) for k, v in values_dict.items()]
    numeric = [(k, f) for k, f in numeric if f is not None]
    if not numeric:
        return "No numeric data available for trend analysis."
    if len(numeric) == 1:
        return (f"Only one quarter of data available ({numeric[0][0]}). "
                "Multi-quarter trend analysis not possible.")

    newest_period, newest_val = numeric[0]

    # YoY-anchored sentence
    if yoy_str and yoy_str != "N/A":
        yoy_pct = _to_float(yoy_str.lstrip("▲▼→ "))
        if   yoy_pct is not None and yoy_pct >  15: yoy_desc = "strong YoY growth"
        elif yoy_pct is not None and yoy_pct >   5: yoy_desc = "healthy YoY growth"
        elif yoy_pct is not None and yoy_pct >   0: yoy_desc = "marginal YoY growth"
        elif yoy_pct is not None and yoy_pct >  -5: yoy_desc = "broadly flat YoY"
        else:                                        yoy_desc = "YoY decline"
        s1 = f"{metric} shows {yoy_desc} ({yoy_str}) in the latest quarter."
    else:
        s1 = (f"{metric} recorded at {newest_val:,.1f} in {newest_period}, "
              "the most recent quarter available.")

    s2 = f"Sequential QoQ change: {qoq_str}." if qoq_str not in ("N/A", "") else ""

    # Consistency over last 4 quarters
    if len(numeric) >= 4:
        vals = [f for _, f in numeric[:4]]
        rising = sum(1 for i in range(len(vals) - 1) if vals[i] >= vals[i + 1])
        if   rising >= 3: s3 = f"Consistently improving trend over the last {len(vals)} quarters."
        elif rising <= 1: s3 = f"Declining trend over the last {len(vals)} quarters — monitor closely."
        else:             s3 = f"Mixed quarterly performance over the last {len(vals)} quarters."
    else:
        s3 = ""

    return " ".join(s for s in [s1, s2, s3] if s)


def _shareholding_summary(category: str, values_dict: dict, change_str: str) -> str:
    """Rule-based 2-3 sentence trend summary for shareholding data.

    Args:
        category: Holder category (e.g. Promoters, FIIs).
        values_dict: Ordered dict newest-first {period_label: value_%_string}.
        change_str: Pre-computed period-over-period change string.

    Returns:
        2-3 sentence plain-English trend summary.
    """
    numeric = [(k, _to_float(v)) for k, v in values_dict.items()]
    numeric = [(k, f) for k, f in numeric if f is not None]
    if not numeric:
        return "No data available for shareholding trend analysis."
    if len(numeric) == 1:
        return (f"{category} holds {numeric[0][1]:.1f}% as of {numeric[0][0]}. "
                "Historical trend not available.")

    newest_period, newest_pct = numeric[0]
    oldest_period, oldest_pct = numeric[-1]
    delta = newest_pct - oldest_pct

    if   abs(delta) < 0.5: s1 = (f"{category} holding broadly stable at ~{newest_pct:.1f}% "
                                   f"over {len(numeric)} periods.")
    elif delta > 0:         s1 = (f"{category} holding increased from {oldest_pct:.1f}% "
                                   f"({oldest_period}) to {newest_pct:.1f}% ({newest_period}).")
    else:                   s1 = (f"{category} holding declined from {oldest_pct:.1f}% "
                                   f"({oldest_period}) to {newest_pct:.1f}% ({newest_period}).")

    s2 = f"Latest period-over-period change: {change_str}." if change_str not in ("N/A", "") else ""

    cat_lower = category.lower()
    if "promoter" in cat_lower:
        if   newest_pct >= 50: s3 = "Promoter holding above 50% indicates strong ownership concentration."
        elif newest_pct >= 40: s3 = "Promoter holding between 40–50% — moderate concentration."
        else:                  s3 = "Low promoter holding — watch for potential dilution risk."
    elif "fii" in cat_lower or "foreign" in cat_lower:
        if   delta >  2: s3 = "Rising FII interest signals growing institutional confidence."
        elif delta < -2: s3 = "Declining FII interest may indicate reduced institutional conviction."
        else:            s3 = ""
    elif "dii" in cat_lower or "mutual" in cat_lower:
        s3 = "Increasing domestic institutional interest is a positive signal." if delta > 1 else ""
    else:
        s3 = ""

    return " ".join(s for s in [s1, s2, s3] if s)


def _make_summary(context: str, value: str = "") -> str:
    """Compact one-line summary from context text (first sentence, ≤120 chars).

    Args:
        context: Full analysis or trend text.
        value: The metric value string (used as fallback when context is empty).

    Returns:
        One-sentence summary string.
    """
    if not context:
        return (value[:120] + "…") if len(value) > 120 else (value or "N/A")
    m = re.search(r"[.!?]", context)
    first = context[: m.end()].strip() if m else context.strip()
    # Strip trailing "relates to …" clause
    first = re.sub(r"\s+\w[\w\s]* relates to.*$", "", first).strip()
    return (first[:120] + "…") if len(first) > 120 else first


# ── Section builders ───────────────────────────────────────────────────────────

def _build_annual_section(table: dict, max_years: int = 10) -> dict:
    """Convert Screener annual/balance-sheet table into per-metric structured dicts.

    Args:
        table: Dict with 'headers' (list of period labels) and 'rows' (list of
               {label, values} dicts). Screener returns oldest-first.
        max_years: Maximum number of years to keep per metric.

    Returns:
        Dict mapping metric_name → {years_data, yoy_change, comparison_summary}.
    """
    headers: list = table.get("headers", [])
    rows: list    = table.get("rows", [])
    if not headers or not rows:
        return {}

    hdrs = list(reversed(headers))[:max_years]
    result: dict = {}
    for row in rows:
        metric = (row.get("label") or "").strip()
        if not metric:
            continue
        values = list(reversed(row.get("values", [])))[:max_years]
        floats = [_to_float(v) for v in values]
        years_data = {str(h): (str(v) if v is not None else "") for h, v in zip(hdrs, values)}
        yoy = _pct_change(floats[0], floats[1]) if len(floats) >= 2 else "N/A"
        result[metric] = {
            "years_data":         years_data,
            "yoy_change":         yoy,
            "comparison_summary": _annual_summary(metric, years_data, yoy),
        }
    return result


def _build_quarterly_section(table: dict, max_quarters: int = 8) -> dict:
    """Convert Screener quarterly table into per-metric structured dicts.

    Args:
        table: Dict with 'headers' and 'rows'. Screener returns oldest-first.
        max_quarters: Maximum number of quarters to keep per metric.

    Returns:
        Dict mapping metric_name → {quarters_data, qoq_change, yoy_change, comparison_summary}.
    """
    headers: list = table.get("headers", [])
    rows: list    = table.get("rows", [])
    if not headers or not rows:
        return {}

    hdrs = list(reversed(headers))[:max_quarters]
    result: dict = {}
    for row in rows:
        metric = (row.get("label") or "").strip()
        if not metric:
            continue
        values = list(reversed(row.get("values", [])))[:max_quarters]
        floats = [_to_float(v) for v in values]
        quarters_data = {str(h): (str(v) if v is not None else "") for h, v in zip(hdrs, values)}
        qoq = _pct_change(floats[0], floats[1]) if len(floats) >= 2 else "N/A"
        yoy = _pct_change(floats[0], floats[4]) if len(floats) >= 5 else "N/A"
        result[metric] = {
            "quarters_data":      quarters_data,
            "qoq_change":         qoq,
            "yoy_change":         yoy,
            "comparison_summary": _quarterly_summary(metric, quarters_data, qoq, yoy),
        }
    return result


def _build_shareholding_section(table: dict, max_periods: int = 6) -> dict:
    """Convert Screener shareholding table into per-category structured dicts.

    Args:
        table: Dict with 'headers' and 'rows'. Screener returns oldest-first.
        max_periods: Maximum number of periods to keep per category.

    Returns:
        Dict mapping category → {periods_data, change, comparison_summary}.
    """
    headers: list = table.get("headers", [])
    rows: list    = table.get("rows", [])
    if not headers or not rows:
        return {}

    hdrs = list(reversed(headers))[:max_periods]
    result: dict = {}
    for row in rows:
        category = (row.get("label") or "").strip()
        if not category:
            continue
        values = list(reversed(row.get("values", [])))[:max_periods]
        floats = [_to_float(v) for v in values]
        periods_data = {str(h): (str(v) if v is not None else "") for h, v in zip(hdrs, values)}
        change = _pct_change(floats[0], floats[1]) if len(floats) >= 2 else "N/A"
        result[category] = {
            "periods_data":       periods_data,
            "change":             change,
            "comparison_summary": _shareholding_summary(category, periods_data, change),
        }
    return result


def _nodes_to_dict(nodes: list) -> dict:
    """Convert a list of Nodes to {name: {value, context, sentiment}}.

    Args:
        nodes: List of Node objects.

    Returns:
        Ordered dict keyed by node.name.
    """
    return {
        n.name: {
            "value":     n.value,
            "context":   getattr(n, "context", "") or "",
            "sentiment": _signal_to_sentiment(n.signal),
        }
        for n in nodes
    }


def _build_announcements(nodes: list, top_n: int = 10) -> list:
    """Extract {date, title, full_text, summary, sentiment} from announcement nodes.

    Args:
        nodes: Announcement Node objects (newest-first from agent).
        top_n: Maximum number of announcements to return.

    Returns:
        List of announcement dicts.
    """
    result = []
    for n in nodes[:top_n]:
        raw  = n.value_raw or {}
        date = raw.get("date") or raw.get("ex_date") or str(n.as_of_date)
        result.append({
            "date":      date,
            "title":     (raw.get("purpose") or n.name or "")[:300],
            "full_text": (raw.get("pdf_text") or "")[:2000],
            "summary":   (raw.get("llm_summary") or getattr(n, "context", "") or n.value or "")[:300],
            "sentiment": _signal_to_sentiment(n.signal),
        })
    return result


def _build_news(nodes: list, top_n: int = 10) -> list:
    """Extract {date, headline, source, url, summary, sentiment} from news nodes.

    Args:
        nodes: News Node objects (newest-first from agent).
        top_n: Maximum number of news items to return.

    Returns:
        List of news dicts.
    """
    result = []
    for n in nodes[:top_n]:
        raw = n.value_raw or {}
        result.append({
            "date":      (raw.get("published") or str(n.as_of_date))[:10],
            "headline":  (raw.get("title") or n.name or "")[:300],
            "source":    raw.get("source_name") or raw.get("source") or n.source or "",
            "url":       raw.get("link") or n.source_url or "",
            "summary":   (raw.get("llm_summary") or raw.get("description") or n.value or "")[:500],
            "sentiment": _signal_to_sentiment(n.signal),
        })
    return result


# ── 5. Assemble final JSON ────────────────────────────────────────────────────
fund_nodes = cat_nodes.get("fundamental",  [])
tech_nodes = cat_nodes.get("technical",    [])
ann_nodes  = cat_nodes.get("announcement", [])
news_nodes = cat_nodes.get("news",         [])
ctx_nodes  = cat_nodes.get("context",      [])

balance_sheet      = _build_annual_section(raw_financials.get("balance_sheet", {}))
profit_loss        = _build_annual_section(raw_financials.get("annual_results", {}))
cash_flow          = _build_annual_section(raw_financials.get("cash_flow", {}))
quarterly_results  = _build_quarterly_section(raw_financials.get("quarterly_results", {}))
shareholding       = _build_shareholding_section(raw_financials.get("shareholding", {}))

output: dict = {
    "symbol":     SYMBOL,
    "as_of_date": str(datetime.date.today()),
    "request_id": request.request_id,
    "horizon":    HORIZON,
    "metadata": {
        "total_nodes":         len(all_nodes),
        "fundamentals_count":  len(fund_nodes),
        "technicals_count":    len(tech_nodes),
        "announcements_count": len(ann_nodes),
        "news_count":          len(news_nodes),
        "context_count":       len(ctx_nodes),
    },
    "fundamentals":          _nodes_to_dict(fund_nodes),
    "technical_indicators":  _nodes_to_dict(tech_nodes),
    "announcements":         _build_announcements(ann_nodes, top_n=10),
    "news":                  _build_news(news_nodes, top_n=10),
    "balance_sheet":         balance_sheet,
    "profit_loss":           profit_loss,
    "cash_flow":             cash_flow,
    "quarterly_results":     quarterly_results,
    "shareholding_pattern":  shareholding,
    "market_context":        {
        k: v for k, v in _nodes_to_dict(ctx_nodes).items()
        if k not in {"Sector_Trend", "Peer_Snapshot", "Data_Completeness"}
    },
}

print(f"      fundamentals      : {len(output['fundamentals'])} metrics")
print(f"      technical         : {len(output['technical_indicators'])} indicators")
print(f"      announcements     : {len(output['announcements'])} items")
print(f"      news              : {len(output['news'])} items")
print(f"      balance_sheet     : {len(output['balance_sheet'])} metrics")
print(f"      profit_loss       : {len(output['profit_loss'])} metrics")
print(f"      cash_flow         : {len(output['cash_flow'])} metrics")
print(f"      quarterly_results : {len(output['quarterly_results'])} metrics")
print(f"      shareholding      : {len(output['shareholding_pattern'])} categories")
print(f"      market_context    : {len(output['market_context'])} nodes")
print("  [OK] Payload assembled\n")


# ── 6. Build graphify-compatible markdown ────────────────────────────────────

_SENTIMENT_ICON = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}
_FUNDAMENTAL_RELATIONS = {
    "PE_Ratio":        "EPS, Revenue_Growth_YoY, Market_Cap",
    "PB_Ratio":        "Total_Assets, Reserves, Net_Worth",
    "ROE":             "Net_Profit_Annual, Reserves, EPS",
    "EPS":             "PE_Ratio, Net_Profit_Annual, Revenue_Annual",
    "OPM":             "Revenue_Annual, EBITDA_TTM, EBITDA_Margin",
    "NPM":             "Revenue_Annual, Net_Profit_Annual, OPM",
    "Revenue_Annual":  "Revenue_Growth_YoY, Net_Profit_Annual, OPM",
    "Net_Profit_Annual": "EPS, ROE, PAT_TTM",
    "Debt_To_Equity":  "Borrowings, Interest_Coverage, Operating_Cash_Flow",
    "Operating_Cash_Flow": "Free_Cashflow, Net_Profit_Annual",
    "Free_Cashflow":   "Operating_Cash_Flow, Debt_To_Equity, Borrowings",
    "Interest_Coverage": "Debt_To_Equity, Borrowings",
    "Market_Cap":      "PE_Ratio, EPS, Revenue_Annual",
    "Total_Assets":    "Total_Liabilities, Reserves, Borrowings",
    "Total_Liabilities": "Total_Assets, Borrowings, Debt_To_Equity",
    "Reserves":        "PB_Ratio, Net_Profit_Annual, Total_Assets",
    "Borrowings":      "Debt_To_Equity, Interest_Coverage, Free_Cashflow",
}
_TECHNICAL_RELATIONS = {
    "RSI":    "Price_Momentum, Overbought_Level, Oversold_Level",
    "MACD":   "Signal_Line, Trend_Direction, Price_Momentum",
    "SMA_20": "SMA_50, SMA_200, Price_Support",
    "SMA_50": "SMA_20, SMA_200, Trend_Direction",
    "SMA_200": "SMA_50, Long_Term_Trend, Golden_Cross",
    "ADX":    "Trend_Strength, MACD, RSI",
    "ATR":    "Volatility, Stop_Loss_Level, Risk",
    "VWAP":   "Price_Level, Volume, Intraday_Trend",
    "Volume": "VWAP, Price_Momentum, Breakout",
}
_BS_RELATIONS = {
    "Total Assets": "Total Liabilities, Net Worth, Borrowings",
    "Net Worth": "Reserves, Share Capital, ROE",
    "Borrowings": "Debt_To_Equity, Interest Coverage, Free_Cashflow",
    "Fixed Assets": "Capital Expenditure, Depreciation, Revenue_Annual",
    "Investments": "Total Assets, Cash, Returns",
    "Reserves": "Net Worth, Retained Earnings, PB_Ratio",
}
_PL_RELATIONS = {
    "Revenue": "Revenue_Annual, Revenue Growth, Operating Profit",
    "Expenses": "Revenue, Operating Profit, OPM",
    "Operating Profit": "OPM, EBITDA, Revenue",
    "Net Profit": "EPS, ROE, PAT_TTM",
    "EPS": "PE_Ratio, Net Profit, Market_Cap",
    "Tax": "Net Profit, PBT",
}
_CF_RELATIONS = {
    "Cash from Operations": "Operating_Cash_Flow, Net Profit, Working Capital",
    "Cash from Investing": "Capital Expenditure, Fixed Assets, Free_Cashflow",
    "Cash from Financing": "Borrowings, Dividends, Debt_To_Equity",
}


def _build_markdown(data: dict) -> str:
    """Render Phase 1 data dict as a graphify-compatible markdown document.

    Args:
        data: The assembled output dict from Phase 1.

    Returns:
        Full markdown string with YAML frontmatter, structured sections, and
        explicit relationship prose so graphify can extract nodes and edges.
    """
    sym     = data["symbol"]
    date    = data["as_of_date"]
    horizon = data["horizon"]
    lines: list[str] = []

    # YAML frontmatter — graphify uses these fields for node metadata
    lines += [
        "---",
        f"symbol: {sym}",
        f"captured_at: {date}",
        f"horizon: {horizon}",
        f"sector: {SECTOR}",
        "author: stocxi_phase1",
        "contributor: stocxi",
        "---",
        "",
        f"# {sym} — Stock Analysis Data",
        "",
        (f"{sym} is a stock in the **{SECTOR}** sector analyzed for a "
         f"**{horizon}-term** investment horizon as of {date}. "
         f"This document captures fundamentals, technical indicators, "
         f"financial statements, announcements, news, and market context. "
         f"Each section relates to others: Fundamentals drive valuation; "
         f"Technical Indicators reflect price momentum; Balance Sheet underpins "
         f"Debt_To_Equity and ROE; Profit Loss feeds EPS and PAT_TTM; "
         f"Cash Flow validates Net Profit quality; Shareholding signals "
         f"institutional confidence; Announcements and News capture recent events."),
        "",
    ]

    # ── Fundamentals ──────────────────────────────────────────────────────────
    lines += [
        "## Fundamentals",
        "",
        (f"{sym} fundamentals provide valuation, profitability, and financial health "
         f"metrics. PE_Ratio relates to EPS and Revenue_Growth_YoY. ROE depends on "
         f"Net_Profit_Annual and Reserves. Operating_Cash_Flow relates to Free_Cashflow "
         f"and Debt_To_Equity. Market_Cap relates to PE_Ratio and EPS."),
        "",
    ]
    for name, d in data.get("fundamentals", {}).items():
        icon  = _SENTIMENT_ICON.get(d.get("sentiment", "neutral"), "➡️")
        rels  = _FUNDAMENTAL_RELATIONS.get(name, "")
        rel_text = f" {name} relates to {rels}." if rels else ""
        lines += [
            f"### {name}",
            f"**Value:** {d.get('value', 'N/A')} | **Sentiment:** {icon} {d.get('sentiment', 'neutral')}",
            f"**Analysis:** {d.get('context', '')}{rel_text}",
            "",
        ]

    # ── Technical Indicators ──────────────────────────────────────────────────
    lines += [
        "## Technical Indicators",
        "",
        (f"Technical indicators for {sym} capture price momentum, trend strength, "
         f"and market timing signals. RSI relates to overbought and oversold conditions. "
         f"MACD relates to trend direction and Signal Line crossovers. "
         f"SMA_20, SMA_50, and SMA_200 relate to short, medium, and long-term trend support. "
         f"ADX relates to trend strength. ATR relates to volatility and risk."),
        "",
    ]
    for name, d in data.get("technical_indicators", {}).items():
        icon  = _SENTIMENT_ICON.get(d.get("sentiment", "neutral"), "➡️")
        rels  = _TECHNICAL_RELATIONS.get(name, "")
        rel_text = f" {name} relates to {rels}." if rels else ""
        lines += [
            f"### {name}",
            f"**Value:** {d.get('value', 'N/A')} | **Sentiment:** {icon} {d.get('sentiment', 'neutral')}",
            f"**Analysis:** {d.get('context', '')}{rel_text}",
            "",
        ]

    # ── Balance Sheet ─────────────────────────────────────────────────────────
    lines += [
        "## Balance Sheet",
        "",
        (f"The Balance Sheet tracks {sym}'s assets, liabilities, and net worth over time. "
         f"Total Assets relates to Total Liabilities and Net Worth. "
         f"Borrowings drives Debt_To_Equity and Interest Coverage. "
         f"Reserves relates to Net Worth and PB_Ratio. "
         f"Fixed Assets relates to Capital Expenditure and Revenue capacity."),
        "",
    ]
    for metric, d in data.get("balance_sheet", {}).items():
        yoy   = d.get("yoy_change", "N/A")
        ydata = d.get("years_data", {})
        vals  = " | ".join(f"{yr}: {v}" for yr, v in list(ydata.items())[:5])
        rels  = _BS_RELATIONS.get(metric, "")
        rel_text = f" {metric} relates to {rels}." if rels else ""
        lines += [
            f"### {metric}",
            f"**Values:** {vals}",
            f"**YoY Change:** {yoy}",
            f"**Summary:** {_make_summary(d.get('comparison_summary', ''), vals[:60])}",
            f"**Trend:** {d.get('comparison_summary', '')}{rel_text}",
            "",
        ]

    # ── Profit & Loss ─────────────────────────────────────────────────────────
    lines += [
        "## Profit and Loss",
        "",
        (f"The Profit and Loss statement for {sym} tracks revenue, expenses, and "
         f"net profit over time. Revenue relates to Revenue_Annual and Revenue_Growth_YoY. "
         f"Operating Profit relates to OPM and EBITDA. Net Profit relates to EPS and ROE. "
         f"EPS relates to PE_Ratio and Market_Cap valuation."),
        "",
    ]
    for metric, d in data.get("profit_loss", {}).items():
        yoy   = d.get("yoy_change", "N/A")
        ydata = d.get("years_data", {})
        vals  = " | ".join(f"{yr}: {v}" for yr, v in list(ydata.items())[:5])
        rels  = _PL_RELATIONS.get(metric, "")
        rel_text = f" {metric} relates to {rels}." if rels else ""
        lines += [
            f"### {metric}",
            f"**Values:** {vals}",
            f"**YoY Change:** {yoy}",
            f"**Summary:** {_make_summary(d.get('comparison_summary', ''), vals[:60])}",
            f"**Trend:** {d.get('comparison_summary', '')}{rel_text}",
            "",
        ]

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    lines += [
        "## Cash Flow",
        "",
        (f"Cash Flow statement for {sym} measures actual cash movement. "
         f"Cash from Operations relates to Operating_Cash_Flow and Net Profit quality. "
         f"Cash from Investing relates to Capital Expenditure and Free_Cashflow. "
         f"Cash from Financing relates to Borrowings and Debt_To_Equity."),
        "",
    ]
    for metric, d in data.get("cash_flow", {}).items():
        yoy   = d.get("yoy_change", "N/A")
        ydata = d.get("years_data", {})
        vals  = " | ".join(f"{yr}: {v}" for yr, v in list(ydata.items())[:5])
        rels  = _CF_RELATIONS.get(metric, "")
        rel_text = f" {metric} relates to {rels}." if rels else ""
        lines += [
            f"### {metric}",
            f"**Values:** {vals}",
            f"**YoY Change:** {yoy}",
            f"**Summary:** {_make_summary(d.get('comparison_summary', ''), vals[:60])}",
            f"**Trend:** {d.get('comparison_summary', '')}{rel_text}",
            "",
        ]

    # ── Quarterly Results ─────────────────────────────────────────────────────
    lines += [
        "## Quarterly Results",
        "",
        (f"Quarterly results for {sym} show near-term revenue, profit, and margin trends. "
         f"Quarterly Revenue relates to Revenue_Annual and Revenue_Growth_YoY. "
         f"Quarterly Net Profit relates to PAT_TTM and EPS trajectory. "
         f"QoQ change shows sequential momentum; YoY change shows annual growth quality."),
        "",
    ]
    for metric, d in data.get("quarterly_results", {}).items():
        qoq   = d.get("qoq_change", "N/A")
        yoy   = d.get("yoy_change", "N/A")
        qdata = d.get("quarters_data", {})
        vals  = " | ".join(f"{q}: {v}" for q, v in list(qdata.items())[:4])
        lines += [
            f"### {metric}",
            f"**Values:** {vals}",
            f"**QoQ Change:** {qoq} | **YoY Change:** {yoy}",
            f"**Summary:** {_make_summary(d.get('comparison_summary', ''), vals[:60])}",
            f"**Trend:** {d.get('comparison_summary', '')}",
            "",
        ]

    # ── Shareholding Pattern ──────────────────────────────────────────────────
    lines += [
        "## Shareholding Pattern",
        "",
        (f"Shareholding pattern for {sym} reveals promoter confidence and institutional interest. "
         f"Promoter holding relates to management confidence and dilution risk. "
         f"FII holding relates to foreign institutional interest and global sentiment. "
         f"DII holding relates to domestic mutual fund confidence. "
         f"Rising FII and DII holdings are bullish signals."),
        "",
    ]
    for category, d in data.get("shareholding_pattern", {}).items():
        change  = d.get("change", "N/A")
        pdata   = d.get("periods_data", {})
        vals    = " | ".join(f"{p}: {v}%" for p, v in list(pdata.items())[:4])
        lines += [
            f"### {category}",
            f"**Values:** {vals}",
            f"**Change:** {change}",
            f"**Summary:** {_make_summary(d.get('comparison_summary', ''), vals[:60])}",
            f"**Trend:** {d.get('comparison_summary', '')}",
            "",
        ]

    # ── Announcements ─────────────────────────────────────────────────────────
    lines += [
        "## Announcements",
        "",
        (f"Recent corporate announcements from {sym} signal strategic direction and events. "
         f"Each announcement relates to corporate governance, business expansion, or financial action. "
         f"Positive announcements conceptually relate to bullish price momentum. "
         f"Negative announcements conceptually relate to bearish market reaction."),
        "",
    ]
    for i, ann in enumerate(data.get("announcements", []), 1):
        icon = _SENTIMENT_ICON.get(ann.get("sentiment", "neutral"), "➡️")
        lines += [
            f"### Announcement {i}: {ann.get('title', 'N/A')}",
            f"**Date:** {ann.get('date', 'N/A')} | **Sentiment:** {icon} {ann.get('sentiment', 'neutral')}",
            f"**Summary:** {ann.get('summary', 'No summary available.')}",
            "",
        ]

    # ── News ──────────────────────────────────────────────────────────────────
    lines += [
        "## News",
        "",
        (f"Recent news coverage of {sym} captures market sentiment and external events. "
         f"News items relate to stock price reaction, sector developments, and investor confidence. "
         f"Bullish news conceptually relates to positive price momentum and increased buying interest. "
         f"Bearish news conceptually relates to selling pressure and reduced confidence."),
        "",
    ]
    for i, item in enumerate(data.get("news", []), 1):
        icon   = _SENTIMENT_ICON.get(item.get("sentiment", "neutral"), "➡️")
        source = item.get("source", "")
        lines += [
            f"### News {i}: {item.get('headline', 'N/A')}",
            f"**Date:** {item.get('date', 'N/A')} | **Source:** {source} | **Sentiment:** {icon} {item.get('sentiment', 'neutral')}",
            f"**Summary:** {item.get('summary', 'No summary available.')}",
            "",
        ]

    # ── Market Context ────────────────────────────────────────────────────────
    lines += [
        "## Market Context",
        "",
        (f"Market context for {sym} captures macro environment, sector trends, and market regime. "
         f"Market Regime relates to Nifty 50 trend and overall equity direction. "
         f"Sector Context relates to peer performance and sector rotation. "
         f"These contextually relate to Fundamentals valuation and Technical Indicators trend."),
        "",
    ]
    for name, d in data.get("market_context", {}).items():
        icon = _SENTIMENT_ICON.get(d.get("sentiment", "neutral"), "➡️")
        lines += [
            f"### {name}",
            f"**Value:** {d.get('value', 'N/A')} | **Sentiment:** {icon} {d.get('sentiment', 'neutral')}",
            f"**Summary:** {_make_summary(d.get('context', ''), d.get('value', ''))}",
            f"**Analysis:** {d.get('context', '')}",
            "",
        ]

    return "\n".join(lines)


# ── 6. Write output ────────────────────────────────────────────────────────────
print("[5/6] Writing output file...")
data_dir = ROOT / "data"
data_dir.mkdir(exist_ok=True)

md_path = data_dir / f"{SYMBOL}_data.md"
md_path.write_text(_build_markdown(output), encoding="utf-8")
print(f"      → {md_path}  (graphify-compatible markdown)")
print("  [OK] File written\n")


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"{'='*60}")
print(f"  PHASE 1 COMPLETE — {SYMBOL}")
print(f"  Output : data/{SYMBOL}_data.md")
print()

_sections: dict[str, int] = {
    "Fundamentals":    len(output["fundamentals"]),
    "Technicals":      len(output["technical_indicators"]),
    "Announcements":   len(output["announcements"]),
    "News":            len(output["news"]),
    "Balance Sheet":   len(output["balance_sheet"]),
    "P&L (Annual)":    len(output["profit_loss"]),
    "Cash Flow":       len(output["cash_flow"]),
    "Quarterly":       len(output["quarterly_results"]),
    "Shareholding":    len(output["shareholding_pattern"]),
    "Market Context":  len(output["market_context"]),
}
for label, count in _sections.items():
    status = "[OK]" if count > 0 else "[MISSING]"
    print(f"  {label:18s}: {count:>3}  {status}")

all_ok = all(v > 0 for v in _sections.values())
print()
print(f"  {'ALL SECTIONS POPULATED ✓' if all_ok else 'WARNING: SOME SECTIONS EMPTY'}")
print(f"{'='*60}\n")
