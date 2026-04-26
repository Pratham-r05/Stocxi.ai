"""
yfinance_client.py — yfinance OHLCV fallback for NSE/BSE stocks.

Use ONLY as an OHLCV fallback when the NSE library is unavailable.
Do NOT use yfinance for fundamentals — BSE/Screener are more accurate
for Indian stocks and yfinance ratios can be stale or US-GAAP formatted.

Source IDs (config/sources.yaml):
  "yfinance"      → confidence 0.70 — standard .NS/.BO suffix attempt
  "yfinance_alt"  → confidence 0.70 — alt tickers from config/alt_tickers.yaml

Ticker resolution waterfall:
  1. {SYMBOL}.NS
  2. {SYMBOL}.BO
  3. alt_tickers.yaml ns entry (if present)
  4. alt_tickers.yaml bo entry (if present)
  → Raises ValueError if all four fail or return empty OHLCV.

yfinance uses a network-intensive download. All calls run in thread-pool
executor to avoid blocking the async event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import yfinance as yf  # type: ignore

from backend.config import yaml_cfg

logger = logging.getLogger(__name__)

SOURCE_ID_MAIN = "yfinance"
SOURCE_ID_ALT  = "yfinance_alt"
CONFIDENCE     = 0.70


# ── OHLCV fetch ───────────────────────────────────────────────────────────────

async def fetch_ohlcv(
    symbol: str,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """
    Fetch daily OHLCV history via yfinance with .NS → .BO → alt ticker fallback.

    Args:
        symbol:    NSE ticker in uppercase (e.g. "RELIANCE").
        from_date: Start date (inclusive).
        to_date:   End date (inclusive — yfinance end is exclusive, adjusted +1d).

    Returns:
        Dict with "rows" (list of dicts, newest first), "symbol", "ticker_used",
        and "source_id" ("yfinance" or "yfinance_alt").

    Raises:
        ValueError: all ticker variants returned empty OHLCV.
    """
    symbol = symbol.upper().strip()
    tickers = _build_ticker_list(symbol)
    loop = asyncio.get_running_loop()

    for ticker, source_id in tickers:
        try:
            rows = await loop.run_in_executor(
                None,
                lambda t=ticker: _download_ohlcv(t, from_date, to_date),
            )
            if rows:
                logger.debug("yfinance OHLCV OK: ticker=%s rows=%d", ticker, len(rows))
                return {
                    "symbol":      symbol,
                    "ticker_used": ticker,
                    "source_id":   source_id,
                    "rows":        rows,
                }
            logger.debug("yfinance OHLCV empty: ticker=%s", ticker)
        except Exception as exc:
            logger.debug("yfinance OHLCV failed: ticker=%s error=%s", ticker, exc)

    raise ValueError(
        f"yfinance returned empty OHLCV for '{symbol}' across all ticker variants: "
        + ", ".join(t for t, _ in tickers)
    )


async def fetch_quote(symbol: str) -> dict[str, Any]:
    """
    Fetch last trading day's closing price via yfinance.

    Used only as a tertiary price fallback when NSE and BSE are unavailable.

    Args:
        symbol: NSE ticker in uppercase.

    Returns:
        Dict with close, open, high, low, volume, ticker_used, source_id.

    Raises:
        ValueError: all ticker variants returned no price data.
    """
    symbol = symbol.upper().strip()
    tickers = _build_ticker_list(symbol)
    loop = asyncio.get_running_loop()

    for ticker, source_id in tickers:
        try:
            info = await loop.run_in_executor(
                None,
                lambda t=ticker: _get_fast_info(t),
            )
            if info and info.get("close"):
                return {
                    "symbol":      symbol,
                    "ticker_used": ticker,
                    "source_id":   source_id,
                    **info,
                }
        except Exception as exc:
            logger.debug("yfinance quote failed: ticker=%s error=%s", ticker, exc)

    raise ValueError(
        f"yfinance returned no price for '{symbol}' across all ticker variants: "
        + ", ".join(t for t, _ in tickers)
    )


# ── Sync helpers (run in executor) ────────────────────────────────────────────

def _download_ohlcv(
    ticker: str,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    """
    Download OHLCV via yfinance.download().

    yfinance 'end' is exclusive, so we add 1 day to include to_date.
    Returns list of row dicts (newest first) or empty list on failure.
    """
    import pandas as pd
    from datetime import timedelta

    end = to_date + timedelta(days=1)
    try:
        df = yf.download(
            ticker,
            start=from_date.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as exc:
        logger.debug("yf.download failed: ticker=%s error=%s", ticker, exc)
        return []

    if df is None or df.empty:
        return []

    # Flatten multi-level columns (yfinance 0.2.x returns MultiIndex when
    # downloading a single ticker — columns like ('Close', 'RELIANCE.NS'))
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df.reset_index().rename(columns=str.lower)
    df = df.sort_values("date", ascending=False)

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "date":   str(row.get("date", ""))[:10],
            "open":   _to_float(row.get("open")),
            "high":   _to_float(row.get("high")),
            "low":    _to_float(row.get("low")),
            "close":  _to_float(row.get("close")),
            "volume": _to_int(row.get("volume")),
        })

    return rows


def _get_fast_info(ticker: str) -> dict[str, Any]:
    """
    Get current price from yfinance Ticker.fast_info (cheaper than history download).
    Returns dict with close, open, high, low, volume or empty dict on failure.
    """
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        price = getattr(fi, "last_price", None) or getattr(fi, "regularMarketPrice", None)
        if price is None:
            return {}
        return {
            "close":  _to_float(price),
            "open":   _to_float(getattr(fi, "open", None)),
            "high":   _to_float(getattr(fi, "day_high", None)),
            "low":    _to_float(getattr(fi, "day_low", None)),
            "volume": _to_int(getattr(fi, "three_month_average_volume", None)),
        }
    except Exception as exc:
        logger.debug("yfinance fast_info failed: ticker=%s error=%s", ticker, exc)
        return {}


# ── Ticker list builder ───────────────────────────────────────────────────────

def _build_ticker_list(symbol: str) -> list[tuple[str, str]]:
    """
    Build priority-ordered list of (ticker, source_id) to try.

    Order:
      1. SYMBOL.NS  → source_id = "yfinance"
      2. SYMBOL.BO  → source_id = "yfinance"
      3. alt ns     → source_id = "yfinance_alt"  (if in alt_tickers.yaml)
      4. alt bo     → source_id = "yfinance_alt"  (if in alt_tickers.yaml)
    """
    tickers: list[tuple[str, str]] = [
        (f"{symbol}.NS", SOURCE_ID_MAIN),
        (f"{symbol}.BO", SOURCE_ID_MAIN),
    ]

    alts: dict = yaml_cfg.alt_tickers
    if symbol in alts:
        alt_entry = alts[symbol]
        if alt_entry.get("ns"):
            tickers.append((alt_entry["ns"], SOURCE_ID_ALT))
        if alt_entry.get("bo"):
            tickers.append((alt_entry["bo"], SOURCE_ID_ALT))

    return tickers


# ── Type coercers ─────────────────────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    """Coerce value to float, returning None on failure."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f  # NaN check
    except (ValueError, TypeError):
        return None


def _to_int(v: Any) -> int | None:
    """Coerce value to int, returning None on failure."""
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None
