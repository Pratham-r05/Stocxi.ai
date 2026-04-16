"""
technicals_service.py — Calculate technical indicators from OHLCV history.

OHLCV source hierarchy (never single point of failure):
  Priority 1: yfinance.download() — chart endpoint, sometimes works
  Priority 2: jugaad-data (nse.stock_df) — hits NSE directly, no Yahoo
  Priority 3: Return empty technicals gracefully — app never crashes

Golden rule: every function is try/excepted. On failure return None for that
field. Frontend shows "N/A". Never raise from this service.

Indicators (from ARCHITECTURE.md):
  RSI(14), MACD(12,26,9), ADX(14), ATR(14),
  Bollinger Bands(20,2), EMA(20/50/200), Volume SMA(20)

Library: `ta` (bukosabino/ta) — pandas 2.x native.
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

import ta.momentum   as ta_momentum
import ta.trend      as ta_trend
import ta.volatility as ta_volatility

logger = logging.getLogger(__name__)

_EMPTY = {
    "rsi": None, "rsi_signal": "Neutral",
    "macd": None, "macd_signal_line": None, "macd_histogram": None, "macd_signal": "Neutral",
    "adx": None, "adx_signal": "Weak Trend",
    "atr": None,
    "bb_upper": None, "bb_middle": None, "bb_lower": None, "bb_signal": "Inside Bands",
    "ema_20": None, "ema_50": None, "ema_200": None, "ema_signal": "Mixed",
    "volume_sma_20": None,
    "overall_signal": "Neutral",
}


# ── OHLCV Source 1: yfinance ──────────────────────────────────────────────────
def _try_yfinance(symbol: str) -> pd.DataFrame:
    """yfinance via chart endpoint — works when Yahoo isn't throttling."""
    import yfinance as yf

    for suffix in [".NS", ".BO"]:
        try:
            df = yf.download(
                f"{symbol}{suffix}",
                period="1y", interval="1d",
                progress=False, auto_adjust=True,
            )
            # yfinance sometimes returns MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df is not None and len(df) >= 30 and "Close" in df.columns:
                logger.info(f"OHLCV source: yfinance — {symbol}{suffix} ({len(df)} rows)")
                return df
        except Exception as e:
            logger.debug(f"yfinance failed for {symbol}{suffix}: {e}")
    return pd.DataFrame()


# ── OHLCV Source 2: jugaad-data (NSE direct) ──────────────────────────────────
def _try_jugaad(symbol: str) -> pd.DataFrame:
    """
    jugaad-data hits NSE directly — no Yahoo, no rate limits.
    Column mapping: DATE→index, OPEN→Open, HIGH→High, LOW→Low, CLOSE→Close, VOLUME→Volume
    """
    from jugaad_data.nse import stock_df  # type: ignore

    end   = date.today()
    start = end - timedelta(days=400)  # extra buffer for weekends/holidays

    try:
        df = stock_df(symbol=symbol, from_date=start, to_date=end, series="EQ")
        if df is None or df.empty:
            return pd.DataFrame()

        # Normalize column names — jugaad returns uppercase
        col_map = {
            "DATE": "Date", "OPEN": "Open", "HIGH": "High",
            "LOW": "Low", "CLOSE": "Close", "VOLUME": "Volume",
            # Alternate column names jugaad may use
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Set Date as index if present as column
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")
        elif "DATE" in df.columns:
            df["DATE"] = pd.to_datetime(df["DATE"])
            df = df.set_index("DATE")

        df = df.sort_index(ascending=True)

        required = {"Open", "High", "Low", "Close", "Volume"}
        if required.issubset(df.columns) and len(df) >= 30:
            logger.info(f"OHLCV source: jugaad-data — {symbol} ({len(df)} rows)")
            return df[list(required)]

        logger.debug(f"jugaad: missing columns or insufficient rows for {symbol}")
    except Exception as e:
        logger.warning(f"jugaad-data failed for {symbol}: {e}")
    return pd.DataFrame()


# ── OHLCV Dispatcher ──────────────────────────────────────────────────────────
def _download_history(symbol: str) -> pd.DataFrame:
    """Try all OHLCV sources in priority order. Return empty df if all fail."""
    df = _try_yfinance(symbol)
    if not df.empty:
        return df
    logger.warning(f"yfinance unavailable for {symbol}, trying jugaad-data...")
    df = _try_jugaad(symbol)
    if not df.empty:
        return df
    logger.warning(f"All OHLCV sources failed for {symbol} — returning empty technicals")
    return pd.DataFrame()


# ── Helper: safe scalar ───────────────────────────────────────────────────────
def _f(val) -> float | None:
    try:
        v = float(val)
        return None if pd.isna(v) else round(v, 4)
    except Exception:
        return None


def _last_valid(series: pd.Series) -> float | None:
    try:
        cleaned = series.dropna()
        if cleaned.empty:
            return None
        return _f(cleaned.iloc[-1])
    except Exception:
        return None


# ── Signal interpreters ───────────────────────────────────────────────────────
def _rsi_signal(v):
    if v is None: return "Neutral"
    return "Overbought" if v >= 70 else "Oversold" if v <= 30 else "Neutral"

def _macd_signal(macd, sig):
    if macd is None or sig is None: return "Neutral"
    return "Bullish" if macd > sig else "Bearish" if macd < sig else "Neutral"

def _adx_signal(v):
    if v is None: return "Weak Trend"
    return "Strong Trend" if v >= 40 else "Trend" if v >= 25 else "Weak Trend"

def _bb_signal(price, upper, lower):
    if any(x is None for x in [price, upper, lower]): return "Inside Bands"
    return "Overbought" if price >= upper else "Oversold" if price <= lower else "Inside Bands"

def _ema_signal(price, e20, e50, e200):
    if price is None: return "Mixed"
    votes = []
    for ema in [e20, e50, e200]:
        if ema is not None:
            votes.append("B" if price > ema else "S")
    if not votes: return "Mixed"
    b = votes.count("B")
    s = votes.count("S")
    return "Bullish" if b > s else "Bearish" if s > b else "Mixed"

def _overall(rsi_s, macd_s, ema_s):
    b = sum([macd_s == "Bullish", ema_s == "Bullish", rsi_s == "Oversold"]) * 1
    s = sum([macd_s == "Bearish", ema_s == "Bearish", rsi_s == "Overbought"]) * 1
    total = b + s
    if total == 0: return "Neutral"
    r = b / total
    return "Bullish" if r >= 0.65 else "Bearish" if r <= 0.35 else "Mixed"


# ── Core calculation ──────────────────────────────────────────────────────────
def _calculate_technicals(symbol: str) -> dict:
    """
    Sync — runs in thread pool.
    Downloads OHLCV (3-tier fallback), calculates all indicators.
    Returns _EMPTY dict on any failure — never raises.
    """
    try:
        df = _download_history(symbol.upper())
        if df.empty or len(df) < 20:
            return {**_EMPTY, "error": "No OHLCV data available from any source"}

        close  = df["Close"].squeeze()
        high   = df["High"].squeeze()
        low    = df["Low"].squeeze()
        volume = df["Volume"].squeeze()

        # Ensure all are 1-D Series (jugaad can return DataFrames)
        for col in [close, high, low, volume]:
            if not isinstance(col, pd.Series):
                return {**_EMPTY, "error": "OHLCV data format error"}

        # ── Indicators ────────────────────────────────────────────────────────
        n = len(close)

        rsi_window = min(14, max(2, n - 1))
        rsi = _last_valid(ta_momentum.RSIIndicator(close=close, window=rsi_window).rsi())

        slow = min(26, max(6, n - 1))
        fast = min(12, slow - 1)
        sign = min(9, max(3, fast - 1))
        macd_obj = ta_trend.MACD(close=close, window_fast=fast, window_slow=slow, window_sign=sign)
        macd_v = _last_valid(macd_obj.macd())
        macd_sl = _last_valid(macd_obj.macd_signal())
        macd_h = _last_valid(macd_obj.macd_diff())

        adx_window = min(14, max(3, n - 1))
        adx = _last_valid(ta_trend.ADXIndicator(high=high, low=low, close=close, window=adx_window).adx())

        atr_window = min(14, max(3, n - 1))
        atr = _last_valid(
            ta_volatility.AverageTrueRange(
                high=high,
                low=low,
                close=close,
                window=atr_window,
            ).average_true_range()
        )

        bb_window = min(20, max(5, n))
        bb = ta_volatility.BollingerBands(close=close, window=bb_window, window_dev=2)
        bb_u = _last_valid(bb.bollinger_hband())
        bb_m = _last_valid(bb.bollinger_mavg())
        bb_l = _last_valid(bb.bollinger_lband())

        # ewm fallback gives a stable value even if history is shorter than 200 candles.
        e20 = _f(close.ewm(span=min(20, max(2, n)), adjust=False).mean().iloc[-1])
        e50 = _f(close.ewm(span=min(50, max(2, n)), adjust=False).mean().iloc[-1])
        e200 = _f(close.ewm(span=min(200, max(2, n)), adjust=False).mean().iloc[-1])

        vol_window = min(20, max(2, n))
        vol_sma = _f(volume.rolling(window=vol_window, min_periods=1).mean().iloc[-1])
        price    = _f(close.iloc[-1])

        # ── Signals ──────────────────────────────────────────────────────────
        rsi_s  = _rsi_signal(rsi)
        macd_s = _macd_signal(macd_v, macd_sl)
        adx_s  = _adx_signal(adx)
        bb_s   = _bb_signal(price, bb_u, bb_l)
        ema_s  = _ema_signal(price, e20, e50, e200)
        ov     = _overall(rsi_s, macd_s, ema_s)

        return {
            "rsi": rsi, "rsi_signal": rsi_s,
            "macd": macd_v, "macd_signal_line": macd_sl,
            "macd_histogram": macd_h, "macd_signal": macd_s,
            "adx": adx, "adx_signal": adx_s,
            "atr": atr,
            "bb_upper": bb_u, "bb_middle": bb_m, "bb_lower": bb_l, "bb_signal": bb_s,
            "ema_20": e20, "ema_50": e50, "ema_200": e200, "ema_signal": ema_s,
            "volume_sma_20": vol_sma,
            "overall_signal": ov,
        }

    except Exception as e:
        logger.error(f"Technicals calculation failed for {symbol}: {e}")
        return {**_EMPTY, "error": str(e)}


async def calculate_technicals(symbol: str) -> dict:
    """Async entry point — runs sync calculation in thread pool. Never raises."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _calculate_technicals, symbol.upper())
