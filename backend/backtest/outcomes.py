"""
outcomes.py — Fetch actual price outcomes for backtesting.

Point-in-time guarantee:
  - entry_price  = closing price on signal_date (or nearest trading day after)
  - exit_price   = closing price on signal_date + horizon_days
  - Neither call sees data beyond the target date (explicit start/end to yfinance)

Nifty benchmark:
  - nifty_return = (NIFTY50 exit_price / NIFTY50 entry_price - 1) × 100
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

_NIFTY_SYMBOL = "^NSEI"
_MAX_FORWARD_DAYS = 7    # look-ahead window when exact date has no trade data


def _fetch_close(symbol: str, target_date: date) -> float | None:
    """
    Fetch adjusted closing price on or just after target_date (within MAX_FORWARD_DAYS).
    Uses yfinance with an explicit date range — no future data leaks in.
    Returns None on any failure.
    """
    try:
        import yfinance as yf

        end   = target_date + timedelta(days=_MAX_FORWARD_DAYS + 1)
        start = target_date

        df = yf.download(symbol, start=start, end=end, interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if "Close" not in df.columns:
            return None

        # Return the first available close on or after target_date
        close_series = df["Close"].dropna()
        if close_series.empty:
            return None

        val = close_series.iloc[0]
        return float(val) if not pd.isna(val) else None

    except Exception as exc:
        logger.debug("_fetch_close(%s, %s) failed — %s", symbol, target_date, exc)
        return None


def fetch_outcome(
    nse_symbol: str,
    signal_date: date,
    horizon_days: int,
) -> dict | None:
    """
    Compute the actual outcome for one signal.

    Args:
        nse_symbol:    NSE ticker (e.g. "RELIANCE")
        signal_date:   The date the signal was generated
        horizon_days:  Holding period in calendar days (short=30, long=90)

    Returns:
        {
          "entry_price":      float,
          "exit_price":       float,
          "exit_date":        date,
          "return_pct":       float,      # (exit/entry - 1) × 100
          "nifty_entry":      float | None,
          "nifty_exit":       float | None,
          "nifty_return_pct": float | None,
          "alpha_pct":        float | None,   # return_pct - nifty_return_pct
        }
        or None if price data unavailable.
    """
    for suffix in [".NS", ".BO"]:
        entry = _fetch_close(f"{nse_symbol}{suffix}", signal_date)
        if entry is not None:
            break
    else:
        logger.warning("fetch_outcome: no entry price for %s on %s", nse_symbol, signal_date)
        return None

    exit_date = signal_date + timedelta(days=horizon_days)
    for suffix in [".NS", ".BO"]:
        exit_price = _fetch_close(f"{nse_symbol}{suffix}", exit_date)
        if exit_price is not None:
            break
    else:
        logger.warning("fetch_outcome: no exit price for %s on %s", nse_symbol, exit_date)
        return None

    return_pct = (exit_price / entry - 1) * 100

    # Nifty benchmark
    nifty_entry = _fetch_close(_NIFTY_SYMBOL, signal_date)
    nifty_exit  = _fetch_close(_NIFTY_SYMBOL, exit_date)
    nifty_return_pct = None
    alpha_pct        = None
    if nifty_entry and nifty_exit:
        nifty_return_pct = (nifty_exit / nifty_entry - 1) * 100
        alpha_pct        = return_pct - nifty_return_pct

    return {
        "entry_price":      round(entry, 2),
        "exit_price":       round(exit_price, 2),
        "exit_date":        exit_date,
        "return_pct":       round(return_pct, 4),
        "nifty_entry":      round(nifty_entry, 2) if nifty_entry else None,
        "nifty_exit":       round(nifty_exit, 2)  if nifty_exit  else None,
        "nifty_return_pct": round(nifty_return_pct, 4) if nifty_return_pct is not None else None,
        "alpha_pct":        round(alpha_pct, 4)        if alpha_pct        is not None else None,
    }


def signal_is_correct(signal: str, actual_return_pct: float, neutral_threshold: float = 0.5) -> bool | None:
    """
    Evaluate whether a signal was directionally correct.

    Returns:
        True  — signal direction matched price movement
        False — signal direction was wrong
        None  — signal was neutral/mixed (no trade, skip in accuracy calc)
    """
    if signal in ("neutral", "mixed"):
        return None
    if signal == "bullish":
        return actual_return_pct >= neutral_threshold
    if signal == "bearish":
        return actual_return_pct <= -neutral_threshold
    return None
