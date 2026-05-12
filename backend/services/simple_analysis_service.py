"""
simple_analysis_service.py — Simplified AI analysis pipeline for the frontend.

Pipeline per request:
  1. Run fetch_phase1_data.py as subprocess → creates/refreshes data/{SYMBOL}_data.md
     (skipped if file is < DATA_FRESHNESS_H hours old)
  2. Build 3D knowledge graph HTML using build_knowledge_graph functions
  3. Call Gemini to generate Markdown analysis report
  4. Wrap Markdown in HTML template; save both files to analysis-out/{SYMBOL}/
  5. Return (analysis_html: str, kg_html: str, cached: bool)

Risk → user_level mapping:
  conservative → beginner
  moderate     → medium
  aggressive   → pro
"""

from __future__ import annotations

import os 
import asyncio
import logging
import sys
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from services.symbol_service import canonicalize_symbol

logger = logging.getLogger(__name__)

# _ROOT       = Path(__file__).parents[2]          # stocxi/
# _DATA_DIR   = _ROOT / "data"
# _OUT_DIR    = _ROOT / "analysis-out"
_ROOT = Path(os.getenv("APP_ROOT", str(Path(__file__).parents[2])))
_DEFAULT_DATA_DIR = "/tmp/data" if os.getenv("VERCEL") else str(_ROOT / "data")
_DATA_DIR   = Path(os.getenv("DATA_DIR", _DEFAULT_DATA_DIR))
_OUT_DIR    = Path(os.getenv("ANALYSIS_OUT_DIR", "/tmp/analysis-out"))
DATA_FRESHNESS_H = 12   # re-fetch if data file is older than this


UserLevel = Literal["beginner", "medium", "pro"]
Horizon   = Literal["short", "medium", "long"]

RISK_TO_LEVEL: dict[str, UserLevel] = {
    "conservative": "beginner",
    "moderate":     "medium",
    "aggressive":   "pro",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _data_path(symbol: str) -> Path:
    return _DATA_DIR / f"{symbol.upper()}_data.md"


def _out_paths(symbol: str, horizon: Horizon, level: UserLevel, today: str) -> tuple[Path, Path]:
    """Return (analysis_html_path, kg_html_path)."""
    sym_dir = _OUT_DIR / symbol.upper()
    sym_dir.mkdir(parents=True, exist_ok=True)
    analysis = sym_dir / f"{horizon}_{level}_{today}.html"
    kg        = sym_dir / f"kg_{horizon}_{today}.html"
    return analysis, kg


def _is_fresh(path: Path, max_age_h: float) -> bool:
    if not path.exists():
        return False
    age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
    return age_h < max_age_h


def _analysis_html_template(md_text: str, symbol: str, horizon: Horizon, level: UserLevel) -> str:
    """Wrap Gemini Markdown in a styled, self-contained HTML page."""
    label_h = {"short": "Short-Term (1–3M)", "medium": "Medium-Term (3M–1Y)", "long": "Long-Term (1–5Y)"}
    # Escape backticks so the JS template literal is safe
    safe_md = md_text.replace("`", "\\`").replace("${", "\\${")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{symbol.upper()} — {label_h[horizon]} Analysis ({level.capitalize()})</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
           max-width: 900px; margin: 16px auto; padding: 0 16px;
           background: #09090b; color: #d4d4d8; line-height: 1.8; font-size: 16px; }}
    h1   {{ color: #ffffff; border-bottom: 1px solid #27272a; padding-bottom: 10px; font-size: 2.25rem; font-weight: 800; letter-spacing: -0.025em; }}
    h2   {{ color: #f4f4f5; margin-top: 2.5em; font-size: 1.5rem; font-weight: 700; letter-spacing: -0.025em; }}
    h3   {{ color: #e4e4e7; font-size: 1.25rem; font-weight: 600; margin-top: 2em; }}
    h4   {{ color: #e4e4e7; font-weight: 600; }}
    p    {{ margin: 1.25em 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 2em 0; font-size: 0.95em; }}
    th   {{ background: #18181b; color: #f4f4f5; padding: 12px; text-align: left; border: 1px solid #27272a; }}
    td   {{ padding: 12px; border: 1px solid #27272a; }}
    tr:hover td {{ background: #18181b; }}
    code {{ background: #18181b; padding: 3px 6px; border-radius: 6px; font-size: 0.88em; color: #a78bfa; border: 1px solid #27272a; }}
    pre  {{ background: #000000; padding: 20px; border-radius: 12px; overflow-x: auto; border: 1px solid #27272a; }}
    blockquote {{ border-left: 4px solid #6366f1; padding-left: 20px; color: #a1a1aa; margin: 1.5em 0; font-style: italic; }}
    a    {{ color: #818cf8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    strong {{ color: #ffffff; font-weight: 600; }}
    ul, ol {{ padding-left: 1.5em; margin: 1.25em 0; }}
    li   {{ margin: 0.5em 0; }}
    hr   {{ border: none; border-top: 1px solid #27272a; margin: 3em 0; }}
  </style>
</head>
<body>
  <div id="content"></div>
  <script>
    const md = `{safe_md}`;
    document.getElementById('content').innerHTML = marked.parse(md);
  </script>
</body>
</html>"""


# ── Subprocess: fetch_phase1_data.py ─────────────────────────────────────────

async def _run_fetch_phase1(symbol: str, horizon: Horizon) -> None:
    """Run fetch_phase1_data.py as a subprocess. Raises RuntimeError on failure."""
    logger.info("simple_analysis: running fetch_phase1_data for %s (%s)", symbol, horizon)
    script_path = _ROOT / "fetch_phase1_data.py"
    if not script_path.exists():
        logger.warning("simple_analysis: fetch_phase1_data.py missing, using service fallback")
        await _write_fallback_data_file(symbol, horizon)
        return

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        symbol.upper(), horizon,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_ROOT),
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=360)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("fetch_phase1_data timed out after 6 minutes")
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")[-800:]
        if "fetch_phase1_data.py" in msg and "No such file" in msg:
            logger.warning("simple_analysis: fetch_phase1_data unavailable, using service fallback")
            await _write_fallback_data_file(symbol, horizon)
            return
        raise RuntimeError(f"fetch_phase1_data failed (exit {proc.returncode}): {msg}")
    logger.info("simple_analysis: fetch_phase1_data complete for %s", symbol)


def _compact(value: object, limit: int = 600) -> str:
    text = json.dumps(value, ensure_ascii=True, default=str)
    return text[:limit] + ("..." if len(text) > limit else "")


def _signal(value: object, bullish_high: bool = True) -> str:
    try:
        number = float(str(value).replace(",", "").replace("%", ""))
    except Exception:
        return "neutral"
    if bullish_high:
        if number > 0:
            return "bullish"
        if number < 0:
            return "bearish"
    else:
        if number > 0:
            return "bearish"
        if number < 0:
            return "bullish"
    return "neutral"


def _node(title: str, value: object, sentiment: str, analysis: str) -> str:
    return (
        f"### {title}\n"
        f"**Value:** {value} | **Sentiment:** {sentiment}\n"
        f"**Analysis:** {analysis}\n"
    )


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("announcements", "items", "results", "news"):
            items = value.get(key)
            if isinstance(items, list):
                return items
    return []


async def _write_fallback_data_file(symbol: str, horizon: Horizon) -> None:
    """Create the analysis markdown directly from backend services."""
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    if str(_ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(_ROOT / "backend"))

    from services.yfinance_service import get_price_and_fundamentals
    from services.technicals_service import calculate_technicals
    from services.screener_service import get_financials
    from services.news_service import get_news
    from fetchers import nse_client

    overview, technicals, financials, news, announcements = await asyncio.gather(
        get_price_and_fundamentals(symbol),
        calculate_technicals(symbol),
        get_financials(symbol),
        get_news(symbol),
        nse_client.fetch_announcements(symbol, limit=5),
        return_exceptions=True,
    )

    if isinstance(overview, Exception):
        overview = {}
    if isinstance(technicals, Exception):
        technicals = {}
    if isinstance(financials, Exception):
        financials = {}
    if isinstance(news, Exception):
        news = []
    if isinstance(announcements, Exception):
        announcements = []

    overview_d = _as_dict(overview)
    technicals_d = _as_dict(technicals)
    financials_d = _as_dict(financials)
    news_l = _as_list(news)
    announcements_l = _as_list(announcements)

    sector = str(overview_d.get("sector") or overview_d.get("industry") or "unknown")
    today = str(date.today())

    lines: list[str] = [
        "---",
        f"symbol: {symbol.upper()}",
        f"captured_at: {today}",
        f"horizon: {horizon}",
        f"sector: {sector}",
        "author: stocxi_service_fallback",
        "---",
        "",
        f"# {symbol.upper()} - Stock Analysis Data",
        "",
        "## Fundamentals",
        _node("Price", overview_d.get("price"), "neutral", "Price relates to Market_Cap, PE_Ratio, EPS."),
        _node("Market_Cap", overview_d.get("market_cap"), "neutral", "Market_Cap relates to Price, PE_Ratio, Revenue_Annual."),
        _node("PE_Ratio", overview_d.get("pe_ratio"), "neutral", "PE_Ratio relates to EPS and valuation."),
        _node("PB_Ratio", overview_d.get("pb_ratio"), "neutral", "PB_Ratio relates to book value and valuation."),
        _node("ROE", overview_d.get("roe"), _signal(overview_d.get("roe")), "ROE relates to profitability and capital efficiency."),
        _node("EPS", overview_d.get("eps"), _signal(overview_d.get("eps")), "EPS relates to PE_Ratio and earnings quality."),
        "",
        "## Technical Indicators",
    ]

    for key, value in technicals_d.items():
        if key.endswith("_signal"):
            continue
        signal = technicals_d.get(f"{key}_signal", "neutral")
        lines.append(_node(key.upper(), value, str(signal), f"{key.upper()} relates to price momentum and trend quality."))

    lines.extend(["", "## Balance Sheet"])
    lines.append(_node("Balance_Sheet", _compact(financials_d.get("balance_sheet", {})), "neutral", "Balance sheet relates to debt, assets, and net worth."))
    lines.extend(["", "## Profit and Loss"])
    lines.append(_node("Profit_Loss", _compact(financials_d.get("profit_loss", {})), "neutral", "Profit and loss relates to sales, expenses, margins, and earnings."))
    lines.extend(["", "## Cash Flow"])
    lines.append(_node("Cash_Flow", _compact(financials_d.get("cash_flow", {})), "neutral", "Cash flow relates to earnings quality and reinvestment ability."))
    lines.extend(["", "## Quarterly Results"])
    lines.append(_node("Quarterly_Results", _compact(financials_d.get("quarterly_results", {})), "neutral", "Quarterly results relate to recent growth and margin direction."))
    lines.extend(["", "## Shareholding Pattern"])
    lines.append(_node("Shareholding", _compact(financials_d.get("shareholding", {})), "neutral", "Shareholding relates to promoter, FII, DII, and public ownership."))

    lines.extend(["", "## News"])
    for idx, item in enumerate(news_l[:8], start=1):
        item = _as_dict(item)
        title = item.get("title") or item.get("headline") or f"News_{idx}"
        summary = item.get("summary") or item.get("description") or title
        lines.append(_node(f"News_{idx}", title, "neutral", str(summary)))

    lines.extend(["", "## Announcements"])
    for idx, item in enumerate(announcements_l[:5], start=1):
        item = _as_dict(item)
        title = item.get("desc") or item.get("title") or item.get("subject") or f"Announcement_{idx}"
        lines.append(_node(f"Announcement_{idx}", title, "neutral", _compact(item, 300)))

    lines.extend(["", "## Market Context"])
    lines.append(_node("Sector", sector, "neutral", "Sector context relates to peer performance and demand cycle."))

    data_path = _data_path(symbol)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("simple_analysis: fallback data file written: %s", data_path)


# ── Knowledge graph builder ───────────────────────────────────────────────────

def _build_kg_html_sync(symbol: str) -> str:
    """Build KG HTML synchronously using build_knowledge_graph module."""
    # Add project root to path so build_knowledge_graph is importable
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    import importlib
    bkg = importlib.import_module("build_knowledge_graph")

    data_path = _data_path(symbol)
    meta, nodes = bkg.parse_md(data_path)
    graph_data  = bkg.build_graph_data(symbol.upper(), meta, nodes)
    return bkg.render_html(symbol.upper(), meta, graph_data)


async def _build_kg_html(symbol: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _build_kg_html_sync, symbol)


# ── Gemini analysis ───────────────────────────────────────────────────────────

def _run_gemini_sync(symbol: str, horizon: Horizon, level: UserLevel, kg_link: str) -> str:
    """Call gemini_analysis.run_analysis in a thread-safe way."""
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    if str(_ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(_ROOT / "backend"))

    try:
        from backend.analysis.gemini_analysis import run_analysis  # type: ignore
    except ModuleNotFoundError:
        from analysis.gemini_analysis import run_analysis  # type: ignore
    return run_analysis(symbol.upper(), horizon, level, kg_link=kg_link)


async def _run_gemini(symbol: str, horizon: Horizon, level: UserLevel, kg_link: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_gemini_sync, symbol, horizon, level, kg_link)


# ── Public entry point ────────────────────────────────────────────────────────

async def generate(
    symbol:  str,
    horizon: str,
    risk:    str,
) -> dict:
    """
    Run the simplified analysis pipeline for one stock.

    Args:
        symbol:  NSE ticker (e.g. "ADANIPOWER")
        horizon: "short" | "medium" | "long"
        risk:    "conservative" | "moderate" | "aggressive"

    Returns:
        dict with keys: analysis_html (str), kg_html (str), cached (bool),
        symbol (str), horizon (str), level (str), generated_on (str)

    Raises:
        ValueError:   invalid horizon/risk.
        FileNotFoundError: if data file can't be created.
        RuntimeError: if fetch_phase1 or Gemini fails.
    """
    symbol  = canonicalize_symbol(symbol)
    horizon = horizon.lower()
    risk    = risk.lower()

    if horizon not in ("short", "medium", "long"):
        raise ValueError(f"Invalid horizon: {horizon}")
    level: UserLevel = RISK_TO_LEVEL.get(risk, "medium")

    today   = str(date.today())
    data_p  = _data_path(symbol)
    ana_p, kg_p = _out_paths(symbol, horizon, level, today)

    # ── Serve from cache if both HTML files exist and were made today ──────────
    if _is_fresh(ana_p, 23) and _is_fresh(kg_p, 23):
        logger.info("simple_analysis: cache HIT for %s/%s/%s", symbol, horizon, level)
        return {
            "symbol": symbol, "horizon": horizon, "level": level,
            "generated_on": today, "cached": True,
            "analysis_html": ana_p.read_text(encoding="utf-8"),
            "kg_html":       kg_p.read_text(encoding="utf-8"),
        }

    # ── Step 1: ensure data file is fresh ─────────────────────────────────────
    if not _is_fresh(data_p, DATA_FRESHNESS_H):
        await _run_fetch_phase1(symbol, horizon)

    if not data_p.exists():
        raise FileNotFoundError(
            f"Data file not found after fetch: {data_p}. "
            f"Run: python fetch_phase1_data.py {symbol} {horizon}"
        )

    # ── Step 2: build knowledge graph ─────────────────────────────────────────
    kg_link = f"/stock/{symbol}/knowledge"
    try:
        kg_html = await _build_kg_html(symbol)
        kg_p.write_text(kg_html, encoding="utf-8")
        logger.info("simple_analysis: KG HTML saved → %s", kg_p)
    except Exception as kg_exc:
        logger.warning("simple_analysis: KG build failed (non-fatal) — %s", kg_exc)
        kg_html = "<p style='color:#94a3b8'>Knowledge graph unavailable.</p>"

    # ── Step 3: Gemini analysis ───────────────────────────────────────────────
    report_md = await _run_gemini(symbol, horizon, level, kg_link)
    analysis_html = _analysis_html_template(report_md, symbol, horizon, level)
    ana_p.write_text(analysis_html, encoding="utf-8")
    logger.info("simple_analysis: analysis HTML saved → %s", ana_p)

    return {
        "symbol": symbol, "horizon": horizon, "level": level,
        "generated_on": today, "cached": False,
        "analysis_html": analysis_html,
        "kg_html":       kg_html,
    }
