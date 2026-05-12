"""
technicals_service.py — Compute 17 technical indicators from OHLCV history.

OHLCV source: ohlcv_service.get_ohlcv() — NSE → yfinance waterfall.
Do NOT fetch OHLCV inline here. All source fallback logic lives in ohlcv_service.

Indicators (17 total — ARCHITECTURE.md §4.1 + weights.yaml):
  Trend (4):      SMA, EMA, Ichimoku, Parabolic_SAR
  Momentum (5):   RSI_14, MACD, Stochastic, Williams_R, ROC
  Volatility (2): Bollinger_Bands, ATR_14
  Volume (4):     OBV, VWAP, CMF, MFI
  Strength (2):   ADX_14, 52W_HL_Ratio

Output: list[Node] (NodeCategory.technical, weights from weights.yaml).
Signal logic preserved from M1 implementation — all signal functions unchanged.

Legacy dict API: calculate_technicals() is retained as a compatibility shim
for existing v1 routers until Phase 5 wires up the v2 API.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import pandas as pd

import ta.momentum   as ta_momentum
import ta.trend      as ta_trend
import ta.volatility as ta_volatility
import ta.volume     as ta_volume

from services.ohlcv_service import get_ohlcv
from services.symbol_service import canonicalize_symbol
from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from schemas.messages import UserProfile, Horizon, Risk
from config import yaml_cfg
from util.ist_calendar import now_ist, today_ist

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_technicals(
    symbol: str,
    as_of_date: date | None = None,
    profile: UserProfile | None = None,
    request_id: str = "",
) -> list[Node]:
    """
    Compute 17 technical indicator nodes for a stock.

    Args:
        symbol:     NSE ticker in uppercase.
        as_of_date: Point-in-time cutoff (backtest). None = today.
        profile:    User profile for weight and horizon selection.
                    Defaults to short-term moderate if not provided.
        request_id: Trace ID for logging.

    Returns:
        list[Node] — up to 17 indicator nodes. Fewer if OHLCV data is sparse.
        Empty list if OHLCV data unavailable.
    """
    symbol   = canonicalize_symbol(symbol)
    end_date = as_of_date or today_ist()
    profile  = profile or UserProfile(horizon=Horizon.short, risk=Risk.moderate)

    df = await get_ohlcv(symbol, end_date)
    if df.empty or len(df) < 20:
        logger.warning("technicals: insufficient OHLCV for %s (%d rows)", symbol, len(df))
        return []

    loop = asyncio.get_running_loop()
    nodes = await loop.run_in_executor(None, _compute_nodes, df, symbol, end_date, profile)
    return nodes


# ── Compatibility shim for v1 router ─────────────────────────────────────────

async def calculate_technicals(symbol: str, as_of_date: date | None = None) -> dict:
    """
    Legacy dict API — used by v1 routers until Phase 5 migration.
    Computes technicals and converts Node list back to the original flat dict format.
    """
    nodes = await get_technicals(symbol, as_of_date)
    return _nodes_to_legacy_dict(nodes)


# ── Core computation (sync, runs in executor) ─────────────────────────────────

def _compute_nodes(
    df: pd.DataFrame,
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
) -> list[Node]:
    """
    Compute all 17 indicators from the OHLCV DataFrame and emit Nodes.
    Runs synchronously in a thread-pool executor.
    """
    nodes: list[Node] = []
    horizon = profile.horizon.value
    weights = yaml_cfg.weights
    w_ver   = yaml_cfg.versions.get("weight_version", "")
    fetched = now_ist()

    close  = df["Close"].squeeze()
    high   = df["High"].squeeze()
    low    = df["Low"].squeeze()
    volume = df["Volume"].squeeze()
    n = len(close)
    price = _f(close.iloc[-1])

    if price is None:
        return []

    # ── Helper: emit one Node ────────────────────────────────────────────────
    def emit(name: str, value_str: str, value_raw: dict,
             signal_str: str, weight_key: str,
             horizon_rel: HorizonRelevance = HorizonRelevance.both) -> None:
        sig = _map_signal(signal_str)
        if sig is None:
            return
        w = _get_weight(weights, "technical", weight_key, horizon)
        nodes.append(Node(
            stock=symbol, category=NodeCategory.technical, name=name,
            value=value_str, value_raw={**value_raw, "_signal": signal_str}, signal=sig,
            confidence=1.00,
            source="ta_library", source_url="",
            as_of_date=as_of_date, fetched_at_ist=fetched,
            horizon_relevance=horizon_rel, weight=w, weight_version=w_ver,
            sanitized=False,
        ))

    # ── 1. RSI (14) ──────────────────────────────────────────────────────────
    try:
        w = min(14, max(2, n - 1))
        rsi = _last_valid(ta_momentum.RSIIndicator(close=close, window=w).rsi())
        if rsi is not None:
            s = "Overbought" if rsi >= 70 else "Oversold" if rsi <= 30 else "Neutral"
            emit("RSI_14", f"RSI: {rsi:.1f}",
                 {"rsi": rsi},
                 s, "rsi", HorizonRelevance.short)
    except Exception:
        pass

    # ── 2. MACD (12/26/9) ────────────────────────────────────────────────────
    try:
        slow = min(26, max(6, n - 1))
        fast = min(12, slow - 1)
        sign = min(9, max(3, fast - 1))
        obj = ta_trend.MACD(close=close, window_fast=fast, window_slow=slow, window_sign=sign)
        macd_v  = _last_valid(obj.macd())
        macd_sl = _last_valid(obj.macd_signal())
        macd_h  = _last_valid(obj.macd_diff())
        if macd_v is not None and macd_sl is not None:
            s = "Bullish" if macd_v > macd_sl else "Bearish"
            emit("MACD", f"MACD: {macd_v:.2f}, Signal: {macd_sl:.2f}",
                 {"macd": macd_v, "signal": macd_sl, "histogram": macd_h},
                 s, "macd", HorizonRelevance.short)
    except Exception:
        pass

    # ── 3. ADX (14) ──────────────────────────────────────────────────────────
    try:
        w = min(14, max(3, n - 1))
        adx = _last_valid(ta_trend.ADXIndicator(high=high, low=low, close=close, window=w).adx())
        if adx is not None:
            s = ("Strong Trend" if adx >= 40 else
                 "Trend" if adx >= 25 else "Weak Trend")
            emit("ADX_14", f"ADX: {adx:.1f} ({s})",
                 {"adx": adx}, s, "adx", HorizonRelevance.both)
    except Exception:
        pass

    # ── 4. ATR (14) ──────────────────────────────────────────────────────────
    try:
        w = min(14, max(3, n - 1))
        atr = _last_valid(
            ta_volatility.AverageTrueRange(high=high, low=low, close=close, window=w)
            .average_true_range()
        )
        if atr is not None:
            pct = (atr / price) * 100 if price else 0
            s = ("High Volatility" if pct >= 3.0 else
                 "Low Volatility" if pct < 1.0 else "Normal Volatility")
            emit("ATR_14", f"ATR: {atr:.2f} ({pct:.1f}%)",
                 {"atr": atr, "atr_pct": round(pct, 2)},
                 s, "atr", HorizonRelevance.short)
    except Exception:
        pass

    # ── 5. Bollinger Bands (20, 2σ) ───────────────────────────────────────────
    try:
        w = min(20, max(5, n))
        bb = ta_volatility.BollingerBands(close=close, window=w, window_dev=2)
        bb_u = _last_valid(bb.bollinger_hband())
        bb_m = _last_valid(bb.bollinger_mavg())
        bb_l = _last_valid(bb.bollinger_lband())
        if bb_u and bb_m and bb_l:
            if price >= bb_u:
                s, name = "Overbought", "Bollinger_Upper"
            elif price <= bb_l:
                s, name = "Oversold", "Bollinger_Lower"
            else:
                s, name = "Inside Bands", "Bollinger_Bands"
            emit(name, f"BB: {bb_l:.1f} | {bb_m:.1f} | {bb_u:.1f} | P: {price:.1f}",
                 {"upper": bb_u, "middle": bb_m, "lower": bb_l, "price": price},
                 s, "bollinger_bands", HorizonRelevance.short)
    except Exception:
        pass

    # ── 6. EMA (20/50/200) ────────────────────────────────────────────────────
    try:
        e20  = _f(close.ewm(span=min(20,  max(2, n)), adjust=False).mean().iloc[-1])
        e50  = _f(close.ewm(span=min(50,  max(2, n)), adjust=False).mean().iloc[-1])
        e200 = _f(close.ewm(span=min(200, max(2, n)), adjust=False).mean().iloc[-1])
        votes = [1 if price > e else -1 for e in [e20, e50, e200] if e]
        if votes:
            b, s_c = votes.count(1), votes.count(-1)
            s = "Bullish" if b > s_c else "Bearish" if s_c > b else "Mixed"
            emit("EMA", f"EMA20: {e20:.1f} | EMA50: {e50:.1f} | EMA200: {e200:.1f}",
                 {"ema_20": e20, "ema_50": e50, "ema_200": e200, "price": price},
                 s, "ema", HorizonRelevance.both)
    except Exception:
        pass

    # ── 7. SMA (20/50/200) ────────────────────────────────────────────────────
    try:
        sma200 = _last_valid(ta_trend.SMAIndicator(close=close, window=min(200, n)).sma_indicator())
        sma50  = _last_valid(ta_trend.SMAIndicator(close=close, window=min(50, n)).sma_indicator())
        sma20  = _last_valid(ta_trend.SMAIndicator(close=close, window=min(20, n)).sma_indicator())
        if sma200:
            s = "Bullish" if price > sma200 else "Bearish"
            emit("SMA", f"SMA20: {sma20:.1f} | SMA50: {sma50:.1f} | SMA200: {sma200:.1f}",
                 {"sma_20": sma20, "sma_50": sma50, "sma_200": sma200, "price": price},
                 s, "sma", HorizonRelevance.long)
    except Exception:
        pass

    # ── 8. Ichimoku Cloud (9/26/52) ───────────────────────────────────────────
    try:
        w1 = min(9, max(3, n - 1))
        w2 = min(26, max(w1 + 1, n - 1))
        w3 = min(52, max(w2 + 1, n - 1))
        ichi = ta_trend.IchimokuIndicator(high=high, low=low,
                                           window1=w1, window2=w2, window3=w3,
                                           visual=False)
        ichi_a = _last_valid(ichi.ichimoku_a())
        ichi_b = _last_valid(ichi.ichimoku_b())
        if ichi_a and ichi_b:
            top, bot = max(ichi_a, ichi_b), min(ichi_a, ichi_b)
            s = ("Above Cloud" if price > top
                 else "Below Cloud" if price < bot
                 else "In Cloud")
            emit("Ichimoku", f"Cloud: {bot:.1f}–{top:.1f} | Price: {price:.1f}",
                 {"ichimoku_a": ichi_a, "ichimoku_b": ichi_b,
                  "base_line": _last_valid(ichi.ichimoku_base_line()),
                  "conv_line": _last_valid(ichi.ichimoku_conversion_line()),
                  "price": price},
                 s, "ichimoku", HorizonRelevance.both)
    except Exception:
        pass

    # ── 9. Parabolic SAR ─────────────────────────────────────────────────────
    try:
        psar = _last_valid(ta_trend.PSARIndicator(high=high, low=low, close=close).psar())
        if psar:
            s = "Bullish" if price > psar else "Bearish"
            emit("Parabolic_SAR", f"PSAR: {psar:.2f}, Price: {price:.2f}",
                 {"psar": psar, "price": price},
                 s, "parabolic_sar", HorizonRelevance.short)
    except Exception:
        pass

    # ── 10. Stochastic (14, 3) ────────────────────────────────────────────────
    try:
        w = min(14, max(5, n - 1))
        stoch = ta_momentum.StochasticOscillator(high=high, low=low, close=close,
                                                  window=w, smooth_window=3)
        k = _last_valid(stoch.stoch())
        d = _last_valid(stoch.stoch_signal())
        if k is not None:
            s = "Overbought" if k >= 80 else "Oversold" if k <= 20 else "Neutral"
            emit("Stochastic", f"Stoch %K: {k:.1f}, %D: {d:.1f}" if d else f"Stoch %K: {k:.1f}",
                 {"stoch_k": k, "stoch_d": d},
                 s, "stochastic", HorizonRelevance.short)
    except Exception:
        pass

    # ── 11. Williams %R (14) ─────────────────────────────────────────────────
    try:
        w = min(14, max(5, n - 1))
        wr = _last_valid(
            ta_momentum.WilliamsRIndicator(high=high, low=low, close=close, lbp=w).williams_r()
        )
        if wr is not None:
            s = "Overbought" if wr >= -20 else "Oversold" if wr <= -80 else "Neutral"
            emit("Williams_R", f"Williams %R: {wr:.1f}",
                 {"williams_r": wr}, s, "williams_r", HorizonRelevance.short)
    except Exception:
        pass

    # ── 12. ROC (12) ─────────────────────────────────────────────────────────
    try:
        w = min(12, max(2, n - 1))
        roc = _last_valid(ta_momentum.ROCIndicator(close=close, window=w).roc())
        if roc is not None:
            s = "Bullish" if roc > 0 else "Bearish"
            emit("ROC", f"ROC: {roc:.2f}%",
                 {"roc_pct": roc}, s, "roc", HorizonRelevance.short)
    except Exception:
        pass

    # ── 13. OBV ──────────────────────────────────────────────────────────────
    try:
        obv_series = ta_volume.OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
        obv_v = _last_valid(obv_series)
        if obv_v is not None:
            lookback = min(20, max(5, n // 4))
            obv_chg   = obv_series.iloc[-1] - obv_series.iloc[-lookback]
            price_chg = close.iloc[-1] - close.iloc[-lookback]
            if obv_chg > 0 and price_chg > 0:   s = "Bullish Confirmation"
            elif obv_chg > 0 and price_chg < 0: s = "Bullish Divergence"
            elif obv_chg < 0 and price_chg > 0: s = "Bearish Divergence"
            elif obv_chg < 0 and price_chg < 0: s = "Bearish Confirmation"
            else:                                s = "Neutral"
            obv_sma = _f(obv_series.rolling(window=lookback, min_periods=1).mean().iloc[-1])
            emit("OBV", f"OBV: {obv_v/1e6:.1f}M, Trend: {s}",
                 {"obv": obv_v, "obv_sma": obv_sma, "trend": s.lower()},
                 s, "obv", HorizonRelevance.both)
    except Exception:
        pass

    # ── 14. VWAP (14-day rolling) ─────────────────────────────────────────────
    try:
        w = min(14, max(5, n))
        if volume.sum() <= 0:
            raise ValueError("volume all zero")
        vwap = _last_valid(
            ta_volume.VolumeWeightedAveragePrice(high=high, low=low, close=close,
                                                  volume=volume, window=w)
            .volume_weighted_average_price()
        )
        if vwap:
            s = "Bullish" if price > vwap else "Bearish"
            emit("VWAP", f"VWAP: {vwap:.2f}, Price: {price:.2f}",
                 {"vwap": vwap, "price": price},
                 s, "vwap", HorizonRelevance.short)
    except Exception:
        pass

    # ── 15. CMF (20) ─────────────────────────────────────────────────────────
    try:
        w = min(20, max(5, n))
        cmf = _last_valid(
            ta_volume.ChaikinMoneyFlowIndicator(high=high, low=low, close=close,
                                                 volume=volume, window=w)
            .chaikin_money_flow()
        )
        if cmf is not None:
            s = "Bullish" if cmf > 0.2 else "Bearish" if cmf < -0.2 else "Neutral"
            emit("CMF", f"CMF: {cmf:.3f}",
                 {"cmf": cmf}, s, "cmf", HorizonRelevance.short)
    except Exception:
        pass

    # ── 16. MFI (14) ─────────────────────────────────────────────────────────
    try:
        w = min(14, max(5, n - 1))
        mfi = _last_valid(
            ta_volume.MFIIndicator(high=high, low=low, close=close,
                                   volume=volume, window=w)
            .money_flow_index()
        )
        if mfi is not None:
            s = "Overbought" if mfi >= 80 else "Oversold" if mfi <= 20 else "Neutral"
            emit("MFI", f"MFI: {mfi:.1f}",
                 {"mfi": mfi}, s, "mfi", HorizonRelevance.short)
    except Exception:
        pass

    # ── 17. Volume SMA 20 (for volume ratio card) ────────────────────────────
    try:
        vol_sma20 = _f(volume.rolling(window=min(20, n), min_periods=1).mean().iloc[-1])
        if vol_sma20 and vol_sma20 > 0:
            current_vol = _f(volume.iloc[-1])
            ratio = (current_vol / vol_sma20) if current_vol else 1.0
            s = "Bullish" if ratio >= 1.5 else "Bearish" if ratio < 0.7 else "Neutral"
            emit("Volume_SMA20", f"Vol SMA20: {vol_sma20:.0f}",
                 {"volume_sma_20": vol_sma20, "current_volume": current_vol},
                 s, "volume", HorizonRelevance.short)
    except Exception:
        pass

    # ── 18. 52-Week High/Low Ratio ────────────────────────────────────────────
    try:
        n52   = min(252, n)
        h52   = _f(high.iloc[-n52:].max())
        l52   = _f(low.iloc[-n52:].min())
        r52   = _f((price - l52) / (h52 - l52)) if h52 and l52 and h52 != l52 else None
        if h52 and l52:
            s = ("Near 52W High" if r52 and r52 >= 0.8
                 else "Near 52W Low" if r52 and r52 <= 0.2
                 else "Neutral")
            emit("52W_HL_Ratio",
                 f"52W: {l52:.0f}–{h52:.0f}, CMP: {price:.0f} ({(r52 or 0)*100:.0f}%)",
                 {"high": h52, "low": l52, "price": price, "ratio": r52},
                 s, "week_52_ratio", HorizonRelevance.both)
    except Exception:
        pass

    return nodes


# ── Legacy dict converter ─────────────────────────────────────────────────────

def _nodes_to_legacy_dict(nodes: list[Node]) -> dict:
    """Convert node list back to the flat dict the v1 router expects."""
    d: dict = {}
    for node in nodes:
        raw = node.value_raw
        name = node.name
        sig = raw.get("_signal", "Neutral")  # stored by emit() for round-trip accuracy
        if name == "RSI_14":
            d.update({"rsi": raw.get("rsi"), "rsi_signal": sig})
        elif name == "MACD":
            d.update({"macd": raw.get("macd"), "macd_signal_line": raw.get("signal"),
                      "macd_histogram": raw.get("histogram"), "macd_signal": sig})
        elif name == "ADX_14":
            d.update({"adx": raw.get("adx"), "adx_signal": sig})
        elif name == "ATR_14":
            d.update({"atr": raw.get("atr")})
        elif name in ("Bollinger_Bands", "Bollinger_Upper", "Bollinger_Lower"):
            d.update({"bb_upper": raw.get("upper"), "bb_middle": raw.get("middle"),
                      "bb_lower": raw.get("lower"), "bb_signal": sig})
        elif name == "EMA":
            d.update({"ema_20": raw.get("ema_20"), "ema_50": raw.get("ema_50"),
                      "ema_200": raw.get("ema_200"), "ema_signal": sig})
        elif name == "SMA":
            d.update({"sma_20": raw.get("sma_20"), "sma_50": raw.get("sma_50"),
                      "sma_200": raw.get("sma_200")})
        elif name == "Ichimoku":
            d.update({"ichimoku_a": raw.get("ichimoku_a"), "ichimoku_b": raw.get("ichimoku_b")})
        elif name == "Parabolic_SAR":
            d.update({"psar": raw.get("psar"), "psar_signal": sig})
        elif name == "Stochastic":
            d.update({"stoch_k": raw.get("stoch_k"), "stoch_d": raw.get("stoch_d"),
                      "stoch_signal": sig})
        elif name == "Williams_R":
            d.update({"williams_r": raw.get("williams_r"), "williams_r_signal": sig})
        elif name == "ROC":
            d.update({"roc": raw.get("roc_pct")})
        elif name == "OBV":
            d.update({"obv": raw.get("obv"), "obv_signal": sig})
        elif name == "VWAP":
            d.update({"vwap": raw.get("vwap"), "vwap_signal": sig})
        elif name == "CMF":
            d.update({"cmf": raw.get("cmf")})
        elif name == "MFI":
            d.update({"mfi": raw.get("mfi")})
        elif name == "Volume_SMA20":
            d.update({"volume_sma_20": raw.get("volume_sma_20")})
        elif name == "52W_HL_Ratio":
            d.update({"week_52_high": raw.get("high"), "week_52_low": raw.get("low"),
                      "week_52_ratio": raw.get("ratio")})
    return d


# ── Signal mapper ─────────────────────────────────────────────────────────────

_POSITIVE = {"Oversold", "Bullish", "Bullish Confirmation", "Bullish Divergence",
             "Above Cloud", "Near 52W Low", "Strong Trend", "Trend"}
_NEGATIVE = {"Overbought", "Bearish", "Bearish Confirmation", "Bearish Divergence",
             "Below Cloud", "Near 52W High", "High Volatility"}


def _map_signal(s: str) -> NodeSignal | None:
    """Convert signal string to NodeSignal. Returns None if unrecognised."""
    if s in _POSITIVE:
        return NodeSignal.positive
    if s in _NEGATIVE:
        return NodeSignal.negative
    return NodeSignal.neutral


# ── Math helpers ──────────────────────────────────────────────────────────────

def _f(val: Any) -> float | None:
    try:
        v = float(val)
        return None if pd.isna(v) else round(v, 4)
    except Exception:
        return None


def _last_valid(series: pd.Series) -> float | None:
    try:
        cleaned = series.dropna()
        return _f(cleaned.iloc[-1]) if not cleaned.empty else None
    except Exception:
        return None


def _get_weight(weights: dict, category: str, key: str, horizon: str) -> float:
    try:
        return float(weights[category][key][horizon])
    except (KeyError, TypeError, ValueError):
        return 0.0
