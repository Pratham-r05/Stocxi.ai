"""
test_indianapi.py — Stress test IndianAPI against all 10 companies.
Tests every endpoint, measures accuracy + timing.
"""

import time
import requests
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; BOLD = "\033[1m"; X = "\033[0m"

API_KEY  = "sk-live-QFMn5WMgzBdmMKJtXlqeiykXrRgWmElNaH3YpAwz"
BASE_URL = "https://analyst.indianapi.in"
HEADERS  = {"X-API-Key": API_KEY}
TIMEOUT  = 15

COMPANIES = [
    {"name": "Trent",                     "symbol": "TRENT"},
    {"name": "ONGC",                      "symbol": "ONGC"},
    {"name": "Gujarat Natural Resources", "symbol": "GNRL"},
    {"name": "Yaap Digital",              "symbol": "Yaap Digital"},
    {"name": "Ashoka Buildcon",           "symbol": "ASHOKA"},
    {"name": "Transformers & Rectifiers", "symbol": "TRIL"},
    {"name": "SDC Techmedia",            "symbol": "SDC Techmedia"},
    {"name": "Sun Pharmaceutical",        "symbol": "SUNPHARMA"},
    {"name": "Polycab",                   "symbol": "POLYCAB"},
    {"name": "KJMC Financial Services",   "symbol": "KJMC Financial Services"},
]

@dataclass
class Result:
    company:      str
    symbol:       str
    # stock endpoint fields
    price:        Optional[bool] = None;  price_val:    str = "—"
    pe:           Optional[bool] = None;  pe_val:       str = "—"
    pb:           Optional[bool] = None;  pb_val:       str = "—"
    eps:          Optional[bool] = None;  eps_val:      str = "—"
    market_cap:   Optional[bool] = None;  mc_val:       str = "—"
    roe:          Optional[bool] = None;  roe_val:      str = "—"
    roce:         Optional[bool] = None;  roce_val:     str = "—"
    div_yield:    Optional[bool] = None;  dy_val:       str = "—"
    shareholding: Optional[bool] = None
    corp_actions: Optional[bool] = None
    news:         Optional[bool] = None
    # historical endpoint
    ohlcv:        Optional[bool] = None;  ohlcv_rows:   int = 0
    # historical_stats endpoint
    financials:   Optional[bool] = None
    # timing
    stock_t:      float = 0
    hist_t:       float = 0
    stats_t:      float = 0
    total_t:      float = 0
    error:        str = ""


def get(endpoint: str, params: dict) -> tuple[any, float]:
    t0 = time.time()
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params, timeout=TIMEOUT)
        elapsed = time.time() - t0
        if r.status_code == 200:
            try:    return r.json(), elapsed
            except: return None, elapsed
        return None, elapsed
    except Exception as e:
        return None, time.time() - t0


def test_company(c: dict) -> Result:
    res = Result(company=c["name"], symbol=c["symbol"])
    t_total = time.time()

    # ── 1. /stock ─────────────────────────────────────────────────────────────
    data, t = get("/stock", {"name": c["symbol"]})
    res.stock_t = t

    if data and isinstance(data, dict):
        # Price
        price = (data.get("current_price") or {}).get("BSE") or (data.get("current_price") or {}).get("NSE")
        if not price:
            price = data.get("price") or data.get("ltp") or data.get("last_price")
        res.price = price not in (None, "", 0, "0")
        res.price_val = str(price)[:10] if price else "—"

        # Key metrics — could be nested differently
        metrics = data.get("key_metrics") or data.get("financials") or data.get("ratios") or data

        def extract(keys):
            for k in keys:
                v = data.get(k) or metrics.get(k) if isinstance(metrics, dict) else None
                if v not in (None, "", "—", "N/A", 0, "0"):
                    return v
            return None

        pe  = extract(["pe_ratio","pe","p_e","PE","price_to_earnings"])
        pb  = extract(["pb_ratio","pb","p_b","PB","price_to_book"])
        eps = extract(["eps","EPS","earnings_per_share"])
        mc  = extract(["market_cap","marketcap","market_capitalization","mktcap"])
        roe = extract(["roe","ROE","return_on_equity"])
        roce= extract(["roce","ROCE","return_on_capital_employed"])
        dy  = extract(["dividend_yield","div_yield","dividendYield"])

        res.pe        = pe   is not None; res.pe_val   = str(pe)[:8]   if pe   else "—"
        res.pb        = pb   is not None; res.pb_val   = str(pb)[:8]   if pb   else "—"
        res.eps       = eps  is not None; res.eps_val  = str(eps)[:8]  if eps  else "—"
        res.market_cap= mc   is not None; res.mc_val   = str(mc)[:10]  if mc   else "—"
        res.roe       = roe  is not None; res.roe_val  = str(roe)[:8]  if roe  else "—"
        res.roce      = roce is not None; res.roce_val = str(roce)[:8] if roce else "—"
        res.div_yield = dy   is not None; res.dy_val   = str(dy)[:8]   if dy   else "—"

        # Shareholding
        shp = data.get("shareholding") or data.get("shareholding_pattern") or data.get("share_holding")
        res.shareholding = bool(shp)

        # Corporate Actions
        ca = data.get("corporate_actions") or data.get("events") or data.get("dividends")
        res.corp_actions = bool(ca)

        # News
        news = data.get("news") or data.get("recent_news")
        res.news = bool(news)
    else:
        res.error = "stock endpoint failed"

    # ── 2. /historical_data ───────────────────────────────────────────────────
    hist, t = get("/historical_data", {"stock_name": c["symbol"], "period": "1yr"})
    res.hist_t = t
    if hist and isinstance(hist, (dict, list)):
        if isinstance(hist, list):
            res.ohlcv = len(hist) > 0; res.ohlcv_rows = len(hist)
        else:
            rows = hist.get("data") or hist.get("prices") or hist.get("historical") or []
            res.ohlcv = len(rows) > 0; res.ohlcv_rows = len(rows)
    else:
        res.ohlcv = False

    # ── 3. /historical_stats ──────────────────────────────────────────────────
    stats, t = get("/historical_stats", {"stock_name": c["symbol"], "stats": "income"})
    res.stats_t = t
    res.financials = bool(stats and stats not in ({}, []))

    res.total_t = time.time() - t_total
    return res


def tick(v): return f"{G}✓{X}" if v else f"{R}✗{X}"

def print_results(results: list[Result]):
    print(f"\n{BOLD}{'═'*110}{X}")
    print(f"{BOLD}  INDIANAPI STRESS TEST — 10 COMPANIES{X}")
    print(f"{BOLD}{'═'*110}{X}\n")

    # Detailed per-company
    for r in results:
        status = f"{G}●{X}" if r.price else f"{R}●{X}"
        print(f"{BOLD}{status} {r.company:<30}{X}  (stock:{r.stock_t:.1f}s  hist:{r.hist_t:.1f}s  stats:{r.stats_t:.1f}s  total:{r.total_t:.1f}s)")
        if r.error:
            print(f"    {R}ERROR: {r.error}{X}")
            continue
        print(f"    Price:{tick(r.price)}{r.price_val:<12}  PE:{tick(r.pe)}{r.pe_val:<10}  PB:{tick(r.pb)}{r.pb_val:<10}  EPS:{tick(r.eps)}{r.eps_val:<10}")
        print(f"    MktCap:{tick(r.market_cap)}{r.mc_val:<10}  ROE:{tick(r.roe)}{r.roe_val:<10}  ROCE:{tick(r.roce)}{r.roce_val:<10}  DivYield:{tick(r.div_yield)}{r.dy_val}")
        print(f"    Shareholding:{tick(r.shareholding)}  CorpActions:{tick(r.corp_actions)}  News:{tick(r.news)}  OHLCV:{tick(r.ohlcv)}{r.ohlcv_rows}rows  Financials:{tick(r.financials)}")
        print()

    # Accuracy matrix
    checks = [
        ("Price",        "price"),
        ("PE Ratio",     "pe"),
        ("PB Ratio",     "pb"),
        ("EPS",          "eps"),
        ("Market Cap",   "market_cap"),
        ("ROE",          "roe"),
        ("ROCE",         "roce"),
        ("Div Yield",    "div_yield"),
        ("Shareholding", "shareholding"),
        ("Corp Actions", "corp_actions"),
        ("News",         "news"),
        ("OHLCV",        "ohlcv"),
        ("Financials",   "financials"),
    ]

    print(f"{'─'*110}")
    print(f"{BOLD}  ACCURACY MATRIX{X}\n")
    print(f"  {'Metric':<20} {'Success Rate':<15} {'Details'}")
    print(f"  {'─'*60}")

    for label, attr in checks:
        vals = [getattr(r, attr) for r in results if getattr(r, attr) is not None]
        passed = sum(1 for v in vals if v)
        total  = len(vals)
        pct    = passed / total * 100 if total else 0
        color  = G if pct >= 80 else Y if pct >= 50 else R
        bar    = "█" * int(pct/10) + "░" * (10 - int(pct/10))
        print(f"  {label:<20} {color}{pct:>5.0f}%{X}  {bar}  {passed}/{total}")

    # Timing summary
    print(f"\n  {'─'*60}")
    print(f"  {'Endpoint':<20} {'Avg Time':<12} {'Min':<10} {'Max'}")
    for ep, attr in [("Stock endpoint","stock_t"),("Historical","hist_t"),("Stats/Financials","stats_t")]:
        times = [getattr(r, attr) for r in results]
        print(f"  {ep:<20} {sum(times)/len(times):.2f}s       {min(times):.2f}s      {max(times):.2f}s")

    total_pass = sum(
        1 for r in results for _, attr in checks
        if getattr(r, attr) is True
    )
    total_checks = len(checks) * len(results)
    overall = total_pass / total_checks * 100
    color = G if overall >= 80 else Y if overall >= 50 else R
    print(f"\n  {BOLD}OVERALL ACCURACY: {color}{overall:.0f}%{X}{BOLD} ({total_pass}/{total_checks} checks passed){X}")
    print(f"{BOLD}{'═'*110}{X}\n")


if __name__ == "__main__":
    print(f"\n{BOLD}Testing IndianAPI — {len(COMPANIES)} companies in parallel...{X}\n")
    t0 = time.time()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(test_company, c): c["name"] for c in COMPANIES}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                r = future.result()
                results.append(r)
                ok = r.price and r.pe
                print(f"  {'✓' if ok else '~'} {name} ({r.total_t:.1f}s)")
            except Exception as e:
                print(f"  ✗ {name} crashed: {e}")

    order = {c["name"]: i for i, c in enumerate(COMPANIES)}
    results.sort(key=lambda r: order.get(r.company, 99))

    print(f"\nDone in {time.time()-t0:.1f}s")
    print_results(results)
