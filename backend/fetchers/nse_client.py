"""
nse_client.py — Async wrapper around BennyThadikaran/NseIndiaApi (nse library).

The NSE library is synchronous and uses a requests.Session internally.
Every public method here wraps a sync NSE call in run_in_executor so FastAPI
coroutines are never blocked.

Source ID: "nse_library" (config/sources.yaml, priority 1 for technicals).
Confidence: 1.00 (L1 — exchange-direct data).

Capabilities:
  - fetch_meta_info  → equityMetaInfo(symbol)  — company name, industry, ISIN, listing date
  - fetch_quote      → equityQuote(symbol)    — live price, change%, VWAP, volumes
  - fetch_ohlcv      → fetch_equity_historical_data(symbol, from_date, to_date)
  - fetch_shareholding → shareholding(symbol) — promoter/FII/DII/retail breakdown
  - fetch_announcements → announcements() + filter by symbol
  - fetch_board_meetings → boardMeetings(symbol=symbol)
  - fetch_actions    → actions(symbol=symbol) — dividends, splits, bonus
  - fetch_annual_reports → annual_reports(symbol)

All methods return a plain dict (never raise on normal data absence).
Raises on library-level errors (symbol not found, network timeout) so the
WaterfallRunner can fall through to the next level.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from nse import NSE  # type: ignore

logger = logging.getLogger(__name__)

SOURCE_ID  = "nse_library"
CONFIDENCE = 1.00

# NSE library download folder — only used for bhavcopy / bulk downloads
_DOWNLOAD_FOLDER = "/tmp/stocxi_nse"


# ── Singleton management ──────────────────────────────────────────────────────

_nse_instance: NSE | None = None


def _get_nse() -> NSE:
    """
    Return the module-level NSE singleton, creating it lazily on first call.
    The NSE instance holds an internal requests.Session that we reuse.
    """
    global _nse_instance
    if _nse_instance is None:
        _nse_instance = NSE(download_folder=_DOWNLOAD_FOLDER)
        _nse_instance.__enter__()   # initialise the session
    return _nse_instance


def close() -> None:
    """Close the NSE session — call once at app shutdown."""
    global _nse_instance
    if _nse_instance is not None:
        try:
            _nse_instance.__exit__(None, None, None)
        except Exception:
            pass
        _nse_instance = None


# ── Helper ────────────────────────────────────────────────────────────────────

async def _run_sync(fn, *args, **kwargs) -> Any:
    """Run a blocking NSE call in the default thread-pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ── Public fetch methods ──────────────────────────────────────────────────────

async def fetch_meta_info(symbol: str) -> dict[str, Any]:
    """
    Fetch company metadata from NSE equityMetaInfo.

    Provides sector/industry classification directly from NSE — more reliable than
    any hardcoded map, especially for small-cap and SME stocks.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with company_name, industry, isin, listing_date, segment.

    Raises:
        Exception: on network error or symbol not found.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw: dict = await _run_sync(nse.equityMetaInfo, symbol)
    if not raw:
        raise ValueError(f"NSE equityMetaInfo empty for {symbol}")
    return {
        "symbol":       symbol,
        "company_name": raw.get("companyName") or symbol,
        "industry":     raw.get("industry") or "",
        "isin":         raw.get("isin") or "",
        "listing_date": raw.get("listingDate") or "",
        "segment":      raw.get("segment") or "",
        "_raw":         raw,
    }


async def fetch_quote(symbol: str) -> dict[str, Any]:
    """
    Fetch live equity quote from NSE.

    Returns flat dict with keys: close, open, high, low, volume, previousClose,
    change, changePercent, vwap, weekHigh52, weekLow52, upper_circuit,
    lower_circuit, market_cap_cr, company_name, isin.

    Args:
        symbol: NSE ticker in uppercase (e.g. "RELIANCE").

    Returns:
        Normalised quote dict.

    Raises:
        Exception: on network error or symbol not found.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw: dict = await _run_sync(nse.equityQuote, symbol)

    # equityQuote returns a flat dict with keys like close/open/high/low
    price = raw.get("close") or raw.get("lastPrice") or raw.get("priceInfo", {}).get("lastPrice")
    if price is None:
        raise ValueError(f"NSE equityQuote returned no price for {symbol}")

    return {
        "symbol":         symbol,
        "close":          _to_float(price),
        "open":           _to_float(raw.get("open")),
        "high":           _to_float(raw.get("high")),
        "low":            _to_float(raw.get("low")),
        "volume":         _to_int(raw.get("totalTradedVolume") or raw.get("volume")),
        "previous_close": _to_float(raw.get("previousClose") or raw.get("previousClosePrice")),
        "change":         _to_float(raw.get("change")),
        "change_pct":     _to_float(raw.get("pChange") or raw.get("percentChange")),
        "vwap":           _to_float(raw.get("vwap")),
        "week_high_52":   _to_float(raw.get("weekHighLow52", {}).get("max") if isinstance(raw.get("weekHighLow52"), dict) else raw.get("weekHigh52")),
        "week_low_52":    _to_float(raw.get("weekHighLow52", {}).get("min") if isinstance(raw.get("weekHighLow52"), dict) else raw.get("weekLow52")),
        "upper_circuit":  _to_float(raw.get("upperCP") or raw.get("ucLimit")),
        "lower_circuit":  _to_float(raw.get("lowerCP") or raw.get("lcLimit")),
        "market_cap_cr":  _to_float(raw.get("totalMarketCap") or raw.get("marketCap")),
        "company_name":   raw.get("companyName") or raw.get("name") or symbol,
        "isin":           raw.get("isin") or "",
        "_raw":           raw,
    }


async def fetch_ohlcv(
    symbol: str,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """
    Fetch daily OHLCV history from NSE.

    Column names returned by NSE fetch_equity_historical_data:
      open=chOpeningPrice, high=chTradeHighPrice, low=chTradeLowPrice,
      close=chClosingPrice, volume=chTotTradedQty, date=CH_TIMESTAMP

    Args:
        symbol: NSE ticker in uppercase.
        from_date: Start date (inclusive).
        to_date: End date (inclusive).

    Returns:
        Dict with "rows" (list of dicts, newest first) and "symbol".

    Raises:
        Exception: on network error or empty response.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw = await _run_sync(nse.fetch_equity_historical_data, symbol,
                          from_date=from_date, to_date=to_date)

    if not raw or not isinstance(raw, list):
        raise ValueError(f"NSE returned empty OHLCV for {symbol}")

    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append({
            "date":   item.get("CH_TIMESTAMP") or item.get("chTimestamp") or item.get("mtimestamp") or "",
            "open":   _to_float(item.get("chOpeningPrice") or item.get("open")),
            "high":   _to_float(item.get("chTradeHighPrice") or item.get("high")),
            "low":    _to_float(item.get("chTradeLowPrice") or item.get("low")),
            "close":  _to_float(item.get("chClosingPrice") or item.get("close")),
            "volume": _to_int(item.get("chTotTradedQty") or item.get("volume")),
        })

    if not rows:
        raise ValueError(f"NSE OHLCV rows all malformed for {symbol}")

    return {"symbol": symbol, "rows": rows}


async def fetch_index_ohlcv(
    index_name: str,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """
    Fetch daily OHLCV history for an NSE index (e.g. "NIFTY 50").

    NSE's index history API caps at ~70 rows per request, so this function
    automatically chunks the date range into 90-day windows and concatenates
    results to satisfy long lookbacks (e.g. 400 days for SMA200).

    Field mapping from NSE response:
      EOD_OPEN_INDEX_VAL, EOD_HIGH_INDEX_VAL, EOD_LOW_INDEX_VAL,
      EOD_CLOSE_INDEX_VAL, HIT_TRADED_QTY, EOD_TIMESTAMP

    Args:
        index_name: NSE index name, e.g. "NIFTY 50".
        from_date:  Start date (inclusive).
        to_date:    End date (inclusive).

    Returns:
        Dict with "rows" (list of dicts) and "symbol".

    Raises:
        ValueError: on empty or malformed response.
    """
    from datetime import timedelta
    nse = _get_nse()
    CHUNK_DAYS = 90

    # Build non-overlapping 90-day windows covering [from_date, to_date]
    chunks: list[tuple[date, date]] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), to_date)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)

    all_raw: list[dict] = []
    seen_dates: set[str] = set()
    for c_start, c_end in chunks:
        try:
            chunk = await _run_sync(nse.fetch_historical_index_data, index_name,
                                    c_start, c_end)
            if isinstance(chunk, list):
                for item in chunk:
                    ts = item.get("EOD_TIMESTAMP", "")
                    if ts not in seen_dates:
                        seen_dates.add(ts)
                        all_raw.append(item)
        except Exception as exc:
            logger.warning("fetch_index_ohlcv chunk %s–%s failed: %s", c_start, c_end, exc)

    if not all_raw:
        raise ValueError(f"NSE returned empty index OHLCV for {index_name}")

    rows = []
    for item in all_raw:
        if not isinstance(item, dict):
            continue
        rows.append({
            "date":   item.get("EOD_TIMESTAMP") or "",
            "open":   _to_float(item.get("EOD_OPEN_INDEX_VAL")),
            "high":   _to_float(item.get("EOD_HIGH_INDEX_VAL")),
            "low":    _to_float(item.get("EOD_LOW_INDEX_VAL")),
            "close":  _to_float(item.get("EOD_CLOSE_INDEX_VAL")),
            "volume": _to_int(item.get("HIT_TRADED_QTY")),
        })

    if not rows:
        raise ValueError(f"NSE index OHLCV rows all malformed for {index_name}")

    return {"symbol": index_name, "rows": rows}


async def fetch_shareholding(symbol: str) -> dict[str, Any]:
    """
    Fetch shareholding pattern from NSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with promoter, fii, dii, retail, others percentages and raw data.

    Raises:
        Exception: on network error or data not available.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw = await _run_sync(nse.shareholding, symbol)

    if not raw:
        raise ValueError(f"NSE shareholding empty for {symbol}")

    # NSE shareholding() returns a list of historical entries across formats.
    # Prefer most-recent "NEW_1" entry (current SEBI-mandated format).
    # Fields: pr_and_prgrp = promoter+group %, public_val = public (retail+FII+DII) %.
    if isinstance(raw, list):
        new1_entries = [r for r in raw if isinstance(r, dict) and r.get("desc") == "NEW_1"]
        entry = new1_entries[0] if new1_entries else (raw[0] if raw else {})
    else:
        entry = raw

    parsed: dict[str, Any] = {"period": entry.get("date") or entry.get("period") or ""}

    promoter = _to_float(entry.get("pr_and_prgrp"))
    public   = _to_float(entry.get("public_val"))

    if promoter is not None:
        parsed["promoter"] = round(promoter, 2)
    if public is not None:
        parsed["retail"] = round(public, 2)   # public_val = retail+FII+DII combined

    # Older entry formats use a nested categories list — try as fallback
    if promoter is None and public is None:
        categories = entry.get("categories") or entry.get("shareholdingPattern") or []
        _KEY_MAP = {
            "Promoter": "promoter", "Promoter Group": "promoter",
            "FII": "fii", "FPI": "fii", "Foreign Institutional Investors": "fii",
            "DII": "dii", "Domestic Institutional Investors": "dii",
            "Mutual Funds": "mutual_funds",
            "Public": "retail", "Others": "others", "Non-institutions": "retail",
        }
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            name = cat.get("name") or cat.get("category") or ""
            pct  = _to_float(cat.get("percentageHolding") or cat.get("pct"))
            key  = _KEY_MAP.get(name)
            if key and pct is not None:
                parsed[key] = round((parsed.get(key) or 0.0) + pct, 2)

    if not any(k in parsed for k in ("promoter", "retail", "fii", "dii")):
        raise ValueError(f"NSE shareholding: no usable data extracted for {symbol}")

    parsed["_raw"] = raw
    return parsed


async def fetch_announcements(symbol: str, limit: int = 20) -> dict[str, Any]:
    """
    Fetch corporate announcements from NSE (market-wide, filtered by symbol).

    Args:
        symbol: NSE ticker in uppercase.
        limit: Max announcements to return.

    Returns:
        Dict with "items" list of announcement dicts.

    Raises:
        Exception: on network error.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw = await _run_sync(nse.announcements)   # returns all recent market-wide

    if not isinstance(raw, list):
        raise ValueError("NSE announcements() did not return a list")

    items = [
        {
            "title":    a.get("desc") or a.get("attchmntText") or "",
            "date":     a.get("dt") or a.get("date") or "",
            "category": a.get("desc") or "",
            "pdf_url":  a.get("attchmntFile") or "",
            "symbol":   symbol,
            "source":   SOURCE_ID,
        }
        for a in raw
        if isinstance(a, dict) and str(a.get("symbol", "")).upper() == symbol
    ][:limit]

    if not items:
        # Empty is OK — stock may have no recent announcements
        return {"symbol": symbol, "items": [], "_raw": raw[:5]}

    return {"symbol": symbol, "items": items, "_raw": raw[:5]}


async def fetch_board_meetings(symbol: str) -> dict[str, Any]:
    """
    Fetch upcoming/recent board meeting schedule from NSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with "meetings" list.

    Raises:
        Exception: on network error.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw = await _run_sync(nse.boardMeetings, symbol=symbol)

    if not raw:
        return {"symbol": symbol, "meetings": []}

    meetings = []
    for item in (raw if isinstance(raw, list) else [raw]):
        if not isinstance(item, dict):
            continue
        meetings.append({
            "date":    item.get("bm_date") or item.get("meetingDate") or "",
            "purpose": item.get("bm_purpose") or item.get("purpose") or "",
            "symbol":  symbol,
        })

    return {"symbol": symbol, "meetings": meetings, "_raw": raw}


async def fetch_actions(symbol: str) -> dict[str, Any]:
    """
    Fetch corporate actions (dividends, splits, bonus) from NSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with "actions" list.

    Raises:
        Exception: on network error.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw = await _run_sync(nse.actions, symbol=symbol)

    if not raw:
        return {"symbol": symbol, "actions": []}

    actions = []
    for item in (raw if isinstance(raw, list) else [raw]):
        if not isinstance(item, dict):
            continue
        actions.append({
            "ex_date":   item.get("exDate") or item.get("ex_date") or "",
            "purpose":   item.get("subject") or item.get("purpose") or "",
            "facevalue": _to_float(item.get("faceVal")),
            "symbol":    symbol,
        })

    return {"symbol": symbol, "actions": actions, "_raw": raw}


async def fetch_annual_reports(symbol: str) -> dict[str, Any]:
    """
    Fetch list of annual report URLs from NSE.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with "reports" list of {year, url}.

    Raises:
        Exception: on network error.
    """
    symbol = symbol.upper().strip()
    nse = _get_nse()
    raw = await _run_sync(nse.annual_reports, symbol)

    if not raw:
        return {"symbol": symbol, "reports": []}

    reports = []
    for item in (raw if isinstance(raw, list) else [raw]):
        if not isinstance(item, dict):
            continue
        reports.append({
            "year": item.get("year") or item.get("fromYr") or "",
            "url":  item.get("fileName") or item.get("url") or "",
        })

    return {"symbol": symbol, "reports": reports}


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
