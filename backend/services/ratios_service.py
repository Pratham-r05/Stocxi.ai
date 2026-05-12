"""
ratios_service.py — Key fundamental ratios waterfall: BSE → Screener → yfinance.

Waterfall:
  L1: BSE equityMetaInfo (PE/EPS/ROE/PB/OPM/NPM — confidence=1.0)
  L2: Screener top-ratios (ROCE/ROE/PE/book value — confidence=0.85)
  L3: yfinance fundamentals (market cap, basic ratios — confidence=0.70, not built yet)

Output nodes (all NodeCategory.fundamental):
  PE_Ratio, PB_Ratio, ROE, EPS, OPM, NPM, ROCE, Dividend_Yield

Signal logic follows ARCHITECTURE.md §4.1:
  PE_Ratio:      pe < sector_pe → positive; pe > 2× sector_pe → negative
  PB_Ratio:      pb < 1 → positive; pb > 5 → negative (rough heuristic — sector varies)
  ROE / ROCE:    > 15% → positive; < 8% → negative
  EPS:           not nil → neutral (no directional signal without peer context)
  OPM / NPM:     > 15% → positive; < 5% → negative
  Dividend_Yield: any value → neutral (no universal threshold)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from fetchers import bse_client, nse_client, screener_client
from fetchers.base import waterfall, WaterfallFailure
from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from schemas.messages import UserProfile
from config import yaml_cfg
from util.ist_calendar import now_ist
from services.symbol_service import canonicalize_symbol

logger = logging.getLogger(__name__)


async def get_ratios(
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
    request_id: str = "",
) -> list[Node]:
    """
    Fetch fundamental ratios and return Node list.

    Args:
        symbol:     NSE ticker in uppercase.
        as_of_date: Analysis date (node identity + point-in-time).
        profile:    User profile for weight selection.
        request_id: Trace ID for logging.

    Returns:
        list[Node] with PE, PB, ROE, EPS, OPM, NPM, ROCE, Dividend_Yield nodes.
        Nodes for missing ratios are omitted (never emits a null-value node).
    """
    symbol = canonicalize_symbol(symbol)

    async def _bse() -> dict[str, Any]:
        return await bse_client.fetch_meta_info(symbol)

    async def _screener() -> dict[str, Any]:
        data = await screener_client.fetch_financials(symbol)
        return data.get("ratios") or {}

    try:
        result = await waterfall.run([
            ("bse_library", 1.00, _bse),
            ("screener_in", 0.85, _screener),
        ], request_id=request_id or f"ratios:{symbol}:{as_of_date}")
    except WaterfallFailure as exc:
        logger.warning("Ratios waterfall exhausted for %s: %s", symbol, exc)
        return []

    raw = dict(result.payload)

    bse_snapshot: dict[str, Any] = {}
    try:
        bse_snapshot = await bse_client.fetch_results_snapshot(symbol)
    except Exception as exc:
        logger.debug("BSE results snapshot unavailable for %s: %s", symbol, exc)

    # Augment with BSE market cap (getScripTradingStats.MktCapFull) — more reliable than Screener.
    try:
        stats = await bse_client.fetch_trading_stats(symbol)
        if stats.get("market_cap_cr") is not None:
            raw["market_cap_cr"] = stats["market_cap_cr"]
    except Exception as exc:
        logger.debug("BSE trading stats unavailable for %s: %s", symbol, exc)

    # Augment with NSE/BSE industry classification — overrides any hardcoded sector default.
    try:
        nse_meta = await nse_client.fetch_meta_info(symbol)
        if nse_meta.get("industry"):
            raw["industry"] = nse_meta["industry"]
    except Exception as exc:
        logger.debug("NSE meta info unavailable for %s, trying BSE: %s", symbol, exc)
        try:
            bse_meta = await bse_client.fetch_meta_info(symbol)
            if bse_meta.get("industry"):
                raw["industry"] = bse_meta["industry"]
            if bse_meta.get("sector"):
                raw["sector"] = bse_meta["sector"]
        except Exception as exc2:
            logger.debug("BSE meta info also unavailable for %s: %s", symbol, exc2)

    # Recompute EPS/PB/ROE/PE from Screener quarterly + balance sheet data.
    # OPM/NPM are NOT computed here — BSE exchange data (snapshot then meta) is used
    # exclusively to avoid stale or wrong-period Screener-computed margins.
    try:
        sc_full = await screener_client.fetch_financials(symbol)
        qr = sc_full.get("quarterly_results", {})
        bs = sc_full.get("balance_sheet", {})

        eps_q  = _extract_screener_series(qr, "eps", "earnings per share")
        rev_q  = _extract_screener_series(qr, "sales", "revenue", "net sales")
        op_q   = _extract_screener_series(qr, "operating profit")
        pat_q  = _extract_screener_series(qr, "net profit", "profit after tax")
        eq_bs  = _extract_screener_series(bs, "equity capital", "share capital")
        res_bs = _extract_screener_series(bs, "reserves", "reserves and surplus")

        if len(eps_q) >= 4:
            raw["eps"] = round(sum(eps_q[:4]), 2)

        net_worth = (eq_bs[0] if eq_bs else 0.0) + (res_bs[0] if res_bs else 0.0)
        if net_worth > 0:
            mc_cr = raw.get("market_cap_cr")
            if mc_cr:
                raw["pb"] = round(mc_cr / net_worth, 2)
            if len(pat_q) >= 4:
                pat_ttm = sum(pat_q[:4])
                raw["roe"] = round(pat_ttm / net_worth * 100, 1)

        # PE = live CMP / EPS_TTM (recomputed with corrected EPS)
        eps_ttm = raw.get("eps")
        if eps_ttm and eps_ttm > 0:
            try:
                quote = await nse_client.fetch_quote(symbol)
                cmp = quote.get("close")
                if cmp and cmp > 0:
                    raw["pe"] = round(cmp / eps_ttm, 1)
            except Exception as pe_exc:
                logger.debug("NSE quote for PE computation failed for %s: %s", symbol, pe_exc)

    except Exception as exc:
        logger.debug("Screener ratio override failed for %s: %s", symbol, exc)

    # Override OPM/NPM with BSE results snapshot most-recent period (index 0).
    # BSE periods are newest-first; iterating all periods risks overwriting a
    # newer value with a stale one, so only the first period is used.
    bse_periods = bse_snapshot.get("periods", [])
    if bse_periods and isinstance(bse_periods[0], dict):
        first = bse_periods[0]
        if first.get("opm_pct") is not None:
            raw["opm"] = first["opm_pct"]
        if first.get("npm_pct") is not None:
            raw["npm"] = first["npm_pct"]

    return _build_nodes(raw, symbol, as_of_date,
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
    """Map raw ratio dict → list[Node], skipping missing values."""
    nodes: list[Node] = []
    horizon = profile.horizon.value
    weights = yaml_cfg.weights
    w_ver   = yaml_cfg.versions.get("weight_version", "")

    def _add(name: str, value_str: str, value_raw: dict, signal: NodeSignal,
             weight_key: str, horizon_rel: HorizonRelevance = HorizonRelevance.both) -> None:
        w = _get_weight(weights, "fundamental", weight_key, horizon)
        nodes.append(Node(
            stock=symbol, category=NodeCategory.fundamental, name=name,
            value=value_str, value_raw=value_raw, signal=signal,
            confidence=confidence, source=source_id, source_url="",
            as_of_date=as_of_date, fetched_at_ist=fetched_at,
            horizon_relevance=horizon_rel, weight=w, weight_version=w_ver,
            sanitized=False,
        ))

    # PE_Ratio
    pe = _to_float(raw.get("pe") or raw.get("pe_ratio") or raw.get("ConPE") or raw.get("PE"))
    if pe is not None:
        sector_pe = _to_float(raw.get("sector_pe"))
        if sector_pe and sector_pe > 0:
            sig = (NodeSignal.positive if pe < sector_pe
                   else NodeSignal.negative if pe > 2 * sector_pe
                   else NodeSignal.neutral)
        else:
            sig = NodeSignal.neutral   # no peer context yet
        _add("PE_Ratio", f"PE: {pe:.1f}",
             {"pe": pe, "con_pe": _to_float(raw.get("con_pe")),
              "sector_pe": sector_pe},
             sig, "valuation", HorizonRelevance.long)

    # PB_Ratio
    pb = _to_float(raw.get("pb") or raw.get("pb_ratio") or raw.get("PB"))
    if pb is not None:
        sig = (NodeSignal.positive if pb < 1
               else NodeSignal.negative if pb > 5
               else NodeSignal.neutral)
        _add("PB_Ratio", f"PB: {pb:.2f}",
             {"pb": pb}, sig, "valuation", HorizonRelevance.long)

    # ROE
    roe = _to_float(raw.get("roe") or raw.get("ROE") or raw.get("ConROE"))
    if roe is not None:
        sig = (NodeSignal.positive if roe > 15
               else NodeSignal.negative if roe < 8
               else NodeSignal.neutral)
        _add("ROE", f"ROE: {roe:.1f}%",
             {"roe_pct": roe}, sig, "roe", HorizonRelevance.long)

    # ROCE (Screener provides this; BSE may not)
    roce = _to_float(raw.get("roce") or raw.get("ROCE"))
    if roce is not None:
        sig = (NodeSignal.positive if roce > 15
               else NodeSignal.negative if roce < 8
               else NodeSignal.neutral)
        _add("ROCE", f"ROCE: {roce:.1f}%",
             {"roce_pct": roce}, sig, "roce", HorizonRelevance.long)

    # EPS — comes from bse_client.fetch_meta_info which already applied the
    # consolidated-staleness guard (ConROE/ConPB null check). Just read what it chose.
    eps = _to_float(raw.get("eps"))
    if eps is not None:
        used_con = raw.get("used_consolidated", True)
        _add("EPS", f"EPS: ₹{eps:.2f}",
             {"eps": eps, "basis": "consolidated" if used_con else "standalone"},
             NodeSignal.neutral, "valuation", HorizonRelevance.both)

    # OPM (Operating Profit Margin)
    opm = _to_float(raw.get("opm") or raw.get("OPM"))
    if opm is not None:
        sig = (NodeSignal.positive if opm > 15
               else NodeSignal.negative if opm < 5
               else NodeSignal.neutral)
        _add("OPM", f"OPM: {opm:.1f}%",
             {"opm_pct": opm}, sig, "valuation", HorizonRelevance.long)

    # NPM (Net Profit Margin)
    npm = _to_float(raw.get("npm") or raw.get("NPM"))
    if npm is not None:
        sig = (NodeSignal.positive if npm > 10
               else NodeSignal.negative if npm < 3
               else NodeSignal.neutral)
        _add("NPM", f"NPM: {npm:.1f}%",
             {"npm_pct": npm}, sig, "valuation", HorizonRelevance.long)

    # Dividend Yield
    div_yield = _to_float(raw.get("dividend_yield") or raw.get("DividendYield"))
    if div_yield is not None:
        _add("Dividend_Yield", f"Div Yield: {div_yield:.2f}%",
             {"dividend_yield_pct": div_yield}, NodeSignal.neutral,
             "valuation", HorizonRelevance.long)

    # Market Cap — sourced from BSE getScripTradingStats (MktCapFull) injected in get_ratios
    mc_cr = _to_float(raw.get("market_cap_cr"))
    if mc_cr is not None:
        sig = NodeSignal.neutral
        _add("Market_Cap", f"Mkt Cap: ₹{mc_cr:,.0f} Cr",
             {"market_cap_cr": mc_cr}, sig, "valuation", HorizonRelevance.both)

    return nodes


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _extract_screener_series(table: dict, *label_hints: str) -> list[float]:
    """
    Find a row in a Screener table dict and return its numeric values newest-first.

    Screener stores columns oldest-left → newest-right; this function reverses them.
    Rows with non-numeric cells (e.g. '%' strings) are converted; None on failure.

    Args:
        table:        Screener table dict with "headers" and "rows" keys.
        label_hints:  Lowercase substrings to match against row label.

    Returns:
        List of floats, newest value first. Empty list if row not found.
    """
    if not table:
        return []
    rows = table.get("rows", [])
    for row in rows:
        label = (row.get("label") or "").lower()
        if any(hint in label for hint in label_hints):
            raw_vals = row.get("values", [])
            values: list[float] = []
            for v in raw_vals:
                try:
                    f = float(str(v).replace(",", "").replace("%", "").strip())
                    if f == f:  # exclude NaN
                        values.append(f)
                except (TypeError, ValueError):
                    pass
            return list(reversed(values))
    return []
