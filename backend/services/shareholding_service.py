"""
shareholding_service.py — Shareholding pattern waterfall: NSE → Screener.

Waterfall:
  L1: NSE shareholding() (promoter/FII/DII/retail — confidence=1.0, ~80% coverage)
  L2: Screener shareholding table (confidence=0.85, higher coverage)

Output nodes (all NodeCategory.fundamental):
  Promoter_Holding      — % stake; signal based on trend (rising → positive)
  FII_Holding           — foreign institutional; rising → positive
  DII_Holding           — domestic institutional; combined DII+MF
  Public_Retail_Holding — residual public stake
  MF_Holding            — mutual fund subset of DII (Screener MF drilldown if available)

Signal logic (ARCHITECTURE.md §4.1):
  Promoter_Holding:  holding > 50% positive; pledging data from ratios_service.
  FII/DII trend:     QoQ increase → positive; decrease → negative; flat → neutral.
  No threshold-based signals for absolute % — context matters (sector, peers).
  Promoter_Pledging: handled in ratios_service (weight: promoter_pledging).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from fetchers import nse_client, screener_client
from fetchers.base import waterfall, WaterfallFailure
from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from schemas.messages import UserProfile
from config import yaml_cfg
from util.ist_calendar import now_ist

logger = logging.getLogger(__name__)


async def get_shareholding(
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
    request_id: str = "",
) -> list[Node]:
    """
    Fetch shareholding pattern and return Node list.

    Args:
        symbol:     NSE ticker in uppercase.
        as_of_date: Analysis date.
        profile:    User profile for weight selection.
        request_id: Trace ID for logging.

    Returns:
        list[Node] with up to 5 shareholding nodes.
    """
    symbol = symbol.upper().strip()

    async def _nse() -> dict[str, Any]:
        return await nse_client.fetch_shareholding(symbol)

    async def _screener() -> dict[str, Any]:
        data = await screener_client.fetch_financials(symbol)
        result = data.get("shareholding") or {}
        result["_mf"] = data.get("mf_holdings") or {}
        return result

    try:
        result = await waterfall.run([
            ("nse_library", 1.00, _nse),
            ("screener_in", 0.85, _screener),
        ], request_id=request_id or f"shareholding:{symbol}:{as_of_date}")
    except WaterfallFailure as exc:
        logger.warning("Shareholding waterfall exhausted for %s: %s", symbol, exc)
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
    nodes: list[Node] = []
    horizon = profile.horizon.value
    weights = yaml_cfg.weights
    w_ver   = yaml_cfg.versions.get("weight_version", "")

    def _add(name: str, value_str: str, value_raw: dict, signal: NodeSignal,
             weight_key: str) -> None:
        w = _get_weight(weights, "fundamental", weight_key, horizon)
        nodes.append(Node(
            stock=symbol, category=NodeCategory.fundamental, name=name,
            value=value_str, value_raw=value_raw, signal=signal,
            confidence=confidence, source=source_id, source_url="",
            as_of_date=as_of_date, fetched_at_ist=fetched_at,
            horizon_relevance=HorizonRelevance.long, weight=w, weight_version=w_ver,
            sanitized=False,
        ))

    # ── NSE source path ───────────────────────────────────────────────────────
    if source_id == "nse_library":
        promoter = _to_float(raw.get("promoter"))
        fii      = _to_float(raw.get("fii"))
        dii      = _to_float(raw.get("dii"))
        retail   = _to_float(raw.get("retail") or raw.get("others"))

        if promoter is not None:
            sig = NodeSignal.positive if promoter >= 50 else NodeSignal.neutral
            _add("Promoter_Holding", f"Promoter: {promoter:.1f}%",
                 {"current_pct": promoter, "period": raw.get("period", ""),
                  "prev_quarter_pct": None, "change_pct": None},
                 sig, "promoter_holding_trend")

        if fii is not None:
            _add("FII_Holding", f"FII: {fii:.1f}%",
                 {"current_pct": fii, "period": raw.get("period", ""),
                  "prev_quarter_pct": None, "change_pct": None},
                 NodeSignal.neutral, "fii_holding_trend")

        if dii is not None:
            _add("DII_Holding", f"DII: {dii:.1f}%",
                 {"current_pct": dii, "period": raw.get("period", ""),
                  "prev_quarter_pct": None, "change_pct": None},
                 NodeSignal.neutral, "dii_mf_holding_trend")

        if retail is not None:
            _add("Public_Retail_Holding", f"Public/Retail: {retail:.1f}%",
                 {"current_pct": retail},
                 NodeSignal.neutral, "promoter_holding_trend")

        return nodes

    # ── Screener source path ──────────────────────────────────────────────────
    # Screener shareholding table: rows = [{label, values}], headers = [period strings]
    headers = raw.get("headers", [])
    rows    = raw.get("rows", [])

    def _find_row(*hints: str) -> list[float]:
        """Return values list for a row matching any hint."""
        for row in rows:
            label = (row.get("label") or "").lower()
            if any(h in label for h in hints):
                return [v for v in row.get("values", []) if _to_float(v) is not None]
        return []

    prom_vals = _find_row("promoter", "promoters")
    fii_vals  = _find_row("fii", "foreign institutional", "fpi", "foreign portfolio")
    dii_vals  = _find_row("dii", "domestic institutional")
    pub_vals  = _find_row("public", "retail", "others")

    if prom_vals:
        curr, prev = _to_float(prom_vals[0]), (_to_float(prom_vals[1]) if len(prom_vals) > 1 else None)
        chg = round(curr - prev, 2) if prev is not None else None
        sig = (_growth_signal_holding(chg)
               if chg is not None
               else (NodeSignal.positive if curr >= 50 else NodeSignal.neutral))
        _add("Promoter_Holding", f"Promoter: {curr:.1f}%",
             _holding_raw(curr, prev, chg, headers[:len(prom_vals)], prom_vals),
             sig, "promoter_holding_trend")

    if fii_vals:
        curr, prev = _to_float(fii_vals[0]), (_to_float(fii_vals[1]) if len(fii_vals) > 1 else None)
        chg = round(curr - prev, 2) if prev is not None else None
        _add("FII_Holding", f"FII: {curr:.1f}%",
             _holding_raw(curr, prev, chg, headers[:len(fii_vals)], fii_vals),
             _growth_signal_holding(chg), "fii_holding_trend")

    if dii_vals:
        curr, prev = _to_float(dii_vals[0]), (_to_float(dii_vals[1]) if len(dii_vals) > 1 else None)
        chg = round(curr - prev, 2) if prev is not None else None
        _add("DII_Holding", f"DII: {curr:.1f}%",
             _holding_raw(curr, prev, chg, headers[:len(dii_vals)], dii_vals),
             _growth_signal_holding(chg), "dii_mf_holding_trend")

    if pub_vals:
        curr = _to_float(pub_vals[0])
        _add("Public_Retail_Holding", f"Public/Retail: {curr:.1f}%",
             {"current_pct": curr}, NodeSignal.neutral, "promoter_holding_trend")

    return nodes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _holding_raw(
    curr: float,
    prev: float | None,
    chg: float | None,
    periods: list,
    values: list,
) -> dict:
    """Build value_raw dict for a shareholding node."""
    quarters = [{"period": str(p), "pct": _to_float(v)}
                for p, v in zip(periods[:6], values[:6])]
    return {
        "current_pct":      curr,
        "prev_quarter_pct": prev,
        "change_pct":       chg,
        "quarters":         quarters,
    }


def _growth_signal_holding(change: float | None) -> NodeSignal:
    """Institutional holding increase = positive; decrease = negative."""
    if change is None:
        return NodeSignal.neutral
    if change > 0.5:
        return NodeSignal.positive
    if change < -0.5:
        return NodeSignal.negative
    return NodeSignal.neutral


def _get_weight(weights: dict, category: str, key: str, horizon: str) -> float:
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
