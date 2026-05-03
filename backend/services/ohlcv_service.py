
"""
ohlcv_service.py — OHLCV history waterfall for a given stock or index.

Waterfall (equity):
  L1: NSE library (fetch_equity_historical_data)
  L2: yfinance (.NS → .BO → alt ticker)

Waterfall (index — e.g. "NIFTY 50"):
  L1: NSE library (fetch_historical_index_data)
  Index symbols atrre detected by presence of a space (e.g. "NIFTY 50").

Returns a normalised pandas DataFrame with columns:
  [Open, High, Low, Close, Volume] and DatetimeIndex (ascending).

This service is consumed by technicals_service (indicator computation) and
is the single authoritative OHLCV source for the entire pipeline.
Never use inline yfinance/jugaad/Groww calls in other services — call this.

Point-in-time safety: pass as_of_date to exclude data after that date (backtest).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from backend.fetchers import nse_client, yfinance_client
from backend.fetchers.base import waterfall, WaterfallFailure
from backend.util.ist_calendar import today_ist

logger = logging.getLogger(__name__)

# How many calendar days of history to fetch (includes weekends/holidays)
HISTORY_DAYS = 400   # ~250 trading days for 200-period indicators


async def get_ohlcv(
    symbol: str,
    as_of_date: date | None = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV history with NSE → yfinance waterfall.

    Args:
        symbol:      NSE ticker or index name in uppercase (e.g. "RELIANCE",
                     "NIFTY 50"). Index symbols contain a space.
        as_of_date:  Point-in-time cutoff. None = today (live mode).
                     Backtest callers must pass the analysis date.

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume],
        DatetimeIndex ascending. Empty DataFrame if all sources fail.

    Never raises — returns empty DataFrame on total failure.
    """
    symbol = symbol.strip().upper()
    end_date  = as_of_date or today_ist()
    from_date = end_date - timedelta(days=HISTORY_DAYS)

    # ── Index path (e.g. "NIFTY 50") ─────────────────────────────────────────
    is_index = " " in symbol
    if is_index:
        async def _nse_index() -> dict[str, Any]:
            return await nse_client.fetch_index_ohlcv(symbol, from_date, end_date)

        try:
            fetch_result = await waterfall.run([
                ("nse_library", 1.00, _nse_index),
            ], request_id=f"ohlcv:{symbol}:{end_date}")
        except WaterfallFailure as exc:
            logger.warning("Index OHLCV waterfall exhausted for %s: %s", symbol, exc)
            return pd.DataFrame()

        df = _normalise(fetch_result.payload, fetch_result.source_id)
        if df.empty:
            logger.warning("Index OHLCV normalise empty for %s", symbol)
        return df

    # ── Equity path ───────────────────────────────────────────────────────────
    async def _nse() -> dict[str, Any]:
        result = await nse_client.fetch_ohlcv(symbol, from_date, end_date)
        return result

    async def _yfinance() -> dict[str, Any]:
        result = await yfinance_client.fetch_ohlcv(symbol, from_date, end_date)
        return result

    try:
        fetch_result = await waterfall.run([
            ("nse_library", 1.00, _nse),
            ("yfinance",    0.70, _yfinance),
        ], request_id=f"ohlcv:{symbol}:{end_date}")
    except WaterfallFailure as exc:
        logger.warning("OHLCV waterfall exhausted for %s: %s", symbol, exc)
        return pd.DataFrame()

    df = _normalise(fetch_result.payload, fetch_result.source_id)
    if df.empty:
        logger.warning("OHLCV normalise returned empty for %s (source=%s)",
                       symbol, fetch_result.source_id)

    return df


# ── Normalise raw payload → DataFrame ─────────────────────────────────────────

def _normalise(payload: dict | None, source_id: str) -> pd.DataFrame:
    """
    Convert a raw OHLCV payload dict (from nse_client or yfinance_client)
    into a clean DataFrame with standard column names and DatetimeIndex.

    Returns empty DataFrame on any parse error.
    """
    if not payload:
        return pd.DataFrame()

    rows = payload.get("rows")
    if not rows or not isinstance(rows, list):
        return pd.DataFrame()

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            records.append({
                "date":   row.get("date", ""),
                "Open":   _to_float(row.get("open")),
                "High":   _to_float(row.get("high")),
                "Low":    _to_float(row.get("low")),
                "Close":  _to_float(row.get("close")),
                "Volume": _to_float(row.get("volume")) or 0.0,
            })
        except Exception:
            continue

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    # Try ISO format first (equity: "2025-04-29"), then DD-MON-YYYY (index: "30-APR-2025")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    mask_failed = df["date"].isna()
    if mask_failed.any():
        if "date_raw" in df.columns:
            date_input = df.loc[mask_failed, "date_raw"]
        else:
            date_input = df.loc[mask_failed, "date"].copy()
        df.loc[mask_failed, "date"] = pd.to_datetime(
            date_input,
            format="%d-%b-%Y", errors="coerce",
        )
    # Fallback: re-parse any still-NaT cells with mixed-format inference
    still_nat = df["date"].isna()
    if still_nat.any():
        df.loc[still_nat, "date"] = pd.to_datetime(
            [records[i]["date"] for i in df.index[still_nat]],
            format="mixed",
            errors="coerce",
        )
    df = df.dropna(subset=["date", "Close"])
    df = df.set_index("date").sort_index(ascending=True)

    # Drop rows with zero/negative close (data artifact)
    df = df[df["Close"] > 0]

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.warning("OHLCV missing columns from %s: %s", source_id, missing)
        return pd.DataFrame()

    # Correct unadjusted prices caused by splits/bonuses (NSE returns raw prices)
    df = _apply_split_adjustment(df[required].copy(), source_id)
    return df


_SPLIT_DETECTION_THRESHOLD = 0.40  # ratio < this → forward split (catches 3:1, 4:1, 5:1, 10:1)
_SPLIT_CANDIDATES = [2.0, 3.0, 4.0, 5.0, 10.0, 1.5, 2.5]


def _nearest_split_factor(raw: float) -> float:
    """Round a detected ratio to the nearest common corporate action factor."""
    return min(_SPLIT_CANDIDATES, key=lambda c: abs(c - raw))


def _apply_split_adjustment(df: pd.DataFrame, source_id: str) -> pd.DataFrame:
    """
    Detect consecutive-day price discontinuities caused by unadjusted splits/bonuses
    and normalise all historical prices to the post-split scale.

    NSE's fetch_equity_historical_data returns raw (unadjusted) prices. When a
    stock has had a corporate split, pre-split prices are N× higher, inflating
    SMA/EMA calculations. This function detects jumps where the day-over-day
    close ratio falls outside [threshold, 1/threshold] and adjusts all prices
    before the jump date by the detected factor.

    Only applied to NSE source data; yfinance already auto-adjusts.
    """
    if source_id not in ("nse_library",) or df.empty or len(df) < 2:
        return df

    close = df["Close"].values
    n = len(close)
    row_factors = [1.0] * n

    for i in range(1, n):
        prev = close[i - 1]
        curr = close[i]
        if prev <= 0 or curr <= 0:
            continue
        ratio = curr / prev
        if ratio < _SPLIT_DETECTION_THRESHOLD:
            # Forward split: price dropped (e.g. 5:1 → ratio ≈ 0.2)
            raw_factor = 1.0 / ratio
            factor = _nearest_split_factor(raw_factor)
            for j in range(i):
                row_factors[j] /= factor
        elif ratio > (1.0 / _SPLIT_DETECTION_THRESHOLD):
            # Reverse split / consolidation: price jumped
            factor = _nearest_split_factor(ratio)
            for j in range(i):
                row_factors[j] *= factor

    if all(abs(f - 1.0) < 1e-6 for f in row_factors):
        return df

    n_adjusted = sum(1 for f in row_factors if abs(f - 1.0) > 1e-6)
    logger.info(
        "ohlcv: split adjustment applied to %d rows (source=%s)", n_adjusted, source_id
    )
    factor_s = pd.Series(row_factors, index=df.index)
    for col in ("Open", "High", "Low", "Close"):
        if col in df.columns:
            df[col] = (df[col] * factor_s).round(2)
    return df


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f
    except (ValueError, TypeError):
        return None
