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

from fetchers import bse_client, screener_client
from fetchers.base import waterfall, WaterfallFailure
from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from schemas.messages import UserProfile
from config import yaml_cfg
from util.ist_calendar import now_ist
from services.symbol_service import canonicalize_symbol

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
    symbol = canonicalize_symbol(symbol)

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

    # Total Debt and D/E (from balance sheet)
    debt      = _extract_series(raw.get("balance_sheet", {}), "borrowings", "total debt", "debt")
    # Net Worth = Equity Capital + Reserves — searched separately to avoid matching
    # "Equity Capital" alone (which is just paid-up share capital, ~1-3 Cr for small-caps,
    # not the full shareholders' equity). Screener doesn't expose a combined "Net Worth" row.
    share_cap = _extract_series(raw.get("balance_sheet", {}), "equity capital", "share capital", "paid-up capital")
    reserves  = _extract_series(raw.get("balance_sheet", {}), "reserves", "reserves and surplus")
    if debt["values"]:
        debt_cr   = debt["values"][0]
        sc_cr     = share_cap["values"][0] if share_cap["values"] else 0.0
        res_cr    = reserves["values"][0]  if reserves["values"]  else 0.0
        equity_cr = (sc_cr + res_cr) if (sc_cr + res_cr) > 0 else None
        de_ratio  = round(debt_cr / equity_cr, 2) if equity_cr else None
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

    # ── TTM metrics + EBITDA + FCF + Interest Coverage + Market Cap ─────────────

    # Revenue TTM (sum last 4 quarters)
    if len(qr["values"]) >= 4:
        ttm_rev = sum(qr["values"][:4])
        prev_ttm = sum(qr["values"][4:8]) if len(qr["values"]) >= 8 else None
        yoy_g = _growth_pct(ttm_rev, prev_ttm)
        _add("Revenue_TTM",
             f"Rev TTM: ₹{ttm_rev:,.0f} Cr" + (f" ({yoy_g:+.1f}% YoY)" if yoy_g else ""),
             {"ttm_cr": ttm_rev, "yoy_growth_pct": yoy_g},
             _growth_signal(yoy_g), "revenue_growth_yoy", HorizonRelevance.both)

    # Revenue_Growth_YoY — separate directional node
    if len(qr["values"]) >= 8:
        ttm_now  = sum(qr["values"][:4])
        ttm_prev = sum(qr["values"][4:8])
        yoy_g    = _growth_pct(ttm_now, ttm_prev)
        if yoy_g is not None:
            _add("Revenue_Growth_YoY",
                 f"Revenue YoY: {yoy_g:+.1f}%",
                 {"yoy_growth_pct": yoy_g},
                 _growth_signal(yoy_g), "revenue_growth_yoy", HorizonRelevance.long)

    # PAT TTM
    if len(qp["values"]) >= 4:
        ttm_pat  = sum(qp["values"][:4])
        prev_ttm = sum(qp["values"][4:8]) if len(qp["values"]) >= 8 else None
        yoy_g    = _growth_pct(ttm_pat, prev_ttm)
        _add("PAT_TTM",
             f"PAT TTM: ₹{ttm_pat:,.0f} Cr" + (f" ({yoy_g:+.1f}% YoY)" if yoy_g else ""),
             {"ttm_cr": ttm_pat, "yoy_growth_pct": yoy_g},
             _growth_signal(yoy_g), "profit_growth_yoy", HorizonRelevance.both)

    # PAT_Growth_YoY — separate directional node
    if len(qp["values"]) >= 8:
        ttm_now  = sum(qp["values"][:4])
        ttm_prev = sum(qp["values"][4:8])
        yoy_g    = _growth_pct(ttm_now, ttm_prev)
        if yoy_g is not None:
            _add("PAT_Growth_YoY",
                 f"PAT YoY: {yoy_g:+.1f}%",
                 {"yoy_growth_pct": yoy_g},
                 _growth_signal(yoy_g), "profit_growth_yoy", HorizonRelevance.long)

    # EBITDA TTM (quarterly Operating Profit, sum of last 4 quarters)
    qop = _extract_series(raw.get("quarterly_results", {}), "operating profit", "ebitda")
    if len(qop["values"]) >= 4:
        ttm_ebitda = sum(qop["values"][:4])
        prev_ttm   = sum(qop["values"][4:8]) if len(qop["values"]) >= 8 else None
        yoy_g      = _growth_pct(ttm_ebitda, prev_ttm)
        _add("EBITDA_TTM",
             f"EBITDA TTM: ₹{ttm_ebitda:,.0f} Cr" + (f" ({yoy_g:+.1f}% YoY)" if yoy_g else ""),
             {"ttm_cr": ttm_ebitda, "yoy_growth_pct": yoy_g},
             _growth_signal(yoy_g), "profit_growth_yoy", HorizonRelevance.long)

    # EBITDA Margin (latest OPM %)
    qopm = _extract_series(raw.get("quarterly_results", {}), "opm %", "opm%", "operating margin")
    if qopm["values"]:
        opm_latest = qopm["values"][0]
        sig = (NodeSignal.positive if opm_latest > 20
               else NodeSignal.negative if opm_latest < 5
               else NodeSignal.neutral)
        _add("EBITDA_Margin",
             f"EBITDA Margin: {opm_latest:.1f}%",
             {"opm_pct": opm_latest, "period": qopm["periods"][0] if qopm["periods"] else ""},
             sig, "valuation", HorizonRelevance.long)

    # Free Cash Flow (annual)
    fcf = _extract_series(raw.get("cash_flow", {}), "free cash flow", "fcf")
    if fcf["values"]:
        fcf_cr = fcf["values"][0]
        sig = NodeSignal.positive if fcf_cr > 0 else NodeSignal.negative
        _add("Free_Cashflow",
             f"FCF: ₹{fcf_cr:,.0f} Cr ({fcf['periods'][0] if fcf['periods'] else 'latest'})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(fcf["periods"][:3], fcf["values"][:3])]},
             sig, "cash_flow_ops", HorizonRelevance.long)

    # Interest Coverage (Operating Profit / Interest — annual)
    op_annual  = _extract_series(raw.get("annual_results", {}), "operating profit", "ebitda")
    int_annual = _extract_series(raw.get("annual_results", {}), "interest")
    if (op_annual["values"] and int_annual["values"]
            and int_annual["values"][0] is not None and int_annual["values"][0] > 0):
        ic  = round(op_annual["values"][0] / int_annual["values"][0], 1)
        sig = (NodeSignal.positive if ic > 3
               else NodeSignal.negative if ic < 1.5
               else NodeSignal.neutral)
        _add("Interest_Coverage",
             f"Interest Coverage: {ic:.1f}x",
             {"ratio": ic, "ebit_cr": op_annual["values"][0],
              "interest_cr": int_annual["values"][0]},
             sig, "debt_equity", HorizonRelevance.long)

    # Market Cap (from Screener ratios)
    mc_raw = _to_float((raw.get("ratios") or {}).get("market_cap"))
    if mc_raw is not None and mc_raw > 0:
        mc_cr = round(mc_raw / 1e7, 0)   # rupees → crores
        sig   = (NodeSignal.positive if mc_cr >= 20_000
                 else NodeSignal.neutral  if mc_cr >= 500
                 else NodeSignal.negative)
        _add("Market_Cap",
             f"Mkt Cap: ₹{mc_cr:,.0f} Cr",
             {"market_cap_cr": mc_cr},
             sig, "valuation", HorizonRelevance.both)

    # ── Additional Balance Sheet nodes ─────────────────────────────────────────
    ta = _extract_series(raw.get("balance_sheet", {}), "total assets")
    if len(ta["values"]) >= 2:
        growth = _growth_pct(ta["values"][0], ta["values"][1])
        sig = _growth_signal(growth)
        _add("Total_Assets",
             f"Total Assets: ₹{ta['values'][0]:,.0f} Cr ({ta['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(ta["periods"][:5], ta["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "debt_equity", HorizonRelevance.long)

    # Screener's "Total Liabilities" row = Total Assets (Indian balance sheet format:
    # both sides balance at Equity + External Liabilities = Total Assets).
    # We expose this as "Total_Capital" to prevent the LLM from misreading it as
    # "equity is zero / insolvency" when Total_Liabilities = Total_Assets.
    tl = _extract_series(raw.get("balance_sheet", {}), "total liabilities")
    eq_cap2  = _extract_series(raw.get("balance_sheet", {}), "equity capital", "share capital")
    res_cap2 = _extract_series(raw.get("balance_sheet", {}), "reserves", "reserves and surplus")
    if len(tl["values"]) >= 2:
        growth = _growth_pct(tl["values"][0], tl["values"][1])
        sig = (NodeSignal.negative if growth and growth > 15
               else NodeSignal.positive if growth and growth < 0
               else NodeSignal.neutral)
        equity_note = ""
        eq_cr  = eq_cap2["values"][0]  if eq_cap2["values"]  else None
        res_cr = res_cap2["values"][0] if res_cap2["values"] else None
        if eq_cr is not None and res_cr is not None:
            equity_note = f" (incl. ₹{eq_cr + res_cr:,.0f} Cr equity)"
        _add("Total_Liabilities",
             f"Total Assets: ₹{tl['values'][0]:,.0f} Cr ({tl['periods'][0]}){equity_note}",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(tl["periods"][:5], tl["values"][:5])],
              "yoy_growth_pct": growth,
              "screener_format_note": "Total Liabilities in Screener = Total Assets (both sides of Indian balance sheet). Equity Capital + Reserves + Borrowings + Other Liabilities = Total Assets."},
             sig, "debt_equity", HorizonRelevance.long)

    se = _extract_series(raw.get("balance_sheet", {}), "shareholders' equity", "total equity")
    if len(se["values"]) >= 2:
        growth = _growth_pct(se["values"][0], se["values"][1])
        sig = _growth_signal(growth)
        _add("Shareholders_Equity",
             f"Equity: ₹{se['values'][0]:,.0f} Cr ({se['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(se["periods"][:5], se["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "debt_equity", HorizonRelevance.long)

    res_bs = _extract_series(raw.get("balance_sheet", {}), "reserves and surplus", "reserves")
    if len(res_bs["values"]) >= 2:
        growth = _growth_pct(res_bs["values"][0], res_bs["values"][1])
        sig = _growth_signal(growth)
        _add("Reserves",
             f"Reserves: ₹{res_bs['values'][0]:,.0f} Cr ({res_bs['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(res_bs["periods"][:5], res_bs["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "debt_equity", HorizonRelevance.long)

    bor = _extract_series(raw.get("balance_sheet", {}), "borrowings", "total debt")
    if len(bor["values"]) >= 2:
        growth = _growth_pct(bor["values"][0], bor["values"][1])
        sig = (NodeSignal.negative if growth and growth > 15
               else NodeSignal.positive if growth and growth < 0
               else NodeSignal.neutral)
        _add("Borrowings",
             f"Borrowings: ₹{bor['values'][0]:,.0f} Cr ({bor['periods'][0]}) (YoY: {growth:+.1f}%)",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(bor["periods"][:5], bor["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "debt_equity", HorizonRelevance.long)
    elif bor["values"]:
        _add("Borrowings",
             f"Borrowings: ₹{bor['values'][0]:,.0f} Cr ({bor['periods'][0] if bor['periods'] else 'latest'})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(bor["periods"][:5], bor["values"][:5])]},
             NodeSignal.neutral, "debt_equity", HorizonRelevance.long)

    # ── Additional Quarterly Result nodes ──────────────────────────────────────
    qexp = _extract_series(raw.get("quarterly_results", {}), "expenses", "total expenditure")
    if len(qexp["values"]) >= 2:
        growth = _growth_pct(qexp["values"][0], qexp["values"][1])
        sig = (NodeSignal.negative if growth and growth > 15
               else NodeSignal.positive if growth and growth < 0
               else NodeSignal.neutral)
        _add("Expenses_Quarterly",
             f"Q Expenses: ₹{qexp['values'][0]:,.0f} Cr ({qexp['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(qexp["periods"][:8], qexp["values"][:8])],
              "yoy_growth_pct": _yoy_growth(qexp["values"])},
             sig, "revenue_growth_yoy", HorizonRelevance.both)

    qop2 = _extract_series(raw.get("quarterly_results", {}), "operating profit")
    if len(qop2["values"]) >= 2:
        growth = _growth_pct(qop2["values"][0], qop2["values"][1])
        sig = _growth_signal(growth)
        _add("Operating_Profit_Quarterly",
             f"Q OP: ₹{qop2['values'][0]:,.0f} Cr ({qop2['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(qop2["periods"][:8], qop2["values"][:8])],
              "yoy_growth_pct": _yoy_growth(qop2["values"])},
             sig, "profit_growth_yoy", HorizonRelevance.both)

    qopm2 = _extract_series(raw.get("quarterly_results", {}), "opm %", "opm%", "operating margin")
    if qopm2["values"]:
        opm_latest = qopm2["values"][0]
        sig = (NodeSignal.positive if opm_latest > 20
               else NodeSignal.negative if opm_latest < 5
               else NodeSignal.neutral)
        _add("OPM_Quarterly",
             f"Q OPM: {opm_latest:.1f}%",
             {"opm_pct": opm_latest, "period": qopm2["periods"][0] if qopm2["periods"] else "",
              "periods": [{"period": p, "value_pct": v}
                          for p, v in zip(qopm2["periods"][:8], qopm2["values"][:8])]},
             sig, "valuation", HorizonRelevance.both)

    # ── Additional Annual Result nodes ─────────────────────────────────────────
    aexp = _extract_series(raw.get("annual_results", {}), "expenses", "total expenditure")
    if len(aexp["values"]) >= 2:
        growth = _growth_pct(aexp["values"][0], aexp["values"][1])
        sig = (NodeSignal.negative if growth and growth > 15
               else NodeSignal.positive if growth and growth < 0
               else NodeSignal.neutral)
        _add("Expenses_Annual",
             f"FY Expenses: ₹{aexp['values'][0]:,.0f} Cr ({aexp['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(aexp["periods"][:5], aexp["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "revenue_growth_yoy", HorizonRelevance.long)

    aop = _extract_series(raw.get("annual_results", {}), "operating profit")
    if len(aop["values"]) >= 2:
        growth = _growth_pct(aop["values"][0], aop["values"][1])
        sig = _growth_signal(growth)
        _add("Operating_Profit_Annual",
             f"FY OP: ₹{aop['values'][0]:,.0f} Cr ({aop['periods'][0]})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(aop["periods"][:5], aop["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "profit_growth_yoy", HorizonRelevance.long)

    aopm2 = _extract_series(raw.get("annual_results", {}), "opm %", "opm%", "operating margin")
    if aopm2["values"]:
        opm_latest = aopm2["values"][0]
        sig = (NodeSignal.positive if opm_latest > 20
               else NodeSignal.negative if opm_latest < 5
               else NodeSignal.neutral)
        _add("OPM_Annual",
             f"FY OPM: {opm_latest:.1f}%",
             {"opm_pct": opm_latest, "period": aopm2["periods"][0] if aopm2["periods"] else "",
              "periods": [{"period": p, "value_pct": v}
                          for p, v in zip(aopm2["periods"][:5], aopm2["values"][:5])]},
             sig, "valuation", HorizonRelevance.long)

    aeps = _extract_series(raw.get("annual_results", {}), "eps", "earnings per share")
    if len(aeps["values"]) >= 2:
        growth = _growth_pct(aeps["values"][0], aeps["values"][1])
        sig = _growth_signal(growth)
        _add("EPS_Annual",
             f"FY EPS: ₹{aeps['values'][0]:.2f} ({aeps['periods'][0]})",
             {"periods": [{"period": p, "value_inr": v}
                          for p, v in zip(aeps["periods"][:5], aeps["values"][:5])],
              "yoy_growth_pct": growth},
             sig, "valuation", HorizonRelevance.long)

    # ── Additional Cash Flow nodes ──────────────────────────────────────────────
    cfi = _extract_series(raw.get("cash_flow", {}), "cash from investing", "investing activities")
    if cfi["values"]:
        cfi_cr = cfi["values"][0]
        sig = NodeSignal.neutral
        _add("Cash_From_Investing",
             f"CFI: ₹{cfi_cr:,.0f} Cr ({cfi['periods'][0] if cfi['periods'] else 'latest'})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(cfi["periods"][:3], cfi["values"][:3])]},
             sig, "cash_flow_ops", HorizonRelevance.long)

    cff = _extract_series(raw.get("cash_flow", {}), "cash from financing", "financing activities")
    if cff["values"]:
        cff_cr = cff["values"][0]
        sig = NodeSignal.neutral
        _add("Cash_From_Financing",
             f"CFF: ₹{cff_cr:,.0f} Cr ({cff['periods'][0] if cff['periods'] else 'latest'})",
             {"periods": [{"period": p, "value_cr": v}
                          for p, v in zip(cff["periods"][:3], cff["values"][:3])]},
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
