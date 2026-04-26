"""
test_financials_sources.py — Compare yfinance, Screener.in, jugaad-data
for financial statement data across 10 stocks.

Statements tested:
  1. Quarterly P&L   (revenue, net profit, EPS per quarter — 4+ quarters)
  2. Annual P&L      (5+ years of revenue, PAT, EPS)
  3. Balance Sheet   (assets, liabilities, equity)
  4. Cash Flow       (operating, investing, financing)

Metrics per source:
  - Fetch success rate (did it return data at all?)
  - Row depth         (how many periods/years?)
  - Field coverage    (how many key metrics present?)
  - Speed             (seconds per stock)

Run: conda run -n datatest python test_financials_sources.py
"""

import time
import json
import requests
from bs4 import BeautifulSoup
import re

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

STOCKS = [
    ("RELIANCE",   "reliance-industries",   "RELIANCE.NS"),
    ("HDFCBANK",   "hdfc-bank",             "HDFCBANK.NS"),
    ("INFY",       "infosys",               "INFY.NS"),
    ("TATAMOTORS", "tata-motors",           "TATAMOTORS.NS"),
    ("SUNPHARMA",  "sun-pharmaceutical-industries", "SUNPHARMA.NS"),
    ("IRCTC",      "irctc",                 "IRCTC.NS"),
    ("ZOMATO",     "zomato",                "ZOMATO.NS"),
    ("COALINDIA",  "coal-india",            "COALINDIA.NS"),
    ("BAJFINANCE", "bajaj-finance",         "BAJFINANCE.NS"),
    ("DMART",      "avenue-supermarts",     "DMART.NS"),
]

STATEMENTS = ["quarterly_pl", "annual_pl", "balance_sheet", "cash_flow"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def section(t):
    print(f"\n{BOLD}{CYAN}{'─'*68}{RESET}\n{BOLD}{CYAN}  {t}{RESET}\n{BOLD}{CYAN}{'─'*68}{RESET}")

def tag(label, note=""):
    note_s = f"  {YELLOW}({note}){RESET}" if note else ""
    print(f"    {GREEN}✓{RESET} {label}{note_s}")

def bad(label, note=""):
    note_s = f"  {RED}({note}){RESET}" if note else ""
    print(f"    {RED}✗{RESET} {label}{note_s}")

def warn(label, note=""):
    note_s = f"  {YELLOW}({note}){RESET}" if note else ""
    print(f"    {YELLOW}~{RESET} {label}{note_s}")

# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 1 — yfinance
# ══════════════════════════════════════════════════════════════════════════════

def test_yfinance(ticker_ns: str) -> dict:
    import yfinance as yf
    result = {s: {"ok": False, "periods": 0, "fields": 0, "sample": ""} for s in STATEMENTS}
    try:
        t = yf.Ticker(ticker_ns)

        # Quarterly P&L
        try:
            df = t.quarterly_financials
            if df is not None and not df.empty:
                result["quarterly_pl"]["ok"] = True
                result["quarterly_pl"]["periods"] = df.shape[1]
                result["quarterly_pl"]["fields"] = df.shape[0]
                result["quarterly_pl"]["sample"] = str(list(df.index[:3]))
        except Exception as e:
            result["quarterly_pl"]["err"] = str(e)

        # Annual P&L
        try:
            df = t.financials
            if df is not None and not df.empty:
                result["annual_pl"]["ok"] = True
                result["annual_pl"]["periods"] = df.shape[1]
                result["annual_pl"]["fields"] = df.shape[0]
                result["annual_pl"]["sample"] = str(list(df.index[:3]))
        except Exception as e:
            result["annual_pl"]["err"] = str(e)

        # Balance Sheet
        try:
            df = t.balance_sheet
            if df is not None and not df.empty:
                result["balance_sheet"]["ok"] = True
                result["balance_sheet"]["periods"] = df.shape[1]
                result["balance_sheet"]["fields"] = df.shape[0]
                result["balance_sheet"]["sample"] = str(list(df.index[:3]))
        except Exception as e:
            result["balance_sheet"]["err"] = str(e)

        # Cash Flow
        try:
            df = t.cashflow
            if df is not None and not df.empty:
                result["cash_flow"]["ok"] = True
                result["cash_flow"]["periods"] = df.shape[1]
                result["cash_flow"]["fields"] = df.shape[0]
                result["cash_flow"]["sample"] = str(list(df.index[:3]))
        except Exception as e:
            result["cash_flow"]["err"] = str(e)

    except Exception as e:
        for s in STATEMENTS:
            result[s]["err"] = str(e)

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 2 — Screener.in
# ══════════════════════════════════════════════════════════════════════════════

def _screener_fetch(slug: str):
    for url in [
        f"https://www.screener.in/company/{slug}/consolidated/",
        f"https://www.screener.in/company/{slug}/",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code == 200 and len(r.text) > 5000:
                return BeautifulSoup(r.text, "html.parser")
        except Exception:
            pass
    return None

def _parse_screener_table(soup, section_id: str) -> dict:
    try:
        sec = soup.find("section", {"id": section_id}) or soup.find(id=section_id)
        if not sec:
            return {"ok": False}
        tbl = sec.find("table")
        if not tbl:
            return {"ok": False}
        headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
        rows = tbl.find_all("tr")
        data_rows = [r for r in rows if r.find("td")]
        # periods = number of columns minus label column
        periods = max(0, len(headers) - 1) if headers else 0
        return {
            "ok": True,
            "periods": periods,
            "fields": len(data_rows),
            "sample": str(headers[:4]),
        }
    except Exception as e:
        return {"ok": False, "err": str(e)}

def test_screener(slug: str) -> dict:
    result = {s: {"ok": False, "periods": 0, "fields": 0, "sample": ""} for s in STATEMENTS}
    soup = _screener_fetch(slug)
    if not soup:
        for s in STATEMENTS:
            result[s]["err"] = "page fetch failed"
        return result

    mapping = {
        "quarterly_pl":  "quarters",
        "annual_pl":     "profit-loss",
        "balance_sheet": "balance-sheet",
        "cash_flow":     "cash-flow",
    }
    for stmt, sid in mapping.items():
        r = _parse_screener_table(soup, sid)
        result[stmt] = r

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 3 — jugaad-data
# ══════════════════════════════════════════════════════════════════════════════

def test_jugaad(symbol: str) -> dict:
    result = {s: {"ok": False, "periods": 0, "fields": 0, "sample": ""} for s in STATEMENTS}
    try:
        from jugaad_data.nse import NSELive, stock_df  # type: ignore

        # jugaad only provides OHLCV via stock_df; no financial statements API
        # Check if any fin-statement module exists
        try:
            from jugaad_data import financials as jf  # type: ignore
            result["annual_pl"]["err"] = "financials module exists — checking"
        except ImportError:
            for s in STATEMENTS:
                result[s]["ok"] = False
                result[s]["err"] = "no financials module in jugaad-data"

    except ImportError:
        for s in STATEMENTS:
            result[s]["err"] = "jugaad-data not installed"
    except Exception as e:
        for s in STATEMENTS:
            result[s]["err"] = str(e)

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN RUN
# ══════════════════════════════════════════════════════════════════════════════

# Store: results[source][symbol][statement] = {ok, periods, fields, sample}
all_results = {
    "yfinance":  {},
    "screener":  {},
    "jugaad":    {},
}
timings = {
    "yfinance":  {},
    "screener":  {},
    "jugaad":    {},
}

section("SOURCE 1 — yfinance")
for symbol, slug, ticker in STOCKS:
    print(f"\n  {BOLD}[{symbol}]{RESET}  ({ticker})")
    t0 = time.time()
    r = test_yfinance(ticker)
    elapsed = round(time.time() - t0, 2)
    timings["yfinance"][symbol] = elapsed
    all_results["yfinance"][symbol] = r

    for stmt in STATEMENTS:
        d = r[stmt]
        if d["ok"]:
            tag(stmt, f"{d['periods']} periods  {d['fields']} fields  {d['sample'][:60]}")
        else:
            bad(stmt, d.get("err", "empty"))
    print(f"    {YELLOW}⏱  {elapsed}s{RESET}")
    time.sleep(0.3)

section("SOURCE 2 — Screener.in")
for symbol, slug, ticker in STOCKS:
    print(f"\n  {BOLD}[{symbol}]{RESET}  ({slug})")
    t0 = time.time()
    r = test_screener(slug)
    elapsed = round(time.time() - t0, 2)
    timings["screener"][symbol] = elapsed
    all_results["screener"][symbol] = r

    for stmt in STATEMENTS:
        d = r[stmt]
        if d.get("ok"):
            tag(stmt, f"{d['periods']} periods  {d['fields']} fields  {d.get('sample','')[:60]}")
        else:
            bad(stmt, d.get("err", "empty / missing"))
    print(f"    {YELLOW}⏱  {elapsed}s{RESET}")
    time.sleep(1.5)

section("SOURCE 3 — jugaad-data")
for symbol, slug, ticker in STOCKS:
    print(f"\n  {BOLD}[{symbol}]{RESET}")
    t0 = time.time()
    r = test_jugaad(symbol)
    elapsed = round(time.time() - t0, 2)
    timings["jugaad"][symbol] = elapsed
    all_results["jugaad"][symbol] = r

    for stmt in STATEMENTS:
        d = r[stmt]
        if d.get("ok"):
            tag(stmt, f"{d['periods']} periods  {d['fields']} fields")
        else:
            bad(stmt, d.get("err", "empty"))
    print(f"    {YELLOW}⏱  {elapsed}s{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════
section("SUMMARY — Success Rate per Source per Statement")

sources = ["yfinance", "screener", "jugaad"]
col = 16
sym_w = 12

for source in sources:
    print(f"\n  {BOLD}{source.upper()}{RESET}")
    header = f"  {'Statement':<20}" + "".join(f"{s:<{sym_w}}" for s, *_ in STOCKS) + "  Rate  Avg periods  Avg fields  AvgTime"
    print(header)
    print(f"  {'─'*20}" + "─"*sym_w*len(STOCKS) + "─"*40)

    for stmt in STATEMENTS:
        row = f"  {stmt:<20}"
        pass_count = 0
        total_periods = []
        total_fields  = []
        for symbol, *_ in STOCKS:
            d = all_results[source].get(symbol, {}).get(stmt, {})
            if d.get("ok"):
                pass_count += 1
                total_periods.append(d.get("periods", 0))
                total_fields.append(d.get("fields", 0))
                row += f"{GREEN}✓{RESET}{'':<{sym_w-1}}"
            else:
                row += f"{RED}✗{RESET}{'':<{sym_w-1}}"

        pct = int(100 * pass_count / len(STOCKS))
        avg_p = round(sum(total_periods)/len(total_periods), 1) if total_periods else 0
        avg_f = round(sum(total_fields)/len(total_fields), 1) if total_fields else 0
        avg_t = round(sum(timings[source].values())/len(timings[source]), 1)
        color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
        row += f"  {color}{pct:3d}%{RESET}  {avg_p:<12} {avg_f:<11} {avg_t}s"
        print(row)


# ══════════════════════════════════════════════════════════════════════════════
#  FINAL RANKING
# ══════════════════════════════════════════════════════════════════════════════
section("FINAL RANKING — Best Source for Financial Statements")

# Score: success_rate * 0.5 + has_depth * 0.3 + speed_score * 0.2
scores = {}
for source in sources:
    total_pass = 0
    total_checks = len(STOCKS) * len(STATEMENTS)
    total_periods = []
    for symbol, *_ in STOCKS:
        for stmt in STATEMENTS:
            d = all_results[source].get(symbol, {}).get(stmt, {})
            if d.get("ok"):
                total_pass += 1
                total_periods.append(d.get("periods", 0))
    success_rate = total_pass / total_checks
    avg_periods  = (sum(total_periods)/len(total_periods)) if total_periods else 0
    avg_time     = sum(timings[source].values()) / len(timings[source])
    # normalise speed: faster = better (cap at 10s)
    speed_score  = max(0, 1 - avg_time / 10)
    depth_score  = min(1, avg_periods / 12)   # 12 quarters = perfect depth
    score = success_rate * 0.5 + depth_score * 0.3 + speed_score * 0.2
    scores[source] = {
        "score": round(score, 3),
        "success_pct": round(100 * success_rate, 1),
        "avg_periods": round(avg_periods, 1),
        "avg_time_s": round(avg_time, 1),
    }

ranked = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)

print()
for rank, (source, s) in enumerate(ranked, 1):
    medal = ["🥇", "🥈", "🥉"][rank-1]
    color = [GREEN, YELLOW, RED][rank-1]
    print(f"  {medal}  {color}{BOLD}#{rank} {source.upper()}{RESET}")
    print(f"      Score        : {color}{s['score']}{RESET}")
    print(f"      Success rate : {s['success_pct']}%")
    print(f"      Avg periods  : {s['avg_periods']} columns per statement")
    print(f"      Avg speed    : {s['avg_time_s']}s per stock")
    print()
