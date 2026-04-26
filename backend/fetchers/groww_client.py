"""
groww_client.py — Production Groww Trade API client.

Layer: fetchers/
Role: Singleton wrapper around the growwapi SDK. Provides:
  - Authenticated GrowwAPI instance (token refreshed via get_access_token)
  - get_ohlcv(symbol, start, end, as_of_date) → pd.DataFrame [Open,High,Low,Close,Volume]
  - get_quote(symbol) → dict with last_price, ohlc, volume, 52w high/low
  - get_ltp(symbols) → dict[symbol, float]  (batch, up to 50)

Auth:
  Groww tokens are long-lived JWTs (exp ~2065). get_access_token() is called
  once at module load. The client is a module-level singleton — safe under
  async because growwapi SDK calls are synchronous (run in thread executor).

Config keys (all from .env via config.py):
  GROWW_API_KEY    — API key / JWT from Groww Trade API dashboard
  GROWW_API_SECRET — API secret from Groww Trade API dashboard

Never import from this module outside of fetchers/ and services/.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── Singleton lock ─────────────────────────────────────────────────────────────
_client_lock  = threading.Lock()
_groww_client = None   # type: Any  # GrowwAPI instance


def _get_client():
    """Return the module-level GrowwAPI singleton, initialising once."""
    global _groww_client
    if _groww_client is not None:
        return _groww_client

    with _client_lock:
        if _groww_client is not None:          # double-checked locking
            return _groww_client

        from config import settings            # lazy — avoids circular import
        from growwapi import GrowwAPI

        token = GrowwAPI.get_access_token(
            api_key=settings.groww_api_key,
            secret=settings.groww_api_secret,
        )
        _groww_client = GrowwAPI(token)
        logger.info("groww_client: authenticated — client initialised")
        return _groww_client


# ── OHLCV ─────────────────────────────────────────────────────────────────────

def get_ohlcv(
    symbol: str,
    as_of_date: date | None = None,
    lookback_days: int = 400,
    exchange: str = "NSE",
    segment: str = "CASH",
) -> pd.DataFrame:
    """Fetch daily OHLCV history from Groww for the given NSE symbol.

    Enforces point-in-time: no data after as_of_date is included.

    Args:
        symbol:       NSE trading symbol, e.g. "RELIANCE" (no suffix).
        as_of_date:   Upper date bound for point-in-time backtesting.
                      Defaults to today.
        lookback_days: How many calendar days of history to fetch.
        exchange:     "NSE" or "BSE".
        segment:      "CASH" for equities.

    Returns:
        pd.DataFrame with DatetimeIndex and columns [Open, High, Low, Close, Volume].
        Empty DataFrame if fetch fails or fewer than 30 rows returned.
    """
    end_date   = as_of_date or date.today()
    start_date = end_date - timedelta(days=lookback_days)

    start_str = datetime.combine(start_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    end_str   = datetime.combine(end_date,   datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")

    try:
        client  = _get_client()
        # get_historical_candle_data returns {"candles": [[ts, o, h, l, c, v], ...], ...}
        # interval_in_minutes=1440 → daily candles
        response = client.get_historical_candle_data(
            trading_symbol=symbol,
            exchange=exchange,
            segment=segment,
            start_time=start_str,
            end_time=end_str,
            interval_in_minutes=1440,
        )

        candles = response.get("candles", []) if isinstance(response, dict) else []
        if not candles:
            logger.warning("groww_client: empty candles for %s", symbol)
            return pd.DataFrame()

        # Each candle: [epoch_seconds, open, high, low, close, volume]
        rows = []
        for entry in candles:
            if len(entry) < 6:
                continue
            ts, o, h, l, c, v = entry[0], entry[1], entry[2], entry[3], entry[4], entry[5]
            dt = datetime.fromtimestamp(ts).date()
            rows.append({"Date": dt, "Open": o, "High": h, "Low": l, "Close": c, "Volume": v})

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index(ascending=True)

        # Point-in-time enforcement: strip any rows after as_of_date
        if as_of_date:
            df = df[df.index.date <= as_of_date]   # type: ignore[operator]

        if len(df) < 30:
            logger.warning("groww_client: only %d rows for %s — insufficient", len(df), symbol)
            return pd.DataFrame()

        logger.info("groww_client: OHLCV OK — %s (%d rows, %s → %s)",
                    symbol, len(df), df.index[0].date(), df.index[-1].date())
        return df[["Open", "High", "Low", "Close", "Volume"]]

    except Exception as exc:
        logger.warning("groww_client: get_ohlcv failed for %s — %s", symbol, exc)
        return pd.DataFrame()


# ── Live quote ────────────────────────────────────────────────────────────────

def get_quote(
    symbol: str,
    exchange: str = "NSE",
    segment: str = "CASH",
) -> dict[str, Any]:
    """Fetch a full live quote for a symbol.

    Returns dict with keys: last_price, day_change, day_change_perc,
    ohlc (open/high/low/close), volume, week_52_high, week_52_low.
    Returns empty dict on failure — never raises.
    """
    try:
        client = _get_client()
        raw = client.get_quote(exchange=exchange, segment=segment, trading_symbol=symbol)
        if not raw:
            return {}

        return {
            "last_price":      raw.get("last_price"),
            "day_change":      raw.get("day_change"),
            "day_change_perc": raw.get("day_change_perc"),
            "open":            (raw.get("ohlc") or {}).get("open"),
            "high":            (raw.get("ohlc") or {}).get("high"),
            "low":             (raw.get("ohlc") or {}).get("low"),
            "prev_close":      (raw.get("ohlc") or {}).get("close"),
            "volume":          raw.get("volume"),
            "week_52_high":    raw.get("week_52_high"),
            "week_52_low":     raw.get("week_52_low"),
            "total_buy_qty":   raw.get("total_buy_quantity"),
            "total_sell_qty":  raw.get("total_sell_quantity"),
        }
    except Exception as exc:
        logger.warning("groww_client: get_quote failed for %s — %s", symbol, exc)
        return {}


# ── Batch LTP ─────────────────────────────────────────────────────────────────

def get_ltp(
    symbols: list[str],
    exchange: str = "NSE",
    segment: str = "CASH",
) -> dict[str, float]:
    """Fetch last traded price for up to 50 symbols in one call.

    Args:
        symbols: List of NSE trading symbols (max 50).
        exchange: "NSE" or "BSE".
        segment:  "CASH" for equities.

    Returns:
        dict mapping symbol → last_price. Missing symbols are omitted.
    """
    if not symbols:
        return {}

    try:
        client  = _get_client()
        batch   = symbols[:50]   # Groww hard cap
        results: dict[str, float] = {}

        for sym in batch:
            try:
                raw = client.get_quote(exchange=exchange, segment=segment, trading_symbol=sym)
                if raw and raw.get("last_price") is not None:
                    results[sym] = float(raw["last_price"])
            except Exception as sym_exc:
                logger.debug("groww_client: ltp failed for %s — %s", sym, sym_exc)

        logger.info("groww_client: batch LTP — %d/%d symbols resolved", len(results), len(batch))
        return results

    except Exception as exc:
        logger.warning("groww_client: get_ltp batch failed — %s", exc)
        return {}
