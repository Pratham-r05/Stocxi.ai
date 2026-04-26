"""
stress_test.py — Parallel stress test for NSE + BSE + Screener across 10 companies.
Tests every data category, measures timing, calculates accuracy ratio per provider.
"""

import time
import requests
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional

# ── Colors ─────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; BOLD = "\033[1m"; X = "\033[0m"

# ── Company list ───────────────────────────────────────────────────────────────
COMPANIES = [
    {"name": "Trent",                        "nse": "TRENT",        "bse": "500251"},
    {"name": "Oil & Natural Gas Corp",       "nse": "ONGC",         "bse": "500312"},
    {"name": "Gujarat Natural Resources",    "nse": "GNRL",         "bse": "519570"},
    {"name": "Yaap Digital",                 "nse": "YAAPDIGITAL",  "bse": "543532"},
    {"name": "Ashoka Buildcon",              "nse": "ASHOKA",       "bse": "533271"},
    {"name": "Transformers & Rectifiers",    "nse": "TRIL",         "bse": "533161"},
    {"name": "SDC Techmedia",               "nse": "SDCTECHMEDIA", "bse": "544015"},
    {"name": "Sun Pharmaceutical",           "nse": "SUNPHARMA",    "bse": "524715"},
    {"name": "Polycab",                      "nse": "POLYCAB",      "bse": "542652"},
    {"name": "KJMC Financial Services",      "nse": "KJMCFIN",      "bse": "512237"},
]

TIMEOUT = 12

# ── Result container ───────────────────────────────────────────────────────────
@dataclass
class TestResult:
    company: str
    nse_quote:       Optional[bool] = None;  nse_quote_t:       float = 0
    nse_history:     Optional[bool] = None;  nse_history_t:     float = 0
    nse_actions:     Optional[bool] = None;  nse_actions_t:     float = 0
    nse_announce:    Optional[bool] = None;  nse_announce_t:    float = 0
    nse_fin_results: Optional[bool] = None;  nse_fin_results_t: float = 0
    screener_ratios: Optional[bool] = None;  screener_ratios_t: float = 0
    screener_pl:     Optional[bool] = None;  screener_pl_t:     float = 0
    screener_bs:     Optional[bool] = None;  screener_bs_t:     float = 0
    screener_cf:     Optional[bool] = None;  screener_cf_t:     float = 0
    screener_shp:    Optional[bool] = None;  screener_shp_t:    float = 0
    bse_quote:       Optional[bool] = None;  bse_quote_t:       float = 0
    total_t:         float = 0
    notes:           list  = field(default_factory=list)


# ── NSE session factory ────────────────────────────────────────────────────────
def make_nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept":          "application/json, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    })
    try:
        s.get("https://www.nseindia.com", timeout=TIMEOUT)
        s.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", timeout=TIMEOUT)
    except Exception:
        pass
    return s


# ── BSE session factory ────────────────────────────────────────────────────────
def make_bse_session(bse_code: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent":       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept":           "application/json, text/plain, */*",
        "Accept-Language":  "en-US,en;q=0.9",
        "Referer":          f"https://www.bseindia.com/stock-share-price/x/x/{bse_code}/",
        "Origin":           "https://www.bseindia.com",
        "Sec-Fetch-Dest":   "empty",
        "Sec-Fetch-Mode":   "cors",
        "Sec-Fetch-Site":   "same-site",
    })
    try:
        s.get("https://www.bseindia.com/", timeout=TIMEOUT)
    except Exception:
        pass
    return s


def _get(session, url, params=None) -> tuple[any, float]:
    t0 = time.time()
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
        elapsed = time.time() - t0
        if r.status_code == 200:
            try:
                return r.json(), elapsed
            except Exception:
                return None, elapsed
        return None, elapsed
    except Exception:
        return None, time.time() - t0


# ── Screener session ───────────────────────────────────────────────────────────
SCREENER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,*/*",
}

def screener_fetch(symbol: str) -> tuple[dict, float]:
    """Returns (parsed sections dict, elapsed). Never raises."""
    result = {"ratios": False, "pl": False, "bs": False, "cf": False, "shp": False}
    t0 = time.time()
    try:
        from bs4 import BeautifulSoup
        for url in [
            f"https://www.screener.in/company/{symbol}/consolidated/",
            f"https://www.screener.in/company/{symbol}/",
        ]:
            r = requests.get(url, headers=SCREENER_HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")
                if soup.find("section", {"id": "quarters"}):
                    result["ratios"] = bool(soup.find("ul", {"id": "top-ratios"}))
                    result["pl"]     = bool(soup.find("section", {"id": "profit-loss"}))
                    result["bs"]     = bool(soup.find("section", {"id": "balance-sheet"}))
                    result["cf"]     = bool(soup.find("section", {"id": "cash-flow"}))
                    result["shp"]    = bool(soup.find("section", {"id": "shareholding"}))
                    break
    except Exception:
        pass
    return result, time.time() - t0


# ── Per-company test ───────────────────────────────────────────────────────────
def test_company(company: dict, nse_session: requests.Session) -> TestResult:
    name = company["name"]
    nse  = company["nse"]
    bse  = company["bse"]
    res  = TestResult(company=name)
    t_total = time.time()

    # ── NSE Quote ──────────────────────────────────────────────────────────────
    data, t = _get(nse_session, f"https://www.nseindia.com/api/quote-equity?symbol={nse}")
    res.nse_quote_t = t
    if data and isinstance(data, dict) and data.get("priceInfo", {}).get("lastPrice"):
        res.nse_quote = True
    else:
        res.nse_quote = False
        res.notes.append(f"NSE quote fail ({nse})")

    # ── NSE Historical ─────────────────────────────────────────────────────────
    from datetime import date, timedelta
    end   = date.today()
    start = end - timedelta(days=365)
    data, t = _get(nse_session, "https://www.nseindia.com/api/historical/cm/equity", params={
        "symbol": nse, "series[]": "EQ",
        "from": start.strftime("%d-%m-%Y"), "to": end.strftime("%d-%m-%Y"),
    })
    res.nse_history_t = t
    res.nse_history = bool(data and isinstance(data, dict) and data.get("data"))

    # ── NSE Corporate Actions ──────────────────────────────────────────────────
    data, t = _get(nse_session, f"https://www.nseindia.com/api/corporates-corporateActions?index=equities&symbol={nse}")
    res.nse_actions_t = t
    res.nse_actions = bool(data and isinstance(data, list) and len(data) > 0)

    # ── NSE Announcements ──────────────────────────────────────────────────────
    data, t = _get(nse_session, f"https://www.nseindia.com/api/corporate-announcements?symbol={nse}&index=equities")
    res.nse_announce_t = t
    res.nse_announce = bool(data and isinstance(data, list) and len(data) > 0)

    # ── NSE Financial Results (Q filings) ─────────────────────────────────────
    data, t = _get(nse_session, f"https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol={nse}&period=Quarterly")
    res.nse_fin_results_t = t
    res.nse_fin_results = bool(data and isinstance(data, list) and len(data) > 0)

    # ── BSE Quote ──────────────────────────────────────────────────────────────
    bse_session = make_bse_session(bse)
    data, t = _get(bse_session, f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode={bse}&seriesid=")
    res.bse_quote_t = t
    res.bse_quote = bool(
        data and isinstance(data, dict) and
        data.get("CurrRate", {}).get("LTP") not in (None, "", "0")
    )

    # ── Screener ───────────────────────────────────────────────────────────────
    sections, t_scr = screener_fetch(nse)
    res.screener_ratios_t = t_scr
    res.screener_pl_t     = t_scr
    res.screener_bs_t     = t_scr
    res.screener_cf_t     = t_scr
    res.screener_shp_t    = t_scr
    res.screener_ratios = sections["ratios"]
    res.screener_pl     = sections["pl"]
    res.screener_bs     = sections["bs"]
    res.screener_cf     = sections["cf"]
    res.screener_shp    = sections["shp"]

    res.total_t = time.time() - t_total
    return res


# ── Print results matrix ───────────────────────────────────────────────────────
def cell(v: Optional[bool], t: float) -> str:
    if v is True:  return f"{G}✓{X}({t:.1f}s)"
    if v is False: return f"{R}✗{X}({t:.1f}s)"
    return f"{Y}?{X}"

def pct(results, attr):
    vals = [getattr(r, attr) for r in results if getattr(r, attr) is not None]
    if not vals: return "N/A"
    ratio = sum(1 for v in vals if v) / len(vals) * 100
    color = G if ratio >= 80 else Y if ratio >= 50 else R
    return f"{color}{ratio:.0f}%{X}"

def avg_t(results, attr):
    vals = [getattr(r, attr) for r in results]
    return f"{sum(vals)/len(vals):.1f}s" if vals else "N/A"


def print_results(results: list[TestResult]):
    cols = [
        ("NSE\nQuote",   "nse_quote",       "nse_quote_t"),
        ("NSE\nHistory", "nse_history",      "nse_history_t"),
        ("NSE\nActions", "nse_actions",      "nse_actions_t"),
        ("NSE\nAnnounce","nse_announce",     "nse_announce_t"),
        ("NSE\nFin Res", "nse_fin_results",  "nse_fin_results_t"),
        ("BSE\nQuote",   "bse_quote",        "bse_quote_t"),
        ("SCR\nRatios",  "screener_ratios",  "screener_ratios_t"),
        ("SCR\nP&L",     "screener_pl",      "screener_pl_t"),
        ("SCR\nBalSheet","screener_bs",      "screener_bs_t"),
        ("SCR\nCashFlow","screener_cf",      "screener_cf_t"),
        ("SCR\nSHP",     "screener_shp",     "screener_shp_t"),
    ]

    NAME_W = 32
    COL_W  = 11

    print(f"\n{BOLD}{'═'*120}{X}")
    print(f"{BOLD}  STRESS TEST RESULTS — 10 COMPANIES{X}")
    print(f"{BOLD}{'═'*120}{X}\n")

    # Header
    header = f"{'Company':<{NAME_W}}"
    for label, _, _ in cols:
        short = label.replace('\n', ' ')
        header += f"  {short:<{COL_W}}"
    header += "  Total"
    print(f"{BOLD}{header}{X}")
    print("─" * 130)

    # Rows
    for r in results:
        row = f"{r.company:<{NAME_W}}"
        for _, attr, t_attr in cols:
            v = getattr(r, attr)
            t = getattr(r, t_attr)
            c = cell(v, t)
            # pad accounting for color codes
            visible_len = len(f"{'✓' if v else '✗'}({t:.1f}s)")
            padding = COL_W - visible_len
            row += f"  {c}{' '*max(0,padding)}"
        row += f"  {BOLD}{r.total_t:.1f}s{X}"
        print(row)

    print("─" * 130)

    # Accuracy row
    acc = f"{'ACCURACY RATIO':<{NAME_W}}"
    for _, attr, t_attr in cols:
        p = pct(results, attr)
        # rough padding
        acc += f"  {p}{'':>5}"
    print(f"{BOLD}{acc}{X}")

    # Avg time row
    avg = f"{'AVG TIME':<{NAME_W}}"
    for _, attr, t_attr in cols:
        avg += f"  {avg_t(results, t_attr):<{COL_W}}"
    print(f"{BOLD}{avg}{X}")

    print(f"\n{BOLD}{'═'*120}{X}")

    # Per-provider summary
    print(f"\n{BOLD}  PROVIDER SUMMARY{X}")
    print("─" * 60)

    nse_checks = ["nse_quote","nse_history","nse_actions","nse_announce","nse_fin_results"]
    bse_checks = ["bse_quote"]
    scr_checks = ["screener_ratios","screener_pl","screener_bs","screener_cf","screener_shp"]

    for provider, checks, label in [
        ("NSE", nse_checks, "NSE APIs"),
        ("BSE", bse_checks, "BSE API"),
        ("Screener", scr_checks, "Screener.in"),
    ]:
        total_tests = len(checks) * len(results)
        passed = sum(
            1 for r in results for c in checks
            if getattr(r, c) is True
        )
        ratio = passed / total_tests * 100
        color = G if ratio >= 80 else Y if ratio >= 50 else R
        times = [getattr(r, c+"_t") for r in results for c in checks]
        avg_time = sum(times)/len(times) if times else 0
        print(f"  {BOLD}{label:<20}{X} {color}{ratio:.0f}% success{X}  ({passed}/{total_tests} checks)  avg {avg_time:.1f}s/call")

    # Notes / failures
    failures = [(r.company, n) for r in results for n in r.notes]
    if failures:
        print(f"\n{BOLD}  NOTABLE FAILURES{X}")
        print("─" * 60)
        for company, note in failures:
            print(f"  {R}{company}{X}: {note}")

    print()


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{BOLD}Warming up NSE session...{X}")
    nse_session = make_nse_session()
    print(f"{G}NSE session ready.{X}")

    print(f"{BOLD}Running parallel tests for {len(COMPANIES)} companies...{X}\n")
    t_start = time.time()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(test_company, c, nse_session): c["name"]
            for c in COMPANIES
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                r = future.result()
                results.append(r)
                status = f"{G}✓{X}" if (r.nse_quote and r.screener_ratios) else f"{Y}~{X}"
                print(f"  {status} {name} done ({r.total_t:.1f}s)")
            except Exception as e:
                print(f"  {R}✗ {name} crashed: {e}{X}")

    # Sort by original order
    order = {c["name"]: i for i, c in enumerate(COMPANIES)}
    results.sort(key=lambda r: order.get(r.company, 99))

    print(f"\nAll tests done in {time.time()-t_start:.1f}s")
    print_results(results)
