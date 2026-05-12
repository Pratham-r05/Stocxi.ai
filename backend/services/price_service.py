"""
price_service.py — Live price waterfall: NSE → BSE → yfinance.

Waterfall:
  L1: NSE equityQuote (confidence=1.0)
  L2: BSE quote        (confidence=1.0)
  L3: yfinance         (confidence=0.7)

Output nodes:
  Price           — current market price
  Change_Pct      — day change percentage
  VWAP            — volume-weighted average price (from NSE; neutral/absent otherwise)

Node values follow ARCHITECTURE.md §4.1 format rules.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from fetchers import bse_client, nse_client, yfinance_client
from fetchers.base import waterfall, WaterfallFailure
from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from schemas.messages import UserProfile
from config import yaml_cfg
from util.ist_calendar import now_ist
from services.symbol_service import canonicalize_symbol

logger = logging.getLogger(__name__)

_CAT = NodeCategory.fundamental   # price nodes are context-level fundamentals


async def get_price(
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
    request_id: str = "",
) -> list[Node]:
    """
    Fetch live price data and return Node list.

    Args:
        symbol:     NSE ticker in uppercase.
        as_of_date: Date of the analysis (used for node identity + backtest safety).
        profile:    User profile — determines horizon for weight selection.
        request_id: Trace ID passed into waterfall logging.

    Returns:
        list[Node] — 1 to 3 nodes: Price (always), Change_Pct (if available),
        VWAP (if available from NSE). Empty list if all sources fail.
    """
    symbol = canonicalize_symbol(symbol)
    bse_code = await _try_bse_code(symbol)

    async def _nse() -> dict[str, Any]:
        return await nse_client.fetch_quote(symbol)

    async def _bse() -> dict[str, Any]:
        if not bse_code:
            raise ValueError("BSE code not resolved")
        return await bse_client.fetch_quote(symbol)

    async def _yf() -> dict[str, Any]:
        return await yfinance_client.fetch_quote(symbol)

    try:
        result = await waterfall.run([
            ("nse_library", 1.00, _nse),
            ("bse_library", 1.00, _bse),
            ("yfinance",    0.70, _yf),
        ], request_id=request_id or f"price:{symbol}:{as_of_date}")
    except WaterfallFailure as exc:
        logger.warning("Price waterfall exhausted for %s: %s", symbol, exc)
        return []

    return _build_nodes(result.payload, symbol, as_of_date,
                        result.source_id, result.confidence,
                        profile, now_ist())


# ── Node builder ──────────────────────────────────────────────────────────────

def _build_nodes(
    raw: dict,
    symbol: str,
    as_of_date: date,
    source_id: str,
    confidence: float,
    profile: UserProfile,
    fetched_at: datetime,
) -> list[Node]:
    """Convert a raw quote dict into price Nodes."""
    nodes: list[Node] = []
    horizon = profile.horizon.value
    weights = yaml_cfg.weights
    w_ver   = yaml_cfg.versions.get("weight_version", "")

    close = _to_float(raw.get("close"))
    if close is None or close <= 0:
        logger.warning("Price node: no valid close price from %s for %s", source_id, symbol)
        return []

    # ── Price node ────────────────────────────────────────────────────────────
    nodes.append(Node(
        stock=symbol,
        category=NodeCategory.context,
        name="Price",
        value=f"₹{close:,.2f}",
        value_raw={
            "price":          close,
            "open":           _to_float(raw.get("open")),
            "high":           _to_float(raw.get("high")),
            "low":            _to_float(raw.get("low")),
            "volume":         raw.get("volume"),
            "market_cap_cr":  _to_float(raw.get("market_cap_cr")),
            "company_name":   raw.get("company_name", symbol),
            "isin":           raw.get("isin", ""),
        },
        signal=NodeSignal.neutral,
        confidence=confidence,
        source=source_id,
        source_url=raw.get("source_url", ""),
        as_of_date=as_of_date,
        fetched_at_ist=fetched_at,
        horizon_relevance=HorizonRelevance.both,
        weight=0.0,   # Price node is always included; no individual weight
        weight_version=w_ver,
        sanitized=False,
    ))

    # ── Change_Pct node ───────────────────────────────────────────────────────
    chg_pct = _to_float(raw.get("change_pct"))
    if chg_pct is not None:
        signal = (NodeSignal.positive if chg_pct > 0
                  else NodeSignal.negative if chg_pct < 0
                  else NodeSignal.neutral)
        nodes.append(Node(
            stock=symbol,
            category=NodeCategory.technical,
            name="Change_Pct",
            value=f"{'+' if chg_pct >= 0 else ''}{chg_pct:.2f}% (₹{_to_float(raw.get('change')) or 0:+.2f})",
            value_raw={
                "change_pct":     chg_pct,
                "change":         _to_float(raw.get("change")),
                "previous_close": _to_float(raw.get("previous_close")),
            },
            signal=signal,
            confidence=confidence,
            source=source_id,
            source_url="",
            as_of_date=as_of_date,
            fetched_at_ist=fetched_at,
            horizon_relevance=HorizonRelevance.short,   # day change is short-term signal
            weight=0.0,
            weight_version=w_ver,
            sanitized=False,
        ))

    # ── VWAP node ─────────────────────────────────────────────────────────────
    vwap = _to_float(raw.get("vwap"))
    if vwap and vwap > 0:
        vwap_signal = (NodeSignal.positive if close > vwap
                       else NodeSignal.negative if close < vwap
                       else NodeSignal.neutral)
        vwap_weight = _get_weight(weights, "technical", "vwap", horizon)
        nodes.append(Node(
            stock=symbol,
            category=NodeCategory.technical,
            name="VWAP",
            value=f"VWAP: ₹{vwap:,.2f}, Price: ₹{close:,.2f}",
            value_raw={"vwap": vwap, "price": close},
            signal=vwap_signal,
            confidence=confidence,
            source=source_id,
            source_url="",
            as_of_date=as_of_date,
            fetched_at_ist=fetched_at,
            horizon_relevance=HorizonRelevance.short,
            weight=vwap_weight,
            weight_version=w_ver,
            sanitized=False,
        ))

    return nodes


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _try_bse_code(symbol: str) -> str | None:
    """Resolve BSE code silently — failure means BSE level will be skipped."""
    try:
        return await bse_client.resolve_scrip_code(symbol)
    except Exception:
        return None


def _get_weight(weights: dict, category: str, key: str, horizon: str) -> float:
    """Look up weight from weights.yaml. Returns 0.0 if not found."""
    try:
        return float(weights[category][key][horizon])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f
    except (ValueError, TypeError):
        return None
