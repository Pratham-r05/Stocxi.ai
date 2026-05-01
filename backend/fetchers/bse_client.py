"""
bse_client.py — Async wrapper around BennyThadikaran/BseIndiaApi (bse library).

The BSE library is synchronous (requests.Session internally).
All public methods run the sync call in a thread-pool executor.

Source ID: "bse_library" (config/sources.yaml, priority 1 for fundamentals).
Confidence: 1.00 (L1 — exchange-direct data).

Capabilities:
  - fetch_scrip_code      → getScripCode(symbol)      — NSE→BSE code lookup
  - fetch_quote           → quote(scripcode)           — live OHLC + market cap
  - fetch_meta_info       → equityMetaInfo(scripcode)  — PE, EPS, ROE, PB, OPM, NPM
  - fetch_results_snapshot → resultsSnapshot(scripcode) — quarterly P&L (3 periods)
  - fetch_weekly_hl       → quoteWeeklyHL(scripcode)   — 52W high/low
  - fetch_trading_stats   → getScripTradingStats(scripcode) — market cap, deliverable
  - fetch_result_calendar → resultCalendar()           — upcoming earnings dates
  - fetch_actions         → actions(scripcode=int)     — dividends, splits, bonus

BSE code resolution order:
  1. BSE.getScripCode(symbol) — live API call
  2. config/bse_codes.yaml static fallback
  3. Raise if both fail

All methods take NSE symbol + resolve the BSE code internally (cached per symbol).
Raises on network errors or symbol not found; caller (WaterfallRunner) handles fallback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bse import BSE  # type: ignore

from backend.config import yaml_cfg

logger = logging.getLogger(__name__)

SOURCE_ID  = "bse_library"
CONFIDENCE = 1.00

_DOWNLOAD_FOLDER = "/tmp/stocxi_bse"


# ── Singleton management ──────────────────────────────────────────────────────

_bse_instance: BSE | None = None
_code_cache: dict[str, str] = {}   # NSE symbol → BSE scrip code


def _get_bse() -> BSE:
    """Return the module-level BSE singleton, creating it lazily."""
    global _bse_instance
    if _bse_instance is None:
        _bse_instance = BSE(download_folder=_DOWNLOAD_FOLDER)
        _bse_instance.__enter__()
    return _bse_instance


def close() -> None:
    """Close the BSE session — call once at app shutdown."""
    global _bse_instance
    if _bse_instance is not None:
        try:
            _bse_instance.__exit__(None, None, None)
        except Exception:
            pass
        _bse_instance = None


# ── Helper ────────────────────────────────────────────────────────────────────

async def _run_sync(fn, *args, **kwargs) -> Any:
    """Run a blocking BSE call in the default thread-pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def resolve_scrip_code(symbol: str) -> str:
    """
    Resolve NSE symbol to BSE scrip code, using a per-process cache.

    Resolution order:
      1. In-memory cache (avoids repeat API calls in same session).
      2. BSE.getScripCode(symbol) — live API call.
      3. config/bse_codes.yaml static fallback.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        BSE scrip code string (e.g. "500325").

    Raises:
        ValueError: if scrip code cannot be resolved from any source.
    """
    symbol = symbol.upper().strip()
    if symbol in _code_cache:
        return _code_cache[symbol]

    bse = _get_bse()

    # Try live API first
    try:
        code = await _run_sync(bse.getScripCode, symbol)
        if code:
            _code_cache[symbol] = str(code)
            return _code_cache[symbol]
    except Exception as exc:
        logger.debug("BSE.getScripCode(%s) failed: %s", symbol, exc)

    # Fallback to static yaml map
    static_map: dict = yaml_cfg.bse_codes
    if symbol in static_map:
        _code_cache[symbol] = str(static_map[symbol])
        logger.debug("BSE scrip code for %s resolved via bse_codes.yaml: %s",
                     symbol, _code_cache[symbol])
        return _code_cache[symbol]

    raise ValueError(
        f"BSE scrip code not found for '{symbol}'. "
        "Add it to config/bse_codes.yaml."
    )


# ── Public fetch methods ──────────────────────────────────────────────────────

async def fetch_quote(symbol: str) -> dict[str, Any]:
    """
    Fetch live OHLC quote + market cap from BSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Normalised quote dict with close, open, high, low, volume, market_cap_cr.

    Raises:
        Exception: on network error or symbol not found.
    """
    bse_code = await resolve_scrip_code(symbol)
    bse = _get_bse()
    raw: dict = await _run_sync(bse.quote, bse_code)

    if not raw:
        raise ValueError(f"BSE quote empty for {symbol} (code={bse_code})")

    # BSE quote returns: LTP, Open, High, Low, PrevClose
    close  = _to_float(raw.get("LTP") or raw.get("CurrentRate") or raw.get("close"))
    prev   = _to_float(raw.get("PrevClose") or raw.get("PrevRate") or raw.get("previousClose"))
    change = (close - prev) if (close is not None and prev is not None) else None
    change_pct = (round(change / prev * 100, 2) if (change is not None and prev) else None)

    return {
        "symbol":         symbol,
        "bse_code":       bse_code,
        "close":          close,
        "open":           _to_float(raw.get("Open") or raw.get("OpenRate") or raw.get("open")),
        "high":           _to_float(raw.get("High") or raw.get("high")),
        "low":            _to_float(raw.get("Low") or raw.get("low")),
        "volume":         _to_int(raw.get("TurnoverVolume") or raw.get("volume")),
        "previous_close": prev,
        "change":         change,
        "change_pct":     change_pct,
        "market_cap_cr":  _to_float(raw.get("Mktcap") or raw.get("MarketCap")),
        "company_name":   raw.get("CompanyName") or raw.get("companyName") or symbol,
        "isin":           raw.get("ISIN") or raw.get("isin") or "",
        "_raw":           raw,
    }


async def fetch_meta_info(symbol: str) -> dict[str, Any]:
    """
    Fetch key fundamental ratios from BSE equityMetaInfo.

    Covers: PE (consolidated preferred), EPS, ROE, PB, OPM, NPM, book value.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with pe, eps, roe, pb, opm, npm, book_value, face_value, sector.

    Raises:
        Exception: on network error or symbol not found.
    """
    bse_code = await resolve_scrip_code(symbol)
    bse = _get_bse()
    raw: dict = await _run_sync(bse.equityMetaInfo, bse_code)

    if not raw:
        raise ValueError(f"BSE equityMetaInfo empty for {symbol}")

    # Consolidated staleness guard:
    # Use consolidated figures if ConPE, ConROE, or ConPB is populated.
    # ConROE/ConPB alone are not always present (e.g. RELIANCE conglomerate structure)
    # but ConPE/ConEPS are still valid — so include ConPE in the check.
    con_pe  = _to_float(raw.get("ConPE"))
    con_roe = _to_float(raw.get("ConROE"))
    con_pb  = _to_float(raw.get("ConPB"))
    use_consolidated = (con_pe is not None) or (con_roe is not None) or (con_pb is not None)

    if use_consolidated:
        pe  = con_pe  if con_pe  is not None else _to_float(raw.get("PE"))
        eps = _to_float(raw.get("ConEPS") or raw.get("EPS"))
        roe = con_roe if con_roe is not None else _to_float(raw.get("ROE"))
    else:
        pe  = _to_float(raw.get("PE"))
        eps = _to_float(raw.get("EPS"))
        roe = _to_float(raw.get("ROE"))

    return {
        "symbol":           symbol,
        "bse_code":         bse_code,
        "pe":               pe,
        "eps":              eps,
        "roe":              roe,
        "pb":               _to_float(raw.get("PB")),
        "opm":              _to_float(raw.get("OPM")),
        "npm":              _to_float(raw.get("NPM")),
        "book_value":       _to_float(raw.get("BookValue") or raw.get("bookValue")),
        "face_value":       _to_float(raw.get("FaceValue") or raw.get("faceValue")),
        "sector":           raw.get("Sector") or raw.get("sector") or "",
        "industry":         raw.get("Industry") or raw.get("industry") or "",
        "used_consolidated": use_consolidated,
        "_raw":             raw,
    }


async def fetch_results_snapshot(symbol: str) -> dict[str, Any]:
    """
    Fetch quarterly P&L snapshot (last 3 periods) from BSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with "periods" list of {period, revenue, net_profit, eps}.

    Raises:
        Exception: on network error.
    """
    bse_code = await resolve_scrip_code(symbol)
    bse = _get_bse()
    raw = await _run_sync(bse.resultsSnapshot, scripcode=bse_code)

    if not raw:
        raise ValueError(f"BSE resultsSnapshot empty for {symbol}")

    # BSE resultsSnapshot structure:
    # {
    #   "periods": ["Dec-25", "Sep-25", "FY24-25"],
    #   "results_in_crores": {
    #     "fields": ["title", "Dec-25", "Sep-25", "FY24-25"],
    #     "data": [
    #       ["Revenue",    "139.19", "192.63", "989.07"],
    #       ["Net Profit", "12.58",  "55.11",  "109.16"],
    #       ["EPS",        "0.28",   "1.23",   "2.49"],
    #       ["OPM %",      "24.76",  "38.17",  "16.34"],
    #       ["NPM %",      "9.04",   "28.61",  "11.04"],
    #     ]
    #   }
    # }
    period_labels: list[str] = raw.get("periods", [])
    block = raw.get("results_in_crores") or raw.get("results_in_millions") or {}
    rows: list[list] = block.get("data", [])

    # Build a label → row lookup
    row_by_label: dict[str, list] = {}
    for row in rows:
        if isinstance(row, list) and len(row) >= 2:
            row_by_label[str(row[0]).lower()] = row[1:]

    def _get_field(hints: list[str], idx: int) -> float | None:
        for hint in hints:
            for label, vals in row_by_label.items():
                if hint in label and idx < len(vals):
                    return _to_float(vals[idx])
        return None

    periods = []
    for idx, label in enumerate(period_labels):
        periods.append({
            "period":     label,
            "revenue":    _get_field(["revenue", "total income", "sales"], idx),
            "net_profit": _get_field(["net profit", "pat", "profit after tax"], idx),
            "eps":        _get_field(["eps", "earnings per share"], idx),
            "opm_pct":    _get_field(["opm", "operating profit margin"], idx),
            "npm_pct":    _get_field(["npm", "net profit margin"], idx),
        })

    return {"symbol": symbol, "bse_code": bse_code, "periods": periods, "_raw": raw}


async def fetch_weekly_hl(symbol: str) -> dict[str, Any]:
    """
    Fetch 52-week high/low from BSE quoteWeeklyHL.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with high_52w, low_52w, current_price (for ratio calculation).

    Raises:
        Exception: on network error.
    """
    bse_code = await resolve_scrip_code(symbol)
    bse = _get_bse()
    raw: dict = await _run_sync(bse.quoteWeeklyHL, bse_code)

    if not raw:
        raise ValueError(f"BSE quoteWeeklyHL empty for {symbol}")

    return {
        "symbol":    symbol,
        "bse_code":  bse_code,
        "high_52w":  _to_float(raw.get("High52") or raw.get("Week52High") or raw.get("high52w")),
        "low_52w":   _to_float(raw.get("Low52") or raw.get("Week52Low") or raw.get("low52w")),
        "current":   _to_float(raw.get("CurrRate") or raw.get("current")),
        "_raw":      raw,
    }


async def fetch_trading_stats(symbol: str) -> dict[str, Any]:
    """
    Fetch trading statistics from BSE (market cap, deliverable volume, circuits).

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with market_cap_cr, deliverable_pct, upper_circuit, lower_circuit.

    Raises:
        Exception: on network error.
    """
    bse_code = await resolve_scrip_code(symbol)
    bse = _get_bse()
    raw: dict = await _run_sync(bse.getScripTradingStats, bse_code)

    if not raw:
        raise ValueError(f"BSE getScripTradingStats empty for {symbol}")

    return {
        "symbol":          symbol,
        "bse_code":        bse_code,
        "market_cap_cr":   _to_float(raw.get("MarketCap") or raw.get("marketCap")),
        "deliverable_pct": _to_float(raw.get("DeliverableQty") or raw.get("deliverable_pct")),
        "upper_circuit":   _to_float(raw.get("UpperCircuit") or raw.get("upper_circuit")),
        "lower_circuit":   _to_float(raw.get("LowerCircuit") or raw.get("lower_circuit")),
        "_raw":            raw,
    }


async def fetch_result_calendar() -> dict[str, Any]:
    """
    Fetch upcoming earnings result calendar from BSE.

    Returns:
        Dict with "events" list of {symbol, date, result_type}.

    Raises:
        Exception: on network error.
    """
    bse = _get_bse()
    raw = await _run_sync(bse.resultCalendar)

    if not raw:
        return {"events": []}

    items = raw if isinstance(raw, list) else raw.get("data", [])
    events = []
    for item in items:
        if not isinstance(item, dict):
            continue
        events.append({
            "symbol":      item.get("SCRIP_CD") or item.get("scripcode") or "",
            "company":     item.get("SCRIP_NAME") or item.get("name") or "",
            "date":        item.get("DATE") or item.get("date") or "",
            "result_type": item.get("RESULT_TYPE") or item.get("type") or "Quarterly",
        })

    return {"events": events, "_raw": raw[:10] if isinstance(raw, list) else raw}


async def fetch_actions(symbol: str) -> dict[str, Any]:
    """
    Fetch corporate actions (dividends, splits, bonus) from BSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with "actions" list.

    Raises:
        Exception: on network error.
    """
    bse_code = await resolve_scrip_code(symbol)
    bse = _get_bse()
    raw = await _run_sync(bse.actions, scripcode=int(bse_code))

    if not raw:
        return {"symbol": symbol, "actions": []}

    items = raw if isinstance(raw, list) else []
    actions = [
        {
            "ex_date":     item.get("Ex_date") or item.get("ExDate") or item.get("exDate") or "",
            "record_date": item.get("RecordDate") or "",
            "purpose":     item.get("Purpose") or item.get("subject") or "",
            "details":     item.get("Details") or item.get("remarks") or "",
        }
        for item in items if isinstance(item, dict)
    ]

    return {"symbol": symbol, "bse_code": bse_code, "actions": actions, "_raw": raw}


# ── Type coercers ─────────────────────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    """Coerce value to float, returning None on failure."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> int | None:
    """Coerce value to int, returning None on failure."""
    if v is None:
        return None
    try:
        return int(str(v).replace(",", "").split(".")[0].strip())
    except (ValueError, TypeError):
        return None
