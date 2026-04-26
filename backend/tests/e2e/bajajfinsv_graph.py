"""
bajajfinsv_graph.py — Premium 3D knowledge graph for BAJAJFINSV.

Collects live data, builds a rich node/edge graph, renders a self-contained
interactive 3D HTML file using 3d-force-graph + Three.js with:
  - Custom 3D geometries per category (icosahedron, octahedron, torus, etc.)
  - Emissive glow halos around nodes
  - Animated particle flow on agreement/contradiction edges
  - Star-field background
  - Elevated cinematic camera angle
  - Bloom-like glow via multiple render layers

Run:
  conda run -n stocxi python backend/tests/e2e/bajajfinsv_graph.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# ── sys.path ──────────────────────────────────────────────────────────────────
_E2E_DIR     = Path(__file__).resolve().parent
_BACKEND_DIR = _E2E_DIR.parent.parent
_REPO_ROOT   = _BACKEND_DIR.parent
for _p in (_REPO_ROOT, _BACKEND_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

import logging
logging.basicConfig(level=logging.WARNING)

from services.yfinance_service import get_price_and_fundamentals, get_history
from services.screener_service import get_financials
from services.technicals_service import calculate_technicals
from services.news_service import get_news
from fetchers.nse_client import fetch_announcements

_SYMBOL = "BAJAJFINSV"
_PERIODS = ["1w", "1mo", "6mo", "1y"]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data collection
# ═══════════════════════════════════════════════════════════════════════════════

async def _collect():
    print(f"  Collecting live data for {_SYMBOL}...", flush=True)
    pd = await get_price_and_fundamentals(_SYMBOL)
    company_name = pd.get("company_name") or _SYMBOL

    sc_r, tc_r, news_r, ann_r, *hist = await asyncio.gather(
        get_financials(_SYMBOL),
        calculate_technicals(_SYMBOL),
        get_news(_SYMBOL, company_name),
        fetch_announcements(_SYMBOL, limit=8),
        *[get_history(_SYMBOL, p) for p in _PERIODS],
        return_exceptions=True,
    )

    def safe(r, d): return d if isinstance(r, Exception) else r

    screener     = safe(sc_r, {})
    tech         = safe(tc_r, {})
    news         = safe(news_r, [])
    ann_raw      = safe(ann_r, {})
    announcements = ann_raw.get("items", []) if isinstance(ann_raw, dict) else []
    history_map  = {p: r for p, r in zip(_PERIODS, hist) if isinstance(r, dict)}

    print(f"  Done. Price: ₹{pd.get('price')}  Tech signal: {tech.get('overall_signal')}", flush=True)
    return dict(price_data=pd, screener=screener, tech=tech, news=news,
                announcements=announcements, history_map=history_map)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Graph data builder
# ═══════════════════════════════════════════════════════════════════════════════

# Category IDs and colour palette
_CAT = {
    "hub":          {"id": -1, "name": "Company Hub",    "color": "#FFD700"},
    "price":        {"id": 0,  "name": "Price / Market", "color": "#CE93D8"},
    "fundamental":  {"id": 1,  "name": "Fundamentals",   "color": "#81C784"},
    "technical":    {"id": 2,  "name": "Technicals",     "color": "#4FC3F7"},
    "history":      {"id": 3,  "name": "Price History",  "color": "#FFB74D"},
    "news":         {"id": 4,  "name": "News",           "color": "#F48FB1"},
    "verdict":      {"id": 5,  "name": "Verdict",        "color": "#FF7043"},
}
_COMMUNITIES = [{"id": v["id"], "name": v["name"], "color": v["color"]}
                for v in _CAT.values() if v["id"] >= 0]

_SIG_COLOR = {
    "bullish":  "#00e676",
    "positive": "#00e676",
    "bearish":  "#ff5252",
    "negative": "#ff5252",
    "neutral":  None,
    "mixed":    "#ffd740",
    "weak":     "#ffd740",
}
_EDGE_COLOR = {
    "hub_spoke":      "rgba(255,215,0,0.55)",
    "category":       "rgba(255,255,255,0.06)",
    "agreement":      "rgba(0,230,118,0.80)",
    "contradiction":  "rgba(255,82,82,0.80)",
    "verdict_support":"rgba(255,171,64,0.80)",
}


def _node(nid, label, cat_key, signal, value_text, weight=1.0):
    """Create a graph node dict."""
    cat   = _CAT[cat_key]
    color = _SIG_COLOR.get(signal.lower()) or cat["color"]
    return {
        "id":          nid,
        "label":       label,
        "community":   cat["id"],
        "signal":      signal,
        "value_text":  str(value_text)[:140],
        "weight":      round(weight, 3),
        "color":       color,
        "val":         max(3, weight * 5),
        "degree":      0,
        "source_file": f"{cat['name']} · {signal}",
    }


def _edge(src, tgt, etype):
    return {"source": src, "target": tgt, "type": etype,
            "color": _EDGE_COLOR.get(etype, "rgba(255,255,255,0.1)")}


def _pct_sig(pct):
    if pct is None:
        return "neutral"
    return "bullish" if pct > 2 else "bearish" if pct < -2 else "neutral"


def _price_history_pct(hdata):
    if not isinstance(hdata, dict):
        return None
    closes = [c for c in hdata.get("closes", [])
              if isinstance(c, dict) and c.get("close")]
    if len(closes) < 2:
        return None
    s, e = float(closes[0]["close"]), float(closes[-1]["close"])
    return round(((e - s) / abs(s)) * 100, 2) if s else None


def build_graph_data(data: dict) -> dict:
    """Convert collected stock data into graph nodes + edges."""
    pd   = data["price_data"]
    sc   = data["screener"]
    tc   = data["tech"]
    ratios = sc.get("ratios", {}) if isinstance(sc, dict) else {}

    nodes: list[dict] = []
    edges: list[dict] = []

    def n(nid, label, cat_key, signal, value_text, weight=1.0):
        nodes.append(_node(nid, label, cat_key, signal, value_text, weight))
        return nid

    def e(src, tgt, etype="category"):
        edges.append(_edge(src, tgt, etype))

    # ── Company Hub ───────────────────────────────────────────────────────────
    company_name = pd.get("company_name") or _SYMBOL
    sector       = pd.get("sector") or ratios.get("sector", "Financial Services")
    hub = n("hub::BAJAJFINSV", _SYMBOL, "hub",
            "neutral",
            f"{company_name} | {sector} | NSE",
            weight=4.0)

    # ── Price / Market cluster ────────────────────────────────────────────────
    price     = pd.get("price")
    chg_pct   = pd.get("change_percent")
    wk52_high = pd.get("week_52_high")
    wk52_low  = pd.get("week_52_low")
    volume    = pd.get("volume")
    beta      = pd.get("beta")

    chg_sig = _pct_sig(chg_pct)
    # How far below 52W high?
    dist_52h = None
    if price and wk52_high and wk52_high > 0:
        dist_52h = round(((price - wk52_high) / wk52_high) * 100, 2)

    p_price = n("price::current",  f"₹{price}",      "price", chg_sig,
                f"Current Price ₹{price} | 1D: {chg_pct}%", weight=2.5)
    p_range = n("price::52w",      "52W Range",       "price", "neutral",
                f"High ₹{wk52_high} / Low ₹{wk52_low}", weight=1.5)
    p_dist  = n("price::dist52h",  "vs 52W High",     "price",
                "bearish" if dist_52h and dist_52h < -10 else "neutral",
                f"{dist_52h}% below 52-week high" if dist_52h else "N/A",
                weight=1.8)
    p_vol   = n("price::volume",   "Volume",          "price", "neutral",
                f"{volume:,}" if isinstance(volume, (int, float)) else "N/A",
                weight=1.0)
    p_beta  = n("price::beta",     f"Beta {beta}",    "price",
                "bearish" if isinstance(beta, (int, float)) and beta > 1.3 else "neutral",
                f"Beta = {beta} (>1 means higher volatility than index)", weight=1.2)
    p_exch  = n("price::exchange", f"{pd.get('exchange', 'NSE')}",
                "price", "neutral", "Exchange listing", weight=0.8)

    # Hub → price spokes
    for pid in [p_price, p_range, p_dist, p_vol, p_beta, p_exch]:
        e(hub, pid, "hub_spoke")
    for a, b in [(p_price, p_range), (p_range, p_dist), (p_dist, p_vol), (p_vol, p_beta)]:
        e(a, b, "category")

    # ── Fundamentals cluster ──────────────────────────────────────────────────
    pe   = pd.get("pe_ratio")  or ratios.get("pe_ratio")
    pb   = pd.get("pb_ratio")  or ratios.get("pb_ratio")
    roe  = ratios.get("roe")
    roce = ratios.get("roce")
    eps  = pd.get("eps")       or ratios.get("eps")
    mktcap = pd.get("market_cap") or ratios.get("market_cap")
    dy   = pd.get("dividend_yield") or ratios.get("dividend_yield")

    roe_sig  = "bullish" if isinstance(roe, (int,float)) and roe >= 15 else \
               "bearish" if isinstance(roe, (int,float)) and roe < 10 else "neutral"
    roce_sig = "bullish" if isinstance(roce, (int,float)) and roce >= 15 else \
               "bearish" if isinstance(roce, (int,float)) and roce < 10 else "neutral"
    pe_sig   = "neutral" if not isinstance(pe, (int,float)) else \
               "bearish" if pe > 50 else "bullish" if pe < 20 else "neutral"
    dy_sig   = "bullish" if isinstance(dy, (int,float)) and dy >= 2 else "neutral"

    f_pe    = n("fund::pe",   f"P/E {pe}",       "fundamental", pe_sig,
                f"P/E Ratio = {pe} | Sector benchmark ~25–35 for NBFC", weight=2.0)
    f_pb    = n("fund::pb",   f"P/B {pb}",       "fundamental", "neutral",
                f"P/B Ratio = {pb}", weight=1.2)
    f_roe   = n("fund::roe",  f"ROE {roe}%",     "fundamental", roe_sig,
                f"Return on Equity = {roe}% | >15% is healthy", weight=2.2)
    f_roce  = n("fund::roce", f"ROCE {roce}%",   "fundamental", roce_sig,
                f"Return on Capital Employed = {roce}% | >15% is healthy", weight=2.2)
    f_eps   = n("fund::eps",  f"EPS ₹{eps}",     "fundamental", "neutral",
                f"Earnings per Share = ₹{eps}", weight=1.5)
    f_mc    = n("fund::mktcap", "Mkt Cap",        "fundamental", "neutral",
                f"Market Cap ₹{mktcap} Cr", weight=1.0)
    f_dy    = n("fund::dy",   f"Div Yield {dy}%","fundamental", dy_sig,
                f"Dividend Yield = {dy}% | Very low — growth focused", weight=1.0)

    for fid in [f_pe, f_pb, f_roe, f_roce, f_eps, f_mc, f_dy]:
        e(hub, fid, "hub_spoke")
    for a, b in [(f_pe, f_pb), (f_pb, f_roe), (f_roe, f_roce), (f_roce, f_eps),
                 (f_eps, f_mc), (f_mc, f_dy)]:
        e(a, b, "category")

    # ── Technicals cluster ────────────────────────────────────────────────────
    rsi      = tc.get("rsi")
    macd     = tc.get("macd")
    macd_sig_line = tc.get("macd_signal_line")
    adx      = tc.get("adx")
    ema20    = tc.get("ema_20")
    ema50    = tc.get("ema_50")
    ema200   = tc.get("ema_200")
    bb_upper = tc.get("bb_upper")
    bb_lower = tc.get("bb_lower")
    overall  = (tc.get("overall_signal") or "neutral").lower()

    rsi_sig  = "bearish"  if isinstance(rsi, (int,float)) and rsi > 70 else \
               "bullish"  if isinstance(rsi, (int,float)) and rsi < 30 else "neutral"
    macd_sig = "bullish"  if isinstance(macd, (int,float)) and isinstance(macd_sig_line, (int,float)) \
                             and macd > macd_sig_line else \
               "bearish"  if isinstance(macd, (int,float)) else "neutral"

    # Price vs EMA
    ema_sig = "neutral"
    if price and ema20 and ema50 and ema200:
        if price > ema20 and price > ema50 and price > ema200:
            ema_sig = "bullish"
        elif price < ema20 and price < ema50 and price < ema200:
            ema_sig = "bearish"

    adx_val_sig = "neutral" if not isinstance(adx, (int,float)) else \
                  "bullish" if adx > 25 else "weak"

    t_rsi   = n("tech::rsi",    f"RSI(14) {round(rsi,1) if rsi else 'N/A'}",
                "technical", rsi_sig,
                f"RSI(14) = {round(rsi,2) if rsi else 'N/A'} | 30=oversold, 70=overbought",
                weight=2.5)
    t_macd  = n("tech::macd",   "MACD",          "technical", macd_sig,
                f"MACD = {round(macd,2) if macd else 'N/A'} | Signal = {round(macd_sig_line,2) if macd_sig_line else 'N/A'}",
                weight=2.2)
    t_adx   = n("tech::adx",    f"ADX {round(adx,1) if adx else 'N/A'}",
                "technical", adx_val_sig,
                f"ADX(14) = {round(adx,2) if adx else 'N/A'} | <25 = weak trend",
                weight=1.8)
    t_ema20 = n("tech::ema20",  f"EMA 20  ₹{round(ema20,1) if ema20 else 'N/A'}",
                "technical", "bearish" if price and ema20 and price < ema20 else "bullish",
                f"20-day EMA = ₹{round(ema20,2) if ema20 else 'N/A'} | Price is {'below' if price and ema20 and price < ema20 else 'above'}",
                weight=1.8)
    t_ema50 = n("tech::ema50",  f"EMA 50  ₹{round(ema50,1) if ema50 else 'N/A'}",
                "technical", "bearish" if price and ema50 and price < ema50 else "bullish",
                f"50-day EMA = ₹{round(ema50,2) if ema50 else 'N/A'} | Price is {'below' if price and ema50 and price < ema50 else 'above'}",
                weight=1.8)
    t_ema200= n("tech::ema200", f"EMA 200 ₹{round(ema200,1) if ema200 else 'N/A'}",
                "technical", "bearish" if price and ema200 and price < ema200 else "bullish",
                f"200-day EMA = ₹{round(ema200,2) if ema200 else 'N/A'} | Long-term trend level",
                weight=2.0)
    t_bb    = n("tech::bb",     "Bollinger Bands","technical", "neutral",
                f"Upper ₹{round(bb_upper,1) if bb_upper else 'N/A'} / Lower ₹{round(bb_lower,1) if bb_lower else 'N/A'}",
                weight=1.5)
    t_sig   = n("tech::overall", f"Signal: {overall.upper()}",
                "technical", overall,
                f"Composite technical signal: {overall.upper()}",
                weight=3.0)

    for tid in [t_rsi, t_macd, t_adx, t_ema20, t_ema50, t_ema200, t_bb, t_sig]:
        e(hub, tid, "hub_spoke")
    for a, b in [(t_rsi, t_macd), (t_macd, t_adx), (t_adx, t_bb),
                 (t_ema20, t_ema50), (t_ema50, t_ema200), (t_ema200, t_sig),
                 (t_rsi, t_sig), (t_macd, t_sig), (t_bb, t_sig)]:
        e(a, b, "category")

    # ── Price History cluster ─────────────────────────────────────────────────
    period_labels = {"1w": "1 Week", "1mo": "1 Month", "6mo": "6 Months", "1y": "1 Year"}
    hist_nodes = {}
    for period in _PERIODS:
        pct = _price_history_pct(data["history_map"].get(period))
        sig = _pct_sig(pct)
        label = f"{period_labels[period]}: {f'{pct:+.2f}%' if pct else 'N/A'}"
        hid = n(f"hist::{period}", label, "history", sig,
                f"Price change over {period_labels[period]}: {pct}%",
                weight=1.5 if period in ("6mo", "1y") else 1.2)
        hist_nodes[period] = hid
        e(hub, hid, "hub_spoke")

    for a, b in [("1w", "1mo"), ("1mo", "6mo"), ("6mo", "1y")]:
        if a in hist_nodes and b in hist_nodes:
            e(hist_nodes[a], hist_nodes[b], "category")

    # ── News cluster ──────────────────────────────────────────────────────────
    neg_kw = {"underperform", "fall", "decline", "bearish", "weak", "down", "loss",
               "sell", "probe", "penalty", "miss"}
    pos_kw = {"surge", "gain", "rally", "beat", "buy", "bullish", "up", "strong",
               "order", "growth", "record"}
    news_nodes = []
    for i, item in enumerate(data["news"][:7]):
        if not isinstance(item, dict) or not item.get("title"):
            continue
        title = item["title"][:60]
        src   = item.get("source", "")
        words = set(title.lower().split())
        neg_hits = len(words & neg_kw)
        pos_hits = len(words & pos_kw)
        sig = "bearish" if neg_hits > pos_hits else \
              "bullish" if pos_hits > neg_hits else "neutral"
        nid_news = n(f"news::{i}", title, "news", sig,
                     f"{item['title']} — {src}", weight=1.5 if i < 3 else 1.0)
        news_nodes.append(nid_news)
        e(hub, nid_news, "hub_spoke")
    for i in range(len(news_nodes) - 1):
        e(news_nodes[i], news_nodes[i+1], "category")

    # ── Announcement cluster ──────────────────────────────────────────────────
    ann_nodes = []
    for i, item in enumerate(data["announcements"][:4]):
        if not isinstance(item, dict):
            continue
        subject = (item.get("title") or item.get("subject") or "")[:55]
        if not subject:
            continue
        cat_label = item.get("category", "")
        date_str  = item.get("date", "")
        nid_ann = n(f"ann::{i}", subject[:30], "news", "neutral",
                    f"{subject} | {cat_label} | {date_str}", weight=1.2)
        ann_nodes.append(nid_ann)
        e(hub, nid_ann, "hub_spoke")
    for i in range(len(ann_nodes) - 1):
        e(ann_nodes[i], ann_nodes[i+1], "category")

    # ── Verdict nodes ─────────────────────────────────────────────────────────
    # Derive each verdict from signals
    fund_signals = [nodes[i]["signal"] for i in range(len(nodes))
                    if nodes[i]["community"] == _CAT["fundamental"]["id"]]
    tech_signals = [nodes[i]["signal"] for i in range(len(nodes))
                    if nodes[i]["community"] == _CAT["technical"]["id"]]
    news_signals = [nodes[i]["signal"] for i in range(len(nodes))
                    if nodes[i]["community"] == _CAT["news"]["id"]]

    def _majority(sigs):
        bulls = sigs.count("bullish") + sigs.count("positive")
        bears = sigs.count("bearish") + sigs.count("negative")
        if bears > bulls + 1:
            return "bearish"
        if bulls > bears + 1:
            return "bullish"
        return "neutral"

    v_fund = _majority(fund_signals)
    v_tech = _majority(tech_signals)
    v_news = _majority(news_signals)

    score = ({"bullish":1,"neutral":0,"bearish":-1}.get(v_fund,0) +
             {"bullish":1,"neutral":0,"bearish":-1}.get(v_tech,0)*1.2 +
             {"bullish":1,"neutral":0,"bearish":-1}.get(v_news,0)*0.5)
    v_final = "bullish" if score > 0.8 else "bearish" if score < -0.5 else "neutral"
    v_label = {"bullish": "BULLISH", "bearish": "BEARISH", "neutral": "HOLD / NEUTRAL"}[v_final]

    vf = n("verdict::fundamentals", f"Fundamentals: {v_fund.upper()}",
           "verdict", v_fund, f"Derived from {len(fund_signals)} fundamental nodes", weight=2.5)
    vt = n("verdict::technicals",   f"Technicals: {v_tech.upper()}",
           "verdict", v_tech, f"Derived from {len(tech_signals)} technical nodes", weight=2.5)
    vn = n("verdict::news",         f"News: {v_news.upper()}",
           "verdict", v_news, f"Derived from {len(news_signals)} news nodes", weight=2.0)
    vfinal = n("verdict::final",    f"FINAL: {v_label}",
               "verdict", v_final, f"Composite verdict from all data sources", weight=4.5)

    e(hub, vf, "hub_spoke")
    e(hub, vt, "hub_spoke")
    e(hub, vn, "hub_spoke")
    e(vf, vfinal, "verdict_support")
    e(vt, vfinal, "verdict_support")
    e(vn, vfinal, "verdict_support")

    # ── Cross-category agreement / contradiction edges ────────────────────────
    # Technical MACD bullish + RSI neutral → mild agreement
    if macd_sig == "bullish":
        e(t_macd, vt, "verdict_support")
    # EMA bearish × 3 → verdict
    for eid in [t_ema20, t_ema50, t_ema200]:
        e(eid, vt, "agreement" if ema_sig == "bearish" else "verdict_support")
    # ADX weak → contradiction with MACD bullish
    if adx_val_sig == "weak" and macd_sig == "bullish":
        e(t_adx, t_macd, "contradiction")
    # ROE/ROCE bearish → fund verdict agreement
    if roe_sig == "bearish":
        e(f_roe, vf, "agreement")
    if roce_sig == "bearish":
        e(f_roce, vf, "agreement")
    # Price below 52W high → bearish momentum
    if dist_52h and dist_52h < -15:
        e(p_dist, t_sig, "agreement")
        e(p_dist, vfinal, "agreement")
    # Historical bearish → verdict
    for period in ["6mo", "1y"]:
        pct = _price_history_pct(data["history_map"].get(period))
        if pct and pct < -10:
            e(hist_nodes[period], vfinal, "agreement")
    # News bearish nodes → news verdict
    for nid in news_nodes:
        node_obj = next((nd for nd in nodes if nd["id"] == nid), None)
        if node_obj and node_obj["signal"] == "bearish":
            e(nid, vn, "agreement")
    # Contradiction: MACD slight bullish vs EMA bearish
    if macd_sig == "bullish" and ema_sig == "bearish":
        e(t_macd, t_ema50, "contradiction")
        e(t_macd, t_ema200, "contradiction")
    # Fundamentals neutral vs news bearish → contradiction
    if v_fund == "neutral" and v_news == "bearish":
        e(vf, vn, "contradiction")

    # ── Update degree counts ──────────────────────────────────────────────────
    degree: dict[str, int] = {nd["id"]: 0 for nd in nodes}
    for lnk in edges:
        degree[lnk["source"]] = degree.get(lnk["source"], 0) + 1
        degree[lnk["target"]] = degree.get(lnk["target"], 0) + 1
    for nd in nodes:
        nd["degree"] = degree.get(nd["id"], 0)

    return {
        "nodes":       nodes,
        "links":       edges,
        "communities": _COMMUNITIES,
        "meta": {
            "symbol":      _SYMBOL,
            "company":     company_name,
            "price":       price,
            "change_pct":  chg_pct,
            "final_verdict": v_label,
            "node_count":  len(nodes),
            "edge_count":  len(edges),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Premium HTML renderer
# ═══════════════════════════════════════════════════════════════════════════════

_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#080c12; overflow:hidden; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
#graph { position:fixed; inset:0; }

/* ── Header strip ── */
#header {
  position:fixed; top:0; left:0; right:0; z-index:200;
  height:52px;
  background:linear-gradient(90deg,rgba(8,12,18,0.98) 0%,rgba(15,20,30,0.95) 100%);
  border-bottom:1px solid rgba(255,215,0,0.18);
  display:flex; align-items:center; gap:16px; padding:0 20px;
  backdrop-filter:blur(20px);
}
#header-logo {
  font-size:18px; font-weight:800; letter-spacing:2px;
  background:linear-gradient(90deg,#FFD700,#FFA500); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
}
#header-sub { color:#8b949e; font-size:12px; }
#header-verdict {
  margin-left:auto; padding:4px 14px; border-radius:6px; font-size:12px;
  font-weight:700; letter-spacing:1px; border:1px solid currentColor;
}
#header-price { font-size:13px; color:#e6edf3; font-weight:600; }

/* ── Side panel ── */
#panel {
  position:fixed; top:64px; right:14px; z-index:100;
  width:270px;
  background:rgba(8,12,18,0.94);
  border:1px solid rgba(48,54,61,0.8);
  border-radius:14px; padding:14px;
  backdrop-filter:blur(24px);
  box-shadow:0 8px 48px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,215,0,0.05);
}
#search {
  width:100%; background:rgba(255,255,255,0.04); border:1.5px solid rgba(48,54,61,0.9);
  border-radius:8px; color:#e6edf3; padding:7px 12px;
  font-size:12px; outline:none; margin-bottom:10px; transition:all .2s;
}
#search:focus { border-color:#FFD700; box-shadow:0 0 0 3px rgba(255,215,0,0.1); }
#node-info {
  font-size:11.5px; color:#8b949e; min-height:56px; margin-bottom:10px;
  padding:9px 10px; background:rgba(255,255,255,0.025);
  border-radius:8px; border:1px solid rgba(48,54,61,0.5); line-height:1.55;
}
#node-info strong { color:#e6edf3; display:block; margin-bottom:3px; font-size:12.5px; }
#controls { display:flex; gap:5px; flex-wrap:wrap; margin-bottom:10px; }
button {
  background:rgba(255,255,255,0.04); border:1px solid rgba(48,54,61,0.9);
  color:#c9d1d9; padding:4px 10px; border-radius:6px; font-size:11px;
  cursor:pointer; transition:all .15s; font-weight:500; letter-spacing:.3px;
}
button:hover { background:rgba(255,255,255,0.08); border-color:rgba(72,79,88,0.9); }
button.active { background:rgba(255,215,0,0.12); border-color:rgba(255,215,0,0.5); color:#FFD700; }

#legend { max-height:200px; overflow-y:auto; }
#legend::-webkit-scrollbar { width:3px; }
#legend::-webkit-scrollbar-thumb { background:#21262d; border-radius:2px; }
.legend-item {
  display:flex; align-items:center; gap:8px; padding:6px 6px;
  font-size:11.5px; cursor:pointer; border-radius:6px; transition:all .2s;
}
.legend-item:hover { background:rgba(255,255,255,0.05); transform:translateX(2px); }
.ldot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.lcount { margin-left:auto; color:#484f58; font-size:10.5px; }

#edge-legend { margin-top:8px; padding-top:8px; border-top:1px solid rgba(48,54,61,0.4); }
.edge-row { display:flex; align-items:center; gap:7px; font-size:11px; color:#8b949e; padding:2px 0; }
.eline { width:22px; height:2px; border-radius:2px; }
#stats {
  font-size:10.5px; color:#484f58; margin-top:8px; padding-top:8px;
  border-top:1px solid rgba(48,54,61,0.4);
}
</style>
</head>
<body>
<div id="graph"></div>

<div id="header">
  <div id="header-logo">STOCXI</div>
  <div id="header-sub">Knowledge Graph</div>
  <div id="header-price" id="hp"></div>
  <div id="header-verdict" id="hv"></div>
</div>

<div id="panel">
  <input id="search" placeholder="🔍  Search nodes..." type="text">
  <div id="node-info">Hover or click a node to inspect</div>
  <div id="controls">
    <button id="btn-rotate" class="active" onclick="toggleRotate()">▶ Orbit</button>
    <button onclick="resetCamera()">⌂ Reset</button>
    <button id="btn-labels" onclick="toggleLabels()">Aa Labels</button>
    <button id="btn-layout" onclick="cycleLayout()">⬡ Layout</button>
  </div>
  <div id="legend"></div>
  <div id="edge-legend">
    <div class="edge-row"><div class="eline" style="background:#00e676;box-shadow:0 0 6px #00e676"></div>Agreement</div>
    <div class="edge-row"><div class="eline" style="background:#ff5252;box-shadow:0 0 6px #ff5252"></div>Contradiction</div>
    <div class="edge-row"><div class="eline" style="background:#ffab40;box-shadow:0 0 6px #ffab40"></div>Verdict support</div>
    <div class="edge-row"><div class="eline" style="background:rgba(255,215,0,0.6)"></div>Hub spoke</div>
  </div>
  <div id="stats"></div>
</div>

<script src="https://unpkg.com/three@0.158.0/build/three.min.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.73.2/dist/3d-force-graph.min.js"></script>
<script>
const GD = __GRAPH_DATA__;

// ── Header wiring ─────────────────────────────────────────────────────────────
document.getElementById('hp').textContent = `${GD.meta.symbol}  ₹${GD.meta.price}  (${GD.meta.change_pct > 0 ? '+' : ''}${GD.meta.change_pct}%)`;
const hv = document.getElementById('hv');
hv.textContent = GD.meta.final_verdict;
const verdictColors = {
  'BULLISH': ['#00e676','rgba(0,230,118,0.15)'],
  'BEARISH': ['#ff5252','rgba(255,82,82,0.15)'],
  'HOLD / NEUTRAL': ['#ffd740','rgba(255,215,64,0.15)'],
};
const [vc, vbg] = verdictColors[GD.meta.final_verdict] || ['#8b949e','rgba(139,148,158,0.1)'];
hv.style.color = vc; hv.style.background = vbg; hv.style.borderColor = vc;

// ── State ─────────────────────────────────────────────────────────────────────
let rotating  = true;
let showLabels= false;
let layoutIdx = 0;
const LAYOUTS  = ['Force 3D','Sphere','Clusters'];
const hlNodes  = new Set();
const hlLinks  = new Set();

// ── Geometry factory ──────────────────────────────────────────────────────────
function makeNodeObject(node) {
  const baseR = Math.sqrt(node.val) * 1.8;
  let geo;
  switch (node.community) {
    case -1: geo = new THREE.SphereGeometry(baseR * 1.6, 32, 32); break;   // hub
    case  0: geo = new THREE.TorusGeometry(baseR, baseR*0.38, 12, 32); break; // price
    case  1: geo = new THREE.BoxGeometry(baseR*1.7, baseR*1.7, baseR*1.7); break; // fundamentals
    case  2: geo = new THREE.OctahedronGeometry(baseR * 1.3, 1); break;    // technical
    case  3: geo = new THREE.ConeGeometry(baseR, baseR*1.8, 8); break;     // history
    case  4: geo = new THREE.SphereGeometry(baseR, 12, 12); break;          // news
    case  5: geo = new THREE.IcosahedronGeometry(baseR * 1.5, 0); break;   // verdict
    default: geo = new THREE.SphereGeometry(baseR, 16, 16);
  }

  const isHighlighted = hlNodes.size === 0 || hlNodes.has(node.id);
  const opacity = isHighlighted ? 0.92 : 0.12;
  const emissive = new THREE.Color(node.color);

  const mat = new THREE.MeshPhongMaterial({
    color:     new THREE.Color(node.color),
    emissive,
    emissiveIntensity: node.community === -1 ? 0.6 : 0.35,
    transparent: true,
    opacity,
    shininess: 140,
  });
  const mesh = new THREE.Mesh(geo, mat);

  // Glow halo
  const glowGeo = new THREE.SphereGeometry(baseR * 2.6, 12, 12);
  const glowMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color(node.color),
    transparent: true,
    opacity: isHighlighted ? (node.community === -1 ? 0.12 : 0.06) : 0.01,
    side: THREE.BackSide,
  });
  mesh.add(new THREE.Mesh(glowGeo, glowMat));

  // Hub gets extra outer ring
  if (node.community === -1) {
    const ringGeo = new THREE.TorusGeometry(baseR * 2.8, 0.5, 8, 48);
    const ringMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#FFD700'), transparent: true, opacity: 0.35,
    });
    mesh.add(new THREE.Mesh(ringGeo, ringMat));
    const ring2Geo = new THREE.TorusGeometry(baseR * 4.2, 0.25, 8, 64);
    const ring2Mat = new THREE.MeshBasicMaterial({
      color: new THREE.Color('#FFD700'), transparent: true, opacity: 0.12,
    });
    const ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
    ring2.rotation.x = Math.PI / 3;
    mesh.add(ring2);
  }

  return mesh;
}

// ── Link helpers ──────────────────────────────────────────────────────────────
function lColor(l) {
  if (hlLinks.size && !hlLinks.has(l)) return 'rgba(255,255,255,0.015)';
  return l.color || 'rgba(255,255,255,0.07)';
}
function lWidth(l) {
  if (hlLinks.size && !hlLinks.has(l)) return 0.1;
  if (l.type === 'category')   return 0.4;
  if (l.type === 'hub_spoke')  return 1.2;
  if (l.type === 'agreement')  return 2.2;
  if (l.type === 'contradiction') return 2.2;
  if (l.type === 'verdict_support') return 2.0;
  return 0.8;
}

// ── Build graph ───────────────────────────────────────────────────────────────
const Graph = ForceGraph3D()(document.getElementById('graph'))
  .graphData(GD)
  .nodeId('id')
  .nodeLabel(nd => `
    <div style="background:rgba(6,10,16,0.96);border:1.5px solid ${nd.color}40;
         border-radius:10px;padding:10px 14px;font-size:12px;color:#e6edf3;
         max-width:280px;box-shadow:0 4px 24px rgba(0,0,0,0.5)">
      <strong style="color:${nd.color};font-size:13px">${nd.label}</strong><br>
      <span style="color:#58a6ff;font-size:11px">${nd.source_file}</span><br>
      <span style="color:#8b949e;font-size:11px;line-height:1.4">${nd.value_text}</span>
    </div>`)
  .nodeThreeObjectExtend(false)
  .nodeThreeObject(makeNodeObject)
  .linkSource('source')
  .linkTarget('target')
  .linkColor(lColor)
  .linkWidth(lWidth)
  .linkOpacity(0.9)
  .linkCurvature(l => l.type === 'contradiction' ? 0.25 : l.type === 'agreement' ? 0.15 : 0.05)
  .linkDirectionalParticles(l => ['agreement','contradiction','verdict_support'].includes(l.type) ? 3 : 0)
  .linkDirectionalParticleSpeed(0.005)
  .linkDirectionalParticleWidth(l => l.type === 'contradiction' ? 2.5 : 2.0)
  .linkDirectionalParticleColor(l => l.color || '#fff')
  .backgroundColor('#080c12')
  .onNodeHover(node => {
    hlNodes.clear(); hlLinks.clear();
    if (node) {
      hlNodes.add(node.id);
      GD.links.forEach(l => {
        const s = typeof l.source==='object'?l.source.id:l.source;
        const t = typeof l.target==='object'?l.target.id:l.target;
        if (s===node.id||t===node.id) { hlLinks.add(l); hlNodes.add(s); hlNodes.add(t); }
      });
    }
    Graph.nodeThreeObject(makeNodeObject).linkColor(lColor).linkWidth(lWidth);
  })
  .onNodeClick(node => {
    if (!node) return;
    const cat = GD.communities.find(c => c.id === node.community);
    document.getElementById('node-info').innerHTML = `
      <strong style="color:${node.color}">${node.label}</strong>
      <span style="color:#58a6ff;font-size:11px">${node.source_file}</span><br>
      <span style="color:#8b949e;font-size:11px">${node.value_text}</span><br>
      <span style="color:#484f58;font-size:10.5px">Weight: ${node.weight} · ${hlNodes.size-1} connections</span>`;
    const dist=180, r=dist/Math.hypot(node.x||1,node.y||1,node.z||1)+1;
    Graph.cameraPosition({x:node.x*r,y:node.y*r,z:node.z*r}, node, 800);
  })
  .onBackgroundClick(() => {
    hlNodes.clear(); hlLinks.clear();
    Graph.nodeThreeObject(makeNodeObject).linkColor(lColor).linkWidth(lWidth);
    document.getElementById('node-info').textContent = 'Hover or click a node to inspect';
  });

// ── Lights & stars ────────────────────────────────────────────────────────────
Graph.onEngineStop(() => {
  const scene = Graph.scene();

  // Lights
  const ambient = new THREE.AmbientLight(0x111827, 2.5);
  scene.add(ambient);
  const point1 = new THREE.PointLight(0xFFD700, 1.8, 800);
  point1.position.set(200, 200, 200);
  scene.add(point1);
  const point2 = new THREE.PointLight(0x4FC3F7, 1.2, 600);
  point2.position.set(-200, -100, 150);
  scene.add(point2);
  const point3 = new THREE.PointLight(0xff5252, 0.8, 500);
  point3.position.set(0, -300, -100);
  scene.add(point3);

  // Star field
  const starCount = 2000;
  const starGeo = new THREE.BufferGeometry();
  const starPos = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount * 3; i++) {
    starPos[i] = (Math.random() - 0.5) * 4000;
  }
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
  const starMat = new THREE.PointsMaterial({
    color: 0xffffff, size: 0.9, transparent: true, opacity: 0.45,
    sizeAttenuation: true,
  });
  scene.add(new THREE.Points(starGeo, starMat));

  // Fog
  scene.fog = new THREE.FogExp2(0x080c12, 0.0012);

  // Auto-rotate
  const ctrl = Graph.controls();
  if (ctrl) { ctrl.autoRotate = rotating; ctrl.autoRotateSpeed = 0.6; }
});

// ── Legend ────────────────────────────────────────────────────────────────────
const legEl = document.getElementById('legend');
const nc = {};
GD.nodes.forEach(n => { nc[n.community] = (nc[n.community]||0)+1; });
GD.communities.forEach(c => {
  if (!nc[c.id]) return;
  const d = document.createElement('div');
  d.className = 'legend-item';
  d.innerHTML = `<div class="ldot" style="background:${c.color};box-shadow:0 0 5px ${c.color}88"></div>
    <span>${c.name}</span><span class="lcount">${nc[c.id]}</span>`;
  d.onclick = () => filterCat(c.id, c);
  legEl.appendChild(d);
});

document.getElementById('stats').innerHTML =
  `${GD.meta.node_count} nodes &nbsp;·&nbsp; ${GD.meta.edge_count} edges &nbsp;·&nbsp; ${GD.meta.symbol}`;

// ── Controls ──────────────────────────────────────────────────────────────────
function toggleRotate() {
  rotating = !rotating;
  document.getElementById('btn-rotate').classList.toggle('active', rotating);
  const c = Graph.controls(); if (c) c.autoRotate = rotating;
}
function resetCamera() {
  Graph.cameraPosition({x:0,y:60,z:560},{x:0,y:0,z:0},900);
  hlNodes.clear(); hlLinks.clear();
  Graph.nodeThreeObject(makeNodeObject).linkColor(lColor).linkWidth(lWidth);
  document.getElementById('node-info').textContent = 'Hover or click a node to inspect';
}
function toggleLabels() {
  showLabels = !showLabels;
  document.getElementById('btn-labels').classList.toggle('active', showLabels);
  if (showLabels) {
    Graph.nodeThreeObjectExtend(true).nodeThreeObject(node => {
      const base = makeNodeObject(node);
      const c = document.createElement('canvas'); c.width=512; c.height=64;
      const ctx = c.getContext('2d');
      ctx.fillStyle='rgba(8,12,18,0.9)';
      ctx.beginPath(); ctx.roundRect(4,6,504,52,8); ctx.fill();
      ctx.strokeStyle=node.color; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.roundRect(4,6,504,52,8); ctx.stroke();
      const txt = node.label.length>26?node.label.slice(0,24)+'…':node.label;
      ctx.font='bold 24px Inter,sans-serif'; ctx.textAlign='center';
      ctx.textBaseline='middle'; ctx.fillStyle=node.color;
      ctx.fillText(txt,256,32);
      const spr = new THREE.Sprite(new THREE.SpriteMaterial(
        {map:new THREE.CanvasTexture(c),depthWrite:false,transparent:true}));
      spr.scale.set(44,8,1); spr.position.set(0,10,0);
      base.add(spr); return base;
    });
  } else {
    Graph.nodeThreeObjectExtend(false).nodeThreeObject(makeNodeObject);
  }
}
function cycleLayout() {
  layoutIdx = (layoutIdx+1)%LAYOUTS.length;
  document.getElementById('btn-layout').textContent = '⬡ '+LAYOUTS[layoutIdx];
  const N = GD.nodes.length;
  if (layoutIdx===1) {
    GD.nodes.forEach((n,i) => {
      const phi=Math.acos(-1+(2*i)/N), th=Math.sqrt(N*Math.PI)*phi, R=280;
      n.fx=R*Math.cos(th)*Math.sin(phi); n.fy=R*Math.sin(th)*Math.sin(phi); n.fz=R*Math.cos(phi);
    });
  } else if (layoutIdx===2) {
    const comms={};
    GD.nodes.forEach(n=>{ (comms[n.community]=comms[n.community]||[]).push(n); });
    Object.keys(comms).forEach((cid,ci,keys)=>{
      const th=(ci/keys.length)*2*Math.PI, R=300;
      comms[cid].forEach((n,ni)=>{
        const r=70,a=(ni/comms[cid].length)*2*Math.PI;
        n.fx=R*Math.cos(th)+r*Math.cos(a); n.fy=R*Math.sin(th)+r*Math.sin(a); n.fz=(Math.random()-.5)*100;
      });
    });
  } else {
    GD.nodes.forEach(n=>{ delete n.fx; delete n.fy; delete n.fz; });
    Graph.cameraPosition({x:0,y:60,z:560},{x:0,y:0,z:0},900);
  }
  Graph.graphData(GD);
}
function filterCat(cid, comm) {
  hlNodes.clear(); hlLinks.clear();
  GD.nodes.forEach(n=>{ if(n.community===cid) hlNodes.add(n.id); });
  GD.links.forEach(l=>{
    const s=typeof l.source==='object'?l.source.id:l.source;
    const t=typeof l.target==='object'?l.target.id:l.target;
    if(hlNodes.has(s)&&hlNodes.has(t)) hlLinks.add(l);
  });
  Graph.nodeThreeObject(makeNodeObject).linkColor(lColor).linkWidth(lWidth);
  document.getElementById('node-info').innerHTML=
    `<strong style="color:${comm.color}">${comm.name}</strong><br>
     <span style="color:#8b949e">${hlNodes.size} nodes highlighted</span>`;
}

// ── Search ────────────────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', e => {
  const q=e.target.value.toLowerCase().trim();
  hlNodes.clear(); hlLinks.clear();
  if (q) {
    const matched=GD.nodes.filter(n=>
      n.label.toLowerCase().includes(q)||n.value_text.toLowerCase().includes(q));
    matched.forEach(n=>hlNodes.add(n.id));
    GD.links.forEach(l=>{
      const s=typeof l.source==='object'?l.source.id:l.source;
      const t=typeof l.target==='object'?l.target.id:l.target;
      if(hlNodes.has(s)||hlNodes.has(t)){ hlLinks.add(l); hlNodes.add(s); hlNodes.add(t); }
    });
  }
  Graph.nodeThreeObject(makeNodeObject).linkColor(lColor).linkWidth(lWidth);
});

// ── Initial camera position (cinematic angle) ─────────────────────────────────
setTimeout(() => {
  Graph.cameraPosition({x:80,y:180,z:520},{x:0,y:0,z:0},0);
  const c = Graph.controls();
  if (c) { c.autoRotate=rotating; c.autoRotateSpeed=0.6; }
}, 400);
</script>
</body>
</html>"""


def render_html(graph_data: dict, title: str) -> str:
    data_json = json.dumps(graph_data, ensure_ascii=False)
    return _HTML.replace("__GRAPH_DATA__", data_json).replace("__TITLE__", title)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Entry point
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    print(f"\n{'═'*56}", flush=True)
    print(f"  BAJAJFINSV  —  3D Knowledge Graph Generator", flush=True)
    print(f"{'═'*56}\n", flush=True)

    data       = await _collect()
    graph_data = build_graph_data(data)

    title      = f"BAJAJFINSV · Knowledge Graph · {graph_data['meta']['node_count']} nodes"
    html       = render_html(graph_data, title)

    out_dir = _E2E_DIR / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "BAJAJFINSV_knowledge_graph.html"
    out_path.write_text(html, encoding="utf-8")

    n_count = graph_data["meta"]["node_count"]
    e_count = graph_data["meta"]["edge_count"]
    print(f"\n  Nodes: {n_count}  |  Edges: {e_count}", flush=True)
    print(f"  Final verdict: {graph_data['meta']['final_verdict']}", flush=True)
    print(f"\n  ✅  Saved → {out_path}", flush=True)

    # Open in default browser
    try:
        subprocess.run(["open", str(out_path)], check=False)
        print("  Browser opened.", flush=True)
    except Exception:
        print(f"  Open manually: file://{out_path}", flush=True)

    print(f"\n{'═'*56}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
