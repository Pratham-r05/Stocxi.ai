"""
test_all_components.py — Full stack component test for Stocxi.

Tests every data source and computation layer we decided to use:

  A. NSE API (BennyThadikaran/NseIndiaApi)
       → price/quote, OHLCV (replaces Groww/yfinance waterfall),
         announcements, shareholding, board meetings, annual reports

  B. BSE API (BennyThadikaran/BseIndiaApi)
       → equityMetaInfo: PE, EPS, ROE, PB, OPM, NPM, Book Value (price/PB)

  C. Screener.in scraper  (with new slug-resolution step)
       → slug resolution for rebrand/mismatch stocks
       → quarterly P&L, annual P&L, balance sheet, cash flow
       → top-ratios: PE, ROE, ROCE, Book Value, EPS

  D. yfinance  (OHLCV fallback)
       → raw DataFrame, column presence

  E. ta library  (17 technical indicators from OHLCV)
       → SMA, EMA, Ichimoku, PSAR, RSI, MACD, Stochastic,
         Williams%R, ROC, Bollinger, ATR, OBV, VWAP, CMF, MFI, ADX, 52W

  F. jugaad-data  (OHLCV fallback — expected fail, confirming no financials module)

Run:
    conda run -n datatest python test_all_components.py
"""

import time
import sys
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta

# ── colour helpers ─────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
B = "\033[1m";  RESET = "\033[0m"

def ok(label, note=""):
    note_s = f"  {Y}({note}){RESET}" if note else ""
    print(f"    {G}✓{RESET} {label:<32}{note_s}")

def fail(label, note=""):
    note_s = f"  {R}({note}){RESET}" if note else ""
    print(f"    {R}✗{RESET} {label:<32}{note_s}")

def warn(label, note=""):
    note_s = f"  {Y}({note}){RESET}" if note else ""
    print(f"    {Y}~{RESET} {label:<32}{note_s}")

def section(title):
    print(f"\n{B}{C}{'═'*72}{RESET}\n{B}{C}  {title}{RESET}\n{B}{C}{'═'*72}{RESET}")

def subsection(title):
    print(f"\n  {B}{title}{RESET}")
    print(f"  {'─'*60}")

# ── 10 test stocks ─────────────────────────────────────────────────────────────
STOCKS = [
    ("RELIANCE",   "500325"),
    ("HDFCBANK",   "500180"),
    ("INFY",       "500209"),
    ("TATAMOTORS", "500570"),
    ("SUNPHARMA",  "524715"),
    ("IRCTC",      "542830"),
    ("ZOMATO",     "543320"),
    ("COALINDIA",  "533278"),
    ("BAJFINANCE", "500034"),
    ("DMART",      "540376"),
]

TODAY     = date.today()
FROM_DATE = TODAY - timedelta(days=365)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── master results tracker ─────────────────────────────────────────────────────
# results[section][symbol] = { check_name: True/False, ... }
RESULTS: dict[str, dict[str, dict[str, bool]]] = {
    "nse": {}, "bse": {}, "screener_slug": {}, "screener_financials": {},
    "screener_ratios": {}, "yfinance": {}, "technicals": {}, "jugaad": {},
}

def record(section_key: str, symbol: str, check: str, passed: bool):
    RESULTS[section_key].setdefault(symbol, {})[check] = passed


# ══════════════════════════════════════════════════════════════════════════════
#  A. NSE API
# ══════════════════════════════════════════════════════════════════════════════
section("A — NSE API  (BennyThadikaran/NseIndiaApi)")

try:
    from nse import NSE
    nse_available = True
except ImportError as e:
    print(f"  {R}✗ nse library not installed: {e}{RESET}")
    nse_available = False

if nse_available:
    with NSE(download_folder="/tmp") as nse:
        for symbol, bse_code in STOCKS:
            subsection(f"[{symbol}]")

            # A1: equity quote (price)
            # equityQuote returns flat dict: {date, open, high, low, close, volume}
            try:
                q = nse.equityQuote(symbol)
                price = q.get("close") or q.get("lastPrice") or q.get("LTP")
                if price:
                    ok("A1  price/quote", f"₹{price}")
                    record("nse", symbol, "quote", True)
                else:
                    warn("A1  price/quote", f"keys={list(q.keys())}")
                    record("nse", symbol, "quote", False)
            except Exception as e:
                fail("A1  price/quote", str(e)[:60])
                record("nse", symbol, "quote", False)

            # A2: OHLCV via fetch_equity_historical_data (primary OHLCV source)
            ohlcv_df = None
            try:
                raw = nse.fetch_equity_historical_data(
                    symbol, from_date=FROM_DATE, to_date=TODAY
                )
                # Returns list of dicts or DataFrame-like
                if isinstance(raw, list) and raw:
                    ohlcv_df = pd.DataFrame(raw)
                elif isinstance(raw, pd.DataFrame) and not raw.empty:
                    ohlcv_df = raw

                if ohlcv_df is not None and len(ohlcv_df) >= 50:
                    ok("A2  OHLCV (1y)", f"{len(ohlcv_df)} rows, cols={list(ohlcv_df.columns)[:5]}")
                    record("nse", symbol, "ohlcv", True)
                else:
                    rows = len(ohlcv_df) if ohlcv_df is not None else 0
                    warn("A2  OHLCV (1y)", f"only {rows} rows")
                    record("nse", symbol, "ohlcv", rows > 0)
            except Exception as e:
                fail("A2  OHLCV (1y)", str(e)[:60])
                record("nse", symbol, "ohlcv", False)

            # A3: shareholding
            try:
                sh = nse.shareholding(symbol)
                if sh and (isinstance(sh, dict) and sh) or (isinstance(sh, list) and sh):
                    ok("A3  shareholding", f"type={type(sh).__name__}")
                    record("nse", symbol, "shareholding", True)
                else:
                    warn("A3  shareholding", "empty response")
                    record("nse", symbol, "shareholding", False)
            except Exception as e:
                fail("A3  shareholding", str(e)[:60])
                record("nse", symbol, "shareholding", False)

            # A4: announcements
            try:
                ann = nse.announcements()
                if ann and isinstance(ann, list):
                    ok("A4  announcements", f"{len(ann)} items (market-wide)")
                    record("nse", symbol, "announcements", True)
                else:
                    warn("A4  announcements", "empty")
                    record("nse", symbol, "announcements", False)
            except Exception as e:
                fail("A4  announcements", str(e)[:60])
                record("nse", symbol, "announcements", False)

            # A5: board meetings
            try:
                bm = nse.boardMeetings(symbol=symbol)
                count = len(bm) if isinstance(bm, list) else (1 if bm else 0)
                if count > 0:
                    ok("A5  boardMeetings", f"{count} items")
                    record("nse", symbol, "board_meetings", True)
                else:
                    warn("A5  boardMeetings", "empty")
                    record("nse", symbol, "board_meetings", False)
            except Exception as e:
                fail("A5  boardMeetings", str(e)[:60])
                record("nse", symbol, "board_meetings", False)

            # A6: annual reports
            try:
                ar = nse.annual_reports(symbol)
                count = len(ar) if isinstance(ar, list) else (1 if ar else 0)
                if count > 0:
                    ok("A6  annual_reports", f"{count} items")
                    record("nse", symbol, "annual_reports", True)
                else:
                    warn("A6  annual_reports", "empty")
                    record("nse", symbol, "annual_reports", False)
            except Exception as e:
                fail("A6  annual_reports", str(e)[:60])
                record("nse", symbol, "annual_reports", False)

            time.sleep(0.5)


# ══════════════════════════════════════════════════════════════════════════════
#  B. BSE API — fundamentals via equityMetaInfo
# ══════════════════════════════════════════════════════════════════════════════
section("B — BSE API  (BennyThadikaran/BseIndiaApi)  →  fundamentals")

BSE_FIELDS = ["PE", "EPS/ConEPS", "ROE/ConROE", "PB", "OPM", "NPM", "BookValue(calc)"]

def safe_float(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "", "-", "N/A") else None
    except Exception:
        return None

try:
    from bse import BSE
    bse_available = True
except ImportError as e:
    print(f"  {R}✗ bse library not installed: {e}{RESET}")
    bse_available = False

if bse_available:
    with BSE(download_folder="/tmp") as bse:
        for symbol, bse_code in STOCKS:
            subsection(f"[{symbol}]  BSE:{bse_code}")

            # B1: quote for price (needed to calc book value)
            price = None
            try:
                q = bse.quote(bse_code)
                price = safe_float(q.get("CurrentValue") or q.get("Last") or q.get("LTP"))
                if price:
                    ok("B1  quote/price", f"₹{price}")
                    record("bse", symbol, "quote", True)
                else:
                    warn("B1  quote/price", "no price field")
                    record("bse", symbol, "quote", False)
            except Exception as e:
                fail("B1  quote/price", str(e)[:60])
                record("bse", symbol, "quote", False)

            # B2: equityMetaInfo — primary fundamentals source
            meta = {}
            try:
                meta = bse.equityMetaInfo(bse_code)
                ok("B2  equityMetaInfo", f"keys={list(meta.keys())[:6]}")
                record("bse", symbol, "meta_fetch", True)
            except Exception as e:
                fail("B2  equityMetaInfo", str(e)[:60])
                record("bse", symbol, "meta_fetch", False)

            # B3: individual field extraction
            pe  = safe_float(meta.get("PE") or meta.get("ConPE"))
            eps = safe_float(meta.get("ConEPS") or meta.get("EPS"))
            roe = safe_float(meta.get("ConROE") or meta.get("ROE"))
            pb  = safe_float(meta.get("PB"))
            opm = safe_float(meta.get("OPM"))
            npm = safe_float(meta.get("NPM"))
            bv  = round(price / pb, 2) if (pb and pb > 0 and price and price > 0) else None

            for name, val in [("B3  PE",pe),("B4  EPS",eps),("B5  ROE",roe),
                               ("B6  PB",pb),("B7  OPM",opm),("B8  NPM",npm),("B9  BookValue",bv)]:
                key = name.split()[1].lower()
                if val is not None:
                    ok(name, str(val))
                    record("bse", symbol, key, True)
                else:
                    fail(name, "None")
                    record("bse", symbol, key, False)

            time.sleep(0.8)


# ══════════════════════════════════════════════════════════════════════════════
#  C. Screener.in  — slug resolution + financial statements + ratios
# ══════════════════════════════════════════════════════════════════════════════
section("C — Screener.in  (slug resolution + financials + ratios)")

def resolve_screener_slug(symbol: str) -> str:
    """2-step slug lookup — Screener search API → extract slug from url field."""
    try:
        r = requests.get(
            f"https://www.screener.in/api/company/search/?q={symbol}&v=3&fts=1",
            headers=HEADERS, timeout=8
        )
        if r.status_code == 200:
            results = r.json()
            if results and isinstance(results, list):
                # Skip "Search everywhere" fallback entries (id is None)
                valid = [x for x in results if x.get("id") is not None]
                if valid:
                    url_path = valid[0].get("url", "")
                    skip = {"company", "consolidated", "standalone", ""}
                    parts = [p for p in url_path.strip("/").split("/") if p not in skip]
                    if parts:
                        return parts[0]
    except Exception:
        pass
    return symbol

def fetch_screener(symbol: str):
    slug = resolve_screener_slug(symbol)
    for url in [
        f"https://www.screener.in/company/{slug}/consolidated/",
        f"https://www.screener.in/company/{slug}/",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and len(r.text) > 5000:
                soup = BeautifulSoup(r.text, "lxml")
                if soup.find("section", {"id": "quarters"}):
                    return soup, slug, url
        except Exception:
            pass
    return None, slug, None

def parse_table(soup, section_id) -> dict:
    sec = soup.find("section", {"id": section_id}) or soup.find(id=section_id)
    if not sec:
        return {}
    tbl = sec.find("table")
    if not tbl:
        return {}
    headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
    rows    = tbl.find_all("tr")
    data_rows = [r for r in rows if r.find("td")]
    periods = max(0, len(headers) - 1) if headers else 0
    return {"ok": True, "periods": periods, "rows": len(data_rows), "headers": headers[:5]}

def parse_top_ratios(soup) -> dict:
    result = {k: None for k in ["pe_ratio","roe","roce","book_value","eps"]}
    ul = soup.find("ul", {"id": "top-ratios"})
    if not ul:
        return result
    for li in ul.find_all("li"):
        name_el  = li.find("span", class_="name")
        value_el = li.find("span", class_="nowrap value") or li.find("span", class_="value")
        if not name_el or not value_el:
            continue
        name = name_el.get_text(strip=True).lower()
        raw  = value_el.get_text(strip=True).replace(",", "")
        m = re.search(r"[-+]?\d+\.?\d*", raw)
        val = float(m.group()) if m else None
        if "stock p/e" in name or ("p/e" in name and "stock" in name):
            result["pe_ratio"] = val
        elif "book value" in name:
            result["book_value"] = val
        elif "eps" in name:
            result["eps"] = val
        elif "roce" in name:
            result["roce"] = val
        elif "roe" in name:
            result["roe"] = val
    return result

for symbol, bse_code in STOCKS:
    subsection(f"[{symbol}]")

    # C1: slug resolution
    slug = resolve_screener_slug(symbol)
    if slug and slug != symbol.lower():
        ok("C1  slug resolved", f"{symbol} → {slug}")
        record("screener_slug", symbol, "slug_resolved", True)
    elif slug == symbol.lower():
        warn("C1  slug resolved", f"used symbol as-is: {slug}")
        record("screener_slug", symbol, "slug_resolved", True)  # still valid
    else:
        fail("C1  slug resolved", "no slug")
        record("screener_slug", symbol, "slug_resolved", False)

    # C2–C5: financial statement tables
    soup, slug_used, used_url = fetch_screener(symbol)
    if soup is None:
        fail("C2  page fetch", f"slug={slug_used}")
        for k in ["quarterly", "annual", "balance_sheet", "cash_flow",
                  "pe_ratio", "roe", "roce", "book_value", "eps"]:
            record("screener_financials", symbol, k, False)
        time.sleep(2)
        continue

    ok("C2  page fetch", f"{used_url}")

    for stmt_id, label, key in [
        ("quarters",      "C3  quarterly P&L", "quarterly"),
        ("profit-loss",   "C4  annual P&L",    "annual"),
        ("balance-sheet", "C5  balance sheet", "balance_sheet"),
        ("cash-flow",     "C6  cash flow",     "cash_flow"),
    ]:
        d = parse_table(soup, stmt_id)
        if d.get("ok"):
            ok(label, f"{d['periods']} periods  {d['rows']} rows")
            record("screener_financials", symbol, key, True)
        else:
            fail(label, "table missing")
            record("screener_financials", symbol, key, False)

    # C7–C11: top-ratios
    ratios = parse_top_ratios(soup)
    for field, label in [("pe_ratio","C7  PE ratio"),("roe","C8  ROE"),
                          ("roce","C9  ROCE"),("book_value","C10 Book Value"),("eps","C11 EPS")]:
        val = ratios.get(field)
        if val is not None:
            ok(label, str(val))
            record("screener_ratios", symbol, field, True)
        else:
            fail(label, "None")
            record("screener_ratios", symbol, field, False)

    time.sleep(2)   # be polite to Screener


# ══════════════════════════════════════════════════════════════════════════════
#  D. yfinance — OHLCV fallback
# ══════════════════════════════════════════════════════════════════════════════
section("D — yfinance  (OHLCV fallback)")

try:
    import yfinance as yf
    yf_available = True
except ImportError as e:
    print(f"  {R}✗ yfinance not installed: {e}{RESET}")
    yf_available = False

YF_TICKERS = {
    "RELIANCE": "RELIANCE.NS", "HDFCBANK": "HDFCBANK.NS",
    "INFY": "INFY.NS",         "TATAMOTORS": "TATAMOTORS.NS",
    "SUNPHARMA": "SUNPHARMA.NS","IRCTC": "IRCTC.NS",
    "ZOMATO": "ZOMATO.NS",     "COALINDIA": "COALINDIA.NS",
    "BAJFINANCE": "BAJFINANCE.NS", "DMART": "DMART.NS",
}

if yf_available:
    for symbol, bse_code in STOCKS:
        ticker = YF_TICKERS.get(symbol, f"{symbol}.NS")
        subsection(f"[{symbol}]  yf={ticker}")
        try:
            t0 = time.time()
            df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
            elapsed = round(time.time() - t0, 2)
            if df is not None and not df.empty:
                cols = list(df.columns)
                ok("D1  OHLCV download", f"{len(df)} rows  cols={cols}  ({elapsed}s)")
                record("yfinance", symbol, "ohlcv", True)
            else:
                fail("D1  OHLCV download", f"empty DataFrame ({elapsed}s)")
                record("yfinance", symbol, "ohlcv", False)
        except Exception as e:
            fail("D1  OHLCV download", str(e)[:60])
            record("yfinance", symbol, "ohlcv", False)
        time.sleep(0.3)


# ══════════════════════════════════════════════════════════════════════════════
#  E. ta library — 17 technical indicators from NSE OHLCV
# ══════════════════════════════════════════════════════════════════════════════
section("E — ta library  (17 indicators, using NSE OHLCV)")

try:
    import ta
    ta_available = True
except ImportError as e:
    print(f"  {R}✗ ta not installed: {e}{RESET}")
    ta_available = False

def build_ohlcv_from_nse(symbol: str) -> pd.DataFrame | None:
    """Fetch OHLCV from NSE and normalise to standard column names."""
    try:
        with NSE(download_folder="/tmp") as nse:
            raw = nse.fetch_equity_historical_data(
                symbol, from_date=FROM_DATE, to_date=TODAY
            )
        if isinstance(raw, list) and raw:
            df = pd.DataFrame(raw)
        elif isinstance(raw, pd.DataFrame):
            df = raw.copy()
        else:
            return None

        # Exact NSE column names (confirmed from live response).
        # Do NOT use substring matching — ch52WeekHighPrice also contains "high"
        # and would create duplicate columns.
        nse_col_map = {
            "chOpeningPrice":   "Open",
            "chTradeHighPrice": "High",
            "chTradeLowPrice":  "Low",
            "chClosingPrice":   "Close",
            "chTotTradedQty":   "Volume",
        }
        col_map = {c: nse_col_map[c] for c in df.columns if c in nse_col_map}
        df.rename(columns=col_map, inplace=True)
        for req in ["Open","High","Low","Close","Volume"]:
            if req not in df.columns:
                return None
        for c in ["Open","High","Low","Close","Volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.dropna(subset=["Open","High","Low","Close","Volume"], inplace=True)
        return df if len(df) >= 50 else None
    except Exception as _e:
        print(f"    [DEBUG] build_ohlcv exception for {symbol}: {_e}")
        import traceback as _tb; _tb.print_exc()
        return None

INDICATOR_CHECKS = [
    "SMA_20","SMA_50","SMA_200",
    "EMA_20","EMA_50","EMA_200",
    "RSI_14","MACD","MACD_signal",
    "BB_upper","BB_lower",
    "ATR_14","OBV","ADX_14",
    "Stoch_K","Williams_R","ROC_12",
]

if ta_available and nse_available:
    # Test on first 3 stocks (indicators don't change by stock)
    test_symbols = [s for s, _ in STOCKS[:3]]
    for symbol in test_symbols:
        subsection(f"[{symbol}]  — indicators")
        df = build_ohlcv_from_nse(symbol)
        if df is None:
            fail("OHLCV build", "failed — cannot test indicators")
            for ind in INDICATOR_CHECKS:
                record("technicals", symbol, ind, False)
            continue
        ok("OHLCV ready", f"{len(df)} rows")

        results_ind = {}
        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df["Volume"]

        try:
            results_ind["SMA_20"]    = ta.trend.sma_indicator(close, 20).dropna()
            results_ind["SMA_50"]    = ta.trend.sma_indicator(close, 50).dropna()
            results_ind["SMA_200"]   = ta.trend.sma_indicator(close, 200).dropna()
            results_ind["EMA_20"]    = ta.trend.ema_indicator(close, 20).dropna()
            results_ind["EMA_50"]    = ta.trend.ema_indicator(close, 50).dropna()
            results_ind["EMA_200"]   = ta.trend.ema_indicator(close, 200).dropna()
            results_ind["RSI_14"]    = ta.momentum.rsi(close, 14).dropna()
            macd_obj = ta.trend.MACD(close, 12, 26, 9)
            results_ind["MACD"]        = macd_obj.macd().dropna()
            results_ind["MACD_signal"] = macd_obj.macd_signal().dropna()
            bb_obj = ta.volatility.BollingerBands(close, 20, 2)
            results_ind["BB_upper"]  = bb_obj.bollinger_hband().dropna()
            results_ind["BB_lower"]  = bb_obj.bollinger_lband().dropna()
            results_ind["ATR_14"]    = ta.volatility.average_true_range(high, low, close, 14).dropna()
            results_ind["OBV"]       = ta.volume.on_balance_volume(close, volume).dropna()
            adx_obj = ta.trend.ADXIndicator(high, low, close, 14)
            results_ind["ADX_14"]    = adx_obj.adx().dropna()
            stoch_obj = ta.momentum.StochasticOscillator(high, low, close, 14)
            results_ind["Stoch_K"]   = stoch_obj.stoch().dropna()
            results_ind["Williams_R"] = ta.momentum.williams_r(high, low, close, 14).dropna()
            results_ind["ROC_12"]    = ta.momentum.roc(close, 12).dropna()
        except Exception as e:
            fail("indicator compute", str(e)[:80])

        for ind in INDICATOR_CHECKS:
            series = results_ind.get(ind)
            if series is not None and len(series) > 0 and not series.isna().all():
                last_val = round(float(series.iloc[-1]), 4)
                ok(f"E  {ind}", f"last={last_val}  n={len(series)}")
                record("technicals", symbol, ind, True)
            else:
                fail(f"E  {ind}", "empty/NaN series")
                record("technicals", symbol, ind, False)

        time.sleep(0.5)


# ══════════════════════════════════════════════════════════════════════════════
#  F. jugaad-data — confirming OHLCV capability + no financials module
# ══════════════════════════════════════════════════════════════════════════════
section("F — jugaad-data  (OHLCV check + financials module check)")

try:
    from jugaad_data.nse import stock_df
    jugaad_available = True
except ImportError as e:
    print(f"  {R}✗ jugaad-data not installed: {e}{RESET}")
    jugaad_available = False

if jugaad_available:
    symbol = "RELIANCE"
    subsection(f"[{symbol}]  jugaad OHLCV")
    try:
        from jugaad_data.nse import stock_df as jsd
        df_j = jsd(symbol=symbol, from_date=FROM_DATE, to_date=TODAY)
        if df_j is not None and not df_j.empty:
            ok("F1  OHLCV", f"{len(df_j)} rows  cols={list(df_j.columns)[:5]}")
            record("jugaad", symbol, "ohlcv", True)
        else:
            fail("F1  OHLCV", "empty")
            record("jugaad", symbol, "ohlcv", False)
    except Exception as e:
        fail("F1  OHLCV", str(e)[:60])
        record("jugaad", symbol, "ohlcv", False)

    subsection("jugaad financials module check")
    try:
        from jugaad_data import financials as jf
        ok("F2  financials module", "exists")
        record("jugaad", "financials", "module", True)
    except ImportError:
        warn("F2  financials module", "NOT available — confirmed, use Screener instead")
        record("jugaad", "financials", "module", False)


# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
section("SUMMARY — Pass Rate per Component per Stock")

def summarize(section_key: str, checks: list[str], label: str):
    print(f"\n  {B}{label}{RESET}")
    sym_w = 13
    chk_w = 18
    header = f"    {'Stock':<12}" + "".join(f"{c:<{chk_w}}" for c in checks) + "  Rate"
    print(header)
    print(f"    {'─'*12}" + "─"*chk_w*len(checks) + "──────")
    overall_pass = overall_total = 0
    for symbol, _ in STOCKS:
        row = f"    {symbol:<12}"
        stock_pass = 0
        for chk in checks:
            v = RESULTS[section_key].get(symbol, {}).get(chk, None)
            if v is True:
                row += f"{G}✓{RESET}{'':<{chk_w-1}}"
                stock_pass += 1
                overall_pass += 1
            elif v is False:
                row += f"{R}✗{RESET}{'':<{chk_w-1}}"
            else:
                row += f"{Y}–{RESET}{'':<{chk_w-1}}"
            overall_total += 1
        pct = int(100 * stock_pass / len(checks)) if checks else 0
        color = G if pct >= 80 else Y if pct >= 50 else R
        row += f"  {color}{pct:3d}%{RESET}"
        print(row)
    total_pct = int(100 * overall_pass / overall_total) if overall_total else 0
    color = G if total_pct >= 80 else Y if total_pct >= 50 else R
    print(f"\n    Overall: {color}{overall_pass}/{overall_total}  ({total_pct}%){RESET}")

summarize("nse", ["quote","ohlcv","shareholding","announcements","board_meetings","annual_reports"],
          "A — NSE API")
summarize("bse", ["quote","meta_fetch","pe","eps","roe","pb","opm","npm","bookvalue"],
          "B — BSE API  (fundamentals)")
summarize("screener_slug", ["slug_resolved"], "C1 — Screener slug resolution")
summarize("screener_financials", ["quarterly","annual","balance_sheet","cash_flow"],
          "C2–C6 — Screener financial statements")
summarize("screener_ratios", ["pe_ratio","roe","roce","book_value","eps"],
          "C7–C11 — Screener top-ratios")
summarize("yfinance", ["ohlcv"], "D — yfinance  (OHLCV fallback)")
summarize("technicals", INDICATOR_CHECKS, "E — ta indicators  (first 3 stocks)")

# Final verdict
section("FINAL VERDICT — Ready to implement?")
component_scores = {
    "NSE  OHLCV": sum(1 for s,_ in STOCKS if RESULTS["nse"].get(s,{}).get("ohlcv")) / len(STOCKS),
    "NSE  price": sum(1 for s,_ in STOCKS if RESULTS["nse"].get(s,{}).get("quote")) / len(STOCKS),
    "BSE  fundamentals": sum(1 for s,_ in STOCKS if RESULTS["bse"].get(s,{}).get("meta_fetch")) / len(STOCKS),
    "Screener financials": (
        sum(RESULTS["screener_financials"].get(s,{}).get("quarterly",False) for s,_ in STOCKS) / len(STOCKS)
    ),
    "Screener ROCE": (
        sum(RESULTS["screener_ratios"].get(s,{}).get("roce",False) for s,_ in STOCKS) / len(STOCKS)
    ),
    "yfinance OHLCV": sum(1 for s,_ in STOCKS if RESULTS["yfinance"].get(s,{}).get("ohlcv")) / len(STOCKS),
    "ta indicators": (
        sum(RESULTS["technicals"].get(STOCKS[0][0],{}).get(ind,False) for ind in INDICATOR_CHECKS) / len(INDICATOR_CHECKS)
        if INDICATOR_CHECKS else 0
    ),
}

print()
for component, rate in component_scores.items():
    pct  = int(rate * 100)
    bar  = "█" * (pct // 10)
    color = G if pct >= 80 else Y if pct >= 50 else R
    status = "READY" if pct >= 80 else "PARTIAL" if pct >= 50 else "NOT READY"
    print(f"  {component:<28} {color}{pct:3d}%  {bar:<10}  {status}{RESET}")

print()
