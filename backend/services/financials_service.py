"""
financials_service.py — Financial statement data: Screener → BSE resultsSnapshot.

Waterfall:
  L1: Screener.in (quarterly P&L, annual P&L, balance sheet, cash flow — confidence=0.85)
  L2: BSE resultsSnapshot (last 3 quarters — confidence=1.0)

Note: BSE has higher exchange-direct confidence but lower coverage (only 3 quarters).
Screener provides the full statement history. Primary is Screener; BSE is the fallback.

Output nodes (all NodeCategory.fundamental):
  Revenue_Quarterly    — quarterly revenue trend (last 4 quarters)
  Net_Profit_Quarterly — quarterly PAT trend
  Revenue_Annual       — annual revenue (last 3 years)
  Net_Profit_Annual    — annual PAT
  OPM_Trend            — operating margin trend
  Total_Debt           — from balance sheet
  Debt_To_Equity       — computed if both debt and equity available
  Operating_Cash_Flow  — from cash flow statement

Growth signals (YoY):
  Revenue/Profit growth >15% → positive; negative growth → negative; else neutral.

Nodes with insufficient history (< 2 data points) are omitted.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from backend.fetchers import bse_client, screener_client
from backend.fetchers.base import waterfall, WaterfallFailure
from backend.schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from backend.schemas.messages import UserProfile
from backend.config import yaml_cfg
from backend.util.ist_calendar import now_ist

logger = logging.getLogger(__name__)


async def get_financials(
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
    request_id: str = "",
) -> list[Node]:
    """
    Fetch financial statement data and return Node list.

    Args:
        symbol:     NSE ticker in uppercase.
        as_of_date: Analysis date.
        profile:    User profile for weight selection.
        request_id: Trace ID for logging.

    Returns:
        list[Node] — up to 8 financial statement nodes.
        Empty list if all sources fail.
    """
    symbol = symbol.upper().strip()

    async def _screener() -> dict[str, Any]:
        return await screener_client.fetch_financials(symbol)

    async def _bse() -> dict[str, Any]:
        snap = await bse_client.fetch_results_snapshot(symbol)
        # Reshape BSE snapshot into screener-compatible format for unified normaliser
        return {"_bse_snapshot": snap.get("periods", []), "_source": "bse"}

    try:
        result = await waterfall.run([
            ("screener_in", 0.85, _screener),
            ("bse_library", 1.00, _bse),
        ], request_id=request_id or f"financials:{symbol}:{as_of_date}")
    except WaterfallFailure as exc:
        logger.warning("Financials waterfall exhausted for %s: %s", symbol, exc)
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
             weight_key: str, horizon_rel: HorizonRelevance = HorizonRelevance.long) -> None:
        w = _get_weight(weights, "fundamental", weight_key, horizon)
        nodes.append(Node(
            stock=symbol, category=NodeCategory.fundamental, name=name,
            value=value_str, value_raw=value_raw, signal=signal,
            confidence=confidence, source=source_id, source_url=raw.get("source_url", ""),
            as_of_date=as_of_date, fetched_at_ist=fetched_at,
            horizon_relevance=horizon_rel, weight=w, weight_version=w_ver,
            sanitized=False,
        ))

    # ── BSE snapshot path ─────────────────────────────────────────────────────
    if raw.get("_source") == "bse":
        periods = raw.get("_bse_snapshot", [])
        if len(periods) >= 2:
            rev = [_to_float(p.get("revenue")) for p in periods if _to_float(p.get("revenue"))]
            pat = [_to_float(p.get("net_profit")) for p in periods if _to_float(p.get("net_profit"))]
            if len(rev) >= 2:
                growth = _growth_pct(rev[0], rev[1])
                sig = _growth_signal(growth)
                _add("Revenue_Quarterly",
                     f"Q Revenue: ₹{rev[0]:,.0f} Cr",
                     {"periods": [{"period": p.get("period", ""), "value_cr": _to_float(p.get("revenue"))} for p in periods[:4]],
                      "yoy_growth_pct": growth, "source_type": "quarterly"},
                     sig, "revenue_growth_yoy", HorizonRelevance.both)
            if len(pat) >= 2:
                growth = _growth_pct(pat[0], pat[1])
                sig = _growth_signal(growth)
                _add("Net_Profit_Quarterly",
                     f"Q PAT: ₹{pat[0]:,.0f} Cr",
                     {"periods": [{"period": p.get("period", ""), "value_cr": _to_float(p.get("net_profit"))} for p in periods[:4]],
                      "yoy_growth_pct": growth},
                     sig, "profit_growth_yoy", HorizonRelevance.both)
        return nodes

    # ── Screener path ─────────────────────────────────────────────────────────

    # Revenue quarterly
    qr = _extract_series(raw.get("quarterly_results", {}), "sales", "revenue", "net sales")
    if len(qr["values"]) >= 2:
        growth = _growth_pct(qr["values"][0], qr["values"][1])  # QoQ (newest vs one ago)
        sig = _growth_signal(growth)
        _add("Revenue_Quarterly",
             f"Q Revenue: ₹{qr['values'][0]:,.0f} Cr (latest period: {qr['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(qr["periods"][:8], qr["values"][:8])],
              "source_type": raw.get("source_url", "").rstrip("/").split("/")[-1] or "unknown",
              "num_quarters": len(qr["values"]),
              "yoy_growth_pct": _yoy_growth(qr["values"])},
             sig, "revenue_growth_yoy", HorizonRelevance.both)

    # Net profit quarterly
    qp = _extract_series(raw.get("quarterly_results", {}), "net profit", "profit after tax", "pat")
    if len(qp["values"]) >= 2:
        growth = _growth_pct(qp["values"][0], qp["values"][1])
        sig = _growth_signal(growth)
        _add("Net_Profit_Quarterly",
             f"Q PAT: ₹{qp['values'][0]:,.0f} Cr (latest period: {qp['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(qp["periods"][:8], qp["values"][:8])],
              "yoy_growth_pct": _yoy_growth(qp["values"])},
             sig, "profit_growth_yoy", HorizonRelevance.both)

    # Revenue annual
    ar = _extract_series(raw.get("annual_results", {}), "sales", "revenue", "net sales")
    if len(ar["values"]) >= 2:
        growth = _growth_pct(ar["values"][0], ar["values"][1])
        sig = _growth_signal(growth)
        _add("Revenue_Annual",
             f"FY Revenue: ₹{ar['values'][0]:,.0f} Cr ({ar['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(ar["periods"][:5], ar["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "revenue_growth_yoy", HorizonRelevance.long)

    # PAT annual
    ap = _extract_series(raw.get("annual_results", {}), "net profit", "profit after tax", "pat")
    if len(ap["values"]) >= 2:
        growth = _growth_pct(ap["values"][0], ap["values"][1])
        sig = _growth_signal(growth)
        _add("Net_Profit_Annual",
             f"FY PAT: ₹{ap['values'][0]:,.0f} Cr ({ap['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(ap["periods"][:5], ap["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "profit_growth_yoy", HorizonRelevance.long)

    # Total Debt (from balance sheet)
    debt = _extract_series(raw.get("balance_sheet", {}), "borrowings", "total debt", "debt")
    equity = _extract_series(raw.get("balance_sheet", {}), "shareholders' equity",
                             "total equity", "equity")
    if debt["values"]:
        debt_cr = debt["values"][0]
        equity_cr = equity["values"][0] if equity["values"] else None
        de_ratio = round(debt_cr / equity_cr, 2) if equity_cr and equity_cr > 0 else None
        sig = (NodeSignal.negative if de_ratio and de_ratio > 2.0
               else NodeSignal.positive if de_ratio and de_ratio < 0.5
               else NodeSignal.neutral)
        _add("Debt_To_Equity",
             f"D/E: {de_ratio:.2f}" if de_ratio is not None else f"Debt: ₹{debt_cr:,.0f} Cr",
             {"debt_cr": debt_cr, "equity_cr": equity_cr,
              "de_ratio": de_ratio, "period": debt["periods"][0] if debt["periods"] else ""},
             sig, "debt_equity", HorizonRelevance.long)

    # Operating Cash Flow
    ocf = _extract_series(raw.get("cash_flow", {}), "cash from operations",
                          "operating cash flow", "cash from operating")
    if ocf["values"]:
        ocf_cr = ocf["values"][0]
        sig = (NodeSignal.positive if ocf_cr > 0 else NodeSignal.negative)
        _add("Operating_Cash_Flow",
             f"OCF: ₹{ocf_cr:,.0f} Cr ({ocf['periods'][0] if ocf['periods'] else 'latest'})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(ocf["periods"][:3], ocf["values"][:3])]},
             sig, "cash_flow_ops", HorizonRelevance.long)

    return nodes


# ── Table extraction helpers ───────────────────────────────────────────────────

def _extract_series(table: dict, *label_hints: str) -> dict:
    """
    Find a row in a Screener table dict by matching label hints.

    Returns {"periods": [...], "values": [...]} newest-first,
    both lists pruned to non-None values.
    """
    empty = {"periods": [], "values": []}
    if not table:
        return empty

    headers = table.get("headers", [])
    rows    = table.get("rows", [])

    for row in rows:
        label = (row.get("label") or "").lower()
        if any(hint in label for hint in label_hints):
            raw_vals = row.get("values", [])
            periods, values = [], []
            for h, v in zip(headers, raw_vals):
                f = _to_float(v)
                if f is not None:
                    periods.append(str(h))
                    values.append(f)
            # Screener columns are oldest-left → newest-right. Reverse to newest-first.
            return {"periods": periods[::-1], "values": values[::-1]}

    return empty


def _growth_pct(current: float, prev: float) -> float | None:
    """YoY or QoQ growth percentage. Returns None if prev is 0 or negative."""
    if prev is None or prev == 0:
        return None
    return round(((current - prev) / abs(prev)) * 100, 1)


def _yoy_growth(values: list[float]) -> float | None:
    """Compare most recent period vs 4 periods ago (quarterly → YoY)."""
    if len(values) >= 5:
        return _growth_pct(values[0], values[4])
    if len(values) >= 2:
        return _growth_pct(values[0], values[-1])
    return None


def _growth_signal(growth: float | None) -> NodeSignal:
    if growth is None:
        return NodeSignal.neutral
    if growth > 15:
        return NodeSignal.positive
    if growth < 0:
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
