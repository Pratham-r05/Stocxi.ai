"""
test_data_providers.py — Standalone API tester for NSE + BSE data sources.

Usage:
    python test_data_providers.py RELIANCE
    python test_data_providers.py ANANTRAJ
    python test_data_providers.py PRESTIGE

Tests every endpoint independently. Shows exactly what data comes back,
what's missing, and how long each call takes.
No existing backend code is touched or imported.
"""

import sys
import time
import json
import requests
from datetime import date, timedelta

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓ {msg}{RESET}")
def fail(msg): print(f"  {RED}✗ {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠ {msg}{RESET}")
def info(msg): print(f"  {BLUE}→ {msg}{RESET}")
def head(msg): print(f"\n{BOLD}{msg}{RESET}\n{'─'*60}")

TIMEOUT = 15

# ══════════════════════════════════════════════════════════════════════════════
# NSE SESSION
# ══════════════════════════════════════════════════════════════════════════════

def make_nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":          "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.nseindia.com/",
    })
    try:
        s.get("https://www.nseindia.com", timeout=TIMEOUT)
        s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=TIMEOUT)
    except Exception:
        pass
    return s

# ══════════════════════════════════════════════════════════════════════════════
# BSE SESSION
# ══════════════════════════════════════════════════════════════════════════════

def make_bse_session(scripcode: str = "") -> requests.Session:
    s = requests.Session()
    referer = (
        f"https://www.bseindia.com/stock-share-price/x/x/{scripcode}/"
        if scripcode else "https://www.bseindia.com/"
    )
    s.headers.update({
        "User-Agent":       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":           "application/json, text/plain, */*",
        "Accept-Language":  "en-US,en;q=0.9",
        "Accept-Encoding":  "gzip, deflate, br",
        "Referer":          referer,
        "Origin":           "https://www.bseindia.com",
        "Sec-Fetch-Dest":   "empty",
        "Sec-Fetch-Mode":   "cors",
        "Sec-Fetch-Site":   "same-site",
        "sec-ch-ua":        '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    })
    try:
        s.get("https://www.bseindia.com/", timeout=TIMEOUT)
    except Exception:
        pass
    return s

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def timed_get(session, url, params=None):
    t0 = time.time()
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
        elapsed = time.time() - t0
        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                return r.json(), elapsed
            # try parsing anyway
            try:
                return r.json(), elapsed
            except Exception:
                return None, elapsed
        return None, elapsed
    except Exception:
        return None, time.time() - t0


# ══════════════════════════════════════════════════════════════════════════════
# BSE SCRIP CODE LOOKUP
# ══════════════════════════════════════════════════════════════════════════════

# Hardcoded map for common symbols — BSE search API is flaky
_BSE_CODE_MAP = {
    "ANANTRAJ":  "515055",
    "PRESTIGE":  "533274",
    "RELIANCE":  "500325",
    "TCS":       "532540",
    "INFY":      "500209",
    "HDFCBANK":  "500180",
    "WIPRO":     "507685",
    "ITC":       "500875",
    "TATAMOTORS":"500570",
    "SBIN":      "500112",
    "ADANIENT":  "512599",
    "BAJFINANCE":"500034",
    "MARUTI":    "532500",
    "SUNPHARMA": "524715",
    "ONGC":      "500312",
}

def resolve_bse_code(symbol: str, nse_session) -> str | None:
    """Try hardcoded map first, then NSE ISIN lookup → BSE code."""
    if symbol in _BSE_CODE_MAP:
        return _BSE_CODE_MAP[symbol]

    # Use NSE to get ISIN, then resolve BSE scrip code via BSE ISIN API
    try:
        data, _ = timed_get(nse_session, f"https://www.nseindia.com/api/quote-equity?symbol={symbol}")
        if data:
            isin = (data.get("metadata") or {}).get("isin")
            if isin:
                bse_s = make_bse_session()
                d, _ = timed_get(bse_s, f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?isin={isin}&seriesid=")
                if d and isinstance(d, dict):
                    code = d.get("scripcode") or d.get("Scripcode")
                    if code:
                        return str(code)
    except Exception:
        pass

    return None


# ══════════════════════════════════════════════════════════════════════════════
# NSE TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_nse_quote(s, symbol):
    head(f"NSE — Live Quote [{symbol}]")
    data, t = timed_get(s, f"https://www.nseindia.com/api/quote-equity?symbol={symbol}")
    if not data:
        fail(f"No data ({t:.2f}s)"); return None

    pd_  = data.get("priceInfo", {})
    td   = data.get("tradeInfo", {})
    md   = data.get("metadata", {})
    ihl  = pd_.get("intraDayHighLow") or {}
    whl  = pd_.get("weekHighLow") or {}

    fields = {
        "Company Name":    md.get("companyName"),
        "Symbol":          md.get("symbol"),
        "Industry":        md.get("industry"),
        "ISIN":            md.get("isin"),
        "Last Price":      pd_.get("lastPrice"),
        "Open":            pd_.get("open"),
        "Prev Close":      pd_.get("previousClose"),
        "Day High":        ihl.get("max"),
        "Day Low":         ihl.get("min"),
        "52W High":        whl.get("max"),
        "52W Low":         whl.get("min"),
        "Change %":        pd_.get("pChange"),
        "Volume":          td.get("totalTradedVolume"),
        "Market Cap (Cr)": td.get("totalMarketCap"),
        "Upper Circuit":   pd_.get("upperCP"),
        "Lower Circuit":   pd_.get("lowerCP"),
        "Face Value":      md.get("pdFaceValue"),
    }
    for k, v in fields.items():
        ok(f"{k}: {v}") if v not in (None, "") else warn(f"{k}: missing")
    info(f"Time: {t:.2f}s")
    return data


def test_nse_historical(s, symbol):
    head(f"NSE — Historical OHLCV [{symbol}] (1 year)")
    end   = date.today()
    start = end - timedelta(days=365)
    params = {
        "symbol":   symbol,
        "series[]": "EQ",
        "from":     start.strftime("%d-%m-%Y"),
        "to":       end.strftime("%d-%m-%Y"),
    }
    data, t = timed_get(s, "https://www.nseindia.com/api/historical/cm/equity", params=params)
    if not data:
        fail(f"No data ({t:.2f}s)"); return

    rows = data.get("data", [])
    if rows:
        r = rows[0]
        ok(f"{len(rows)} candles | Range: {rows[-1].get('CH_TIMESTAMP')} → {rows[0].get('CH_TIMESTAMP')}")
        ok(f"Sample → O:{r.get('CH_OPENING_PRICE')} H:{r.get('CH_TRADE_HIGH_PRICE')} L:{r.get('CH_TRADE_LOW_PRICE')} C:{r.get('CH_CLOSING_PRICE')} V:{r.get('CH_TOT_TRADED_QTY')}")
    else:
        fail("Empty candle list")
    info(f"Time: {t:.2f}s")


def test_nse_corporate_actions(s, symbol):
    head(f"NSE — Corporate Actions [{symbol}]")
    data, t = timed_get(s, f"https://www.nseindia.com/api/corporates-corporateActions?index=equities&symbol={symbol}")
    if not data or not isinstance(data, list):
        fail(f"No data ({t:.2f}s)"); return
    ok(f"{len(data)} corporate actions")
    for item in data[:4]:
        ok(f"  {item.get('exDate','?')} | {item.get('subject','?')[:70]}")
    info(f"Time: {t:.2f}s")


def test_nse_announcements(s, symbol):
    head(f"NSE — Announcements [{symbol}]")
    data, t = timed_get(s, "https://www.nseindia.com/api/corp-announcements", params={"index":"equities","symbol":symbol})
    if not data or not isinstance(data, list):
        fail(f"No data ({t:.2f}s)"); return
    ok(f"{len(data)} announcements")
    for item in data[:3]:
        ok(f"  [{item.get('an_dt','?')}] {str(item.get('desc','?'))[:70]}")
    info(f"Time: {t:.2f}s")


def test_nse_shareholding(s, symbol):
    head(f"NSE — Shareholding Pattern [{symbol}]")
    data, t = timed_get(s, f"https://www.nseindia.com/api/corporate-shareholding-pattern?symbol={symbol}&$csrf=undefined")
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return
    rows = data.get("data", [])
    if rows:
        r = rows[0]
        ok(f"Latest period: {r.get('period','?')}")
        ok(f"Promoter: {r.get('promoter','?')}%  |  FII: {r.get('fii','?')}%  |  DII: {r.get('dii','?')}%  |  Public: {r.get('public','?')}%")
    else:
        fail("No shareholding rows")
    info(f"Time: {t:.2f}s")


# ══════════════════════════════════════════════════════════════════════════════
# BSE TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_bse_quote(s, sc, symbol):
    head(f"BSE — Live Quote + Fundamentals [{symbol} / {sc}]")
    data, t = timed_get(s, f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode={sc}&seriesid=")
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    price  = data.get("CurrRate", {})
    basic  = data.get("Cmpname",  {})
    ratios = data.get("Ratios",   data)

    fields = {
        "Company Name":   basic.get("FullN") or data.get("CompanyName"),
        "Last Price":     price.get("LTP"),
        "Change":         price.get("Chg"),
        "Change %":       price.get("PcChg"),
        "Open":           data.get("OpnRate") or (data.get("Ohlc") or {}).get("Open"),
        "High (day)":     data.get("DayHigh"),
        "Low (day)":      data.get("DayLow"),
        "Volume":         data.get("TotVol") or data.get("Trdvol"),
        "52W High":       data.get("High52") or data.get("FiftyTwoWeekHigh"),
        "52W Low":        data.get("Low52")  or data.get("FiftyTwoWeekLow"),
        "Market Cap":     data.get("Mktcap") or data.get("MarketCap"),
        "PE Ratio":       data.get("PE")     or data.get("PERatio"),
        "PB Ratio":       data.get("PriceBV") or data.get("PBRatio"),
        "EPS":            data.get("EPS"),
        "Book Value":     data.get("BV")     or data.get("BookValue"),
        "Dividend Yield": data.get("DivYield") or data.get("DividendYield"),
        "Face Value":     data.get("FaceValue") or data.get("facevalue"),
        "Industry":       data.get("Industry") or data.get("industry"),
        "ISIN":           data.get("ISIN") or data.get("isin"),
    }
    for k, v in fields.items():
        ok(f"{k}: {v}") if v not in (None, "", "0", 0) else warn(f"{k}: missing")

    if any(v in (None, "", "0", 0) for v in [fields["PE Ratio"], fields["PB Ratio"], fields["EPS"]]):
        info(f"Raw keys available: {list(data.keys())}")
    info(f"Time: {t:.2f}s")
    return data


def test_bse_historical(s, sc, symbol):
    head(f"BSE — Historical OHLCV [{symbol}] (1 year)")
    end   = date.today()
    start = end - timedelta(days=365)
    url   = (f"https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w"
             f"?scripcode={sc}&seriesid=EQ&flag=0"
             f"&fromdate={start.strftime('%Y%m%d')}&todate={end.strftime('%Y%m%d')}&type=I")
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    candles = data.get("Data", data.get("data", []))
    if candles and isinstance(candles, list):
        ok(f"{len(candles)} daily candles")
        ok(f"Sample: {candles[0]}")
    else:
        fail("No candle data"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


def test_bse_quarterly(s, sc, symbol):
    head(f"BSE — Quarterly Results [{symbol}]")
    url  = f"https://api.bseindia.com/BseIndiaAPI/api/FinancialResults/w?scripcode={sc}&type=Quarterly"
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    for key in ["Table", "Table1", "data"]:
        rows = data.get(key, [])
        if rows and isinstance(rows, list):
            ok(f"{len(rows)} rows via key '{key}'")
            labels = list(dict.fromkeys(
                r.get("display_name") or r.get("key_name") or r.get("ROWHEAD","")
                for r in rows
            ))
            for l in labels[:12]:
                if l: ok(f"  Field: {l}")
            break
    else:
        fail("No rows"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


def test_bse_balance_sheet(s, sc, symbol):
    head(f"BSE — Balance Sheet [{symbol}]")
    url  = f"https://api.bseindia.com/BseIndiaAPI/api/BalanceSheetData/w?scripcode={sc}&type=Consolidated"
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    for key in ["Table", "Table1", "data"]:
        rows = data.get(key, [])
        if rows and isinstance(rows, list):
            ok(f"{len(rows)} rows via key '{key}'")
            labels = list(dict.fromkeys(
                r.get("display_name") or r.get("key_name") or r.get("ROWHEAD","")
                for r in rows
            ))
            for l in labels[:12]:
                if l: ok(f"  Field: {l}")
            break
    else:
        fail("No rows"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


def test_bse_cash_flow(s, sc, symbol):
    head(f"BSE — Cash Flow [{symbol}]")
    url  = f"https://api.bseindia.com/BseIndiaAPI/api/CashFlowData/w?scripcode={sc}&type=Consolidated"
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    for key in ["Table", "Table1", "data"]:
        rows = data.get(key, [])
        if rows and isinstance(rows, list):
            ok(f"{len(rows)} rows via key '{key}'")
            labels = list(dict.fromkeys(
                r.get("display_name") or r.get("key_name") or r.get("ROWHEAD","")
                for r in rows
            ))
            for l in labels[:10]:
                if l: ok(f"  Field: {l}")
            break
    else:
        fail("No rows"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


def test_bse_shareholding(s, sc, symbol):
    head(f"BSE — Shareholding Pattern [{symbol}]")
    url  = f"https://api.bseindia.com/BseIndiaAPI/api/ShareHoldingPatern/w?scripcode={sc}"
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    for key in ["ShareHoldingPaternData", "Table", "Table1", "data"]:
        rows = data.get(key, [])
        if rows and isinstance(rows, list):
            ok(f"{len(rows)} rows via key '{key}'")
            for r in rows[:4]:
                category = r.get("category") or r.get("Category") or r.get("shareholder_type","")
                pct      = r.get("percentage") or r.get("Percentage") or r.get("pct","")
                if category:
                    ok(f"  {category}: {pct}%")
            break
    else:
        fail("No rows"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


def test_bse_announcements(s, sc, symbol):
    head(f"BSE — Announcements [{symbol}]")
    url = (f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryQueryResultDetails/w"
           f"?pageno=1&query=&strSearch=E&deadline=0&scripcode={sc}&anntype=&segment=&subcategory=")
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    for key in ["Table", "Table1", "data"]:
        rows = data.get(key, [])
        if rows and isinstance(rows, list):
            ok(f"{len(rows)} announcements")
            for r in rows[:4]:
                dt       = r.get("News_submission_dt") or r.get("DT_TM") or ""
                headline = r.get("HEADLINE") or r.get("NEWSSUB") or ""
                ok(f"  [{dt[:10]}] {str(headline)[:75]}")
            break
    else:
        fail("No rows"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


def test_bse_mf_holdings(s, sc, symbol):
    head(f"BSE — MF / Institutional Holdings [{symbol}]")
    url = f"https://api.bseindia.com/BseIndiaAPI/api/MFHoldingData/w?scripcode={sc}"
    data, t = timed_get(s, url)
    if not data or not isinstance(data, dict):
        fail(f"No data ({t:.2f}s)"); return

    for key in ["Table", "Table1", "data"]:
        rows = data.get(key, [])
        if rows and isinstance(rows, list):
            ok(f"{len(rows)} MF holding records")
            for r in rows[:3]:
                ok(f"  {r}")
            break
    else:
        fail("No rows"); info(f"Keys: {list(data.keys())}")
    info(f"Time: {t:.2f}s")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run(symbol: str):
    symbol = symbol.upper().strip()
    t_total = time.time()

    print(f"\n{'═'*60}")
    print(f"{BOLD}  DATA PROVIDER TEST — {symbol}{RESET}")
    print(f"{'═'*60}")

    # ── NSE ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═'*20} NSE APIs {'═'*20}{RESET}")
    print("  Warming NSE session...")
    nse = make_nse_session()

    test_nse_quote(nse, symbol)
    test_nse_historical(nse, symbol)
    test_nse_corporate_actions(nse, symbol)
    test_nse_announcements(nse, symbol)
    test_nse_shareholding(nse, symbol)

    # ── BSE ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═'*20} BSE APIs {'═'*20}{RESET}")
    sc = resolve_bse_code(symbol, nse)
    if sc:
        ok(f"BSE Scrip Code: {sc}")
        bse = make_bse_session(sc)
        test_bse_quote(bse, sc, symbol)
        test_bse_historical(bse, sc, symbol)
        test_bse_quarterly(bse, sc, symbol)
        test_bse_balance_sheet(bse, sc, symbol)
        test_bse_cash_flow(bse, sc, symbol)
        test_bse_shareholding(bse, sc, symbol)
        test_bse_announcements(bse, sc, symbol)
        test_bse_mf_holdings(bse, sc, symbol)
    else:
        fail(f"BSE scrip code not found for '{symbol}'")
        warn("Add it to _BSE_CODE_MAP in the script for now")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"{BOLD}  Total time: {time.time()-t_total:.2f}s{RESET}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_data_providers.py SYMBOL")
        print("Examples: python test_data_providers.py RELIANCE")
        sys.exit(1)
    run(sys.argv[1])
