"""
test_target_stocks.py — Verify all data components for 3 target stocks.

Stocks:
  UNIECOM  | BSE:544227 | INE00U401027
  TMPV     | BSE:500570 | INE155A01022
  QUESTCAP | BSE:500069 | INE418C01012

Tests every waterfall level for each component:
  A. Price/Quote
  B. OHLCV
  C. BSE Fundamentals
  D. Screener slug + financials + ratios
  E. Technical indicators (ta library)
  F. Announcements
  G. Shareholding

Run: conda run -n datatest python backend/tests/research/test_target_stocks.py
"""

import time, sys, re, requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import date, timedelta

G="\033[92m"; R="\033[91m"; Y="\033[93m"; C="\033[96m"; B="\033[1m"; RESET="\033[0m"

def ok(label, note=""): print(f"    {G}✓{RESET} {label:<34}{Y}({note}){RESET}" if note else f"    {G}✓{RESET} {label}")
def fail(label, note=""): print(f"    {R}✗{RESET} {label:<34}{R}({note}){RESET}" if note else f"    {R}✗{RESET} {label}")
def warn(label, note=""): print(f"    {Y}~{RESET} {label:<34}{Y}({note}){RESET}" if note else f"    {Y}~{RESET} {label}")
def section(t): print(f"\n{B}{C}{'═'*70}{RESET}\n{B}{C}  {t}{RESET}\n{B}{C}{'═'*70}{RESET}")
def sub(t): print(f"\n  {B}[{t}]{RESET}\n  {'─'*60}")

STOCKS = [
    ("UNIECOM",  "544227", "INE00U401027"),
    ("TMPV",     "500570", "INE155A01022"),
    ("QUESTCAP", "500069", "INE418C01012"),
]

TODAY     = date.today()
FROM_DATE = TODAY - timedelta(days=365)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

NSE_OHLCV_COLS = {
    "chOpeningPrice":"Open","chTradeHighPrice":"High",
    "chTradeLowPrice":"Low","chClosingPrice":"Close","chTotTradedQty":"Volume",
}

def safe_float(v):
    try: return float(str(v).replace(",","")) if v not in (None,"","-","N/A") else None
    except: return None

# ── NSE client ─────────────────────────────────────────────────────────────────
from nse import NSE
from bse import BSE

# ── Screener helpers ───────────────────────────────────────────────────────────
def resolve_slug(symbol):
    try:
        r = requests.get(f"https://www.screener.in/api/company/search/?q={symbol}&v=3&fts=1",
                         headers=HEADERS, timeout=8)
        if r.status_code == 200:
            valid = [x for x in r.json() if x.get("id") is not None]
            if valid:
                url = valid[0].get("url","")
                skip = {"company","consolidated","standalone",""}
                parts = [p for p in url.strip("/").split("/") if p not in skip]
                if parts: return parts[0], valid[0].get("id"), url
    except: pass
    return symbol, None, None

_MONTH_MAP = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

def _most_recent_period(soup):
    """Return (year, month) of most recent column in #quarters, or (0,0)."""
    sec = soup.find("section", {"id": "quarters"})
    if not sec: return (0, 0)
    tbl = sec.find("table")
    if not tbl: return (0, 0)
    thead = tbl.find("thead")
    if not thead: return (0, 0)
    tr = thead.find("tr")
    if not tr: return (0, 0)
    headers = [th.get_text(strip=True) for th in tr.find_all("th")[1:]]
    import datetime as _dt
    for h in headers:
        if "ttm" in h.lower():
            now = _dt.date.today()
            return (now.year, now.month)
        m = re.match(r"([a-zA-Z]{3})\s+(\d{4})", h)
        if m:
            mo = _MONTH_MAP.get(m.group(1).lower())
            if mo:
                return (int(m.group(2)), mo)
    return (0, 0)

def fetch_screener(slug):
    """Fetch both consolidated and standalone; return the page with more recent data."""
    candidates = []
    for url in [f"https://www.screener.in/company/{slug}/consolidated/",
                f"https://www.screener.in/company/{slug}/"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and len(r.text) > 3000:
                soup = BeautifulSoup(r.text, "lxml")
                if soup.find("section", {"id": "quarters"}):
                    period = _most_recent_period(soup)
                    candidates.append((soup, url, period))
                    print(f"  screener candidate: {url} → most recent: {period}")
        except: pass
    if not candidates:
        return None, None
    best = max(candidates, key=lambda c: c[2])
    return best[0], best[1]

def parse_table(soup, sid):
    sec = soup.find("section", {"id": sid}) or soup.find(id=sid)
    if not sec: return {}
    tbl = sec.find("table")
    if not tbl: return {}
    hdrs = [th.get_text(strip=True) for th in tbl.find_all("th")]
    rows = [r for r in tbl.find_all("tr") if r.find("td")]
    return {"ok":True, "periods": max(0,len(hdrs)-1), "rows":len(rows), "headers":hdrs[:5]}

def parse_ratios(soup):
    result = {k: None for k in ["pe","roe","roce","bv","eps"]}
    ul = soup.find("ul", {"id":"top-ratios"})
    if not ul: return result
    for li in ul.find_all("li"):
        ne = li.find("span", class_="name")
        ve = li.find("span", class_="nowrap value") or li.find("span", class_="value")
        if not ne or not ve: continue
        name = ne.get_text(strip=True).lower()
        raw  = ve.get_text(strip=True).replace(",","")
        m = re.search(r"[-+]?\d+\.?\d*", raw)
        val = float(m.group()) if m else None
        if "stock p/e" in name or ("p/e" in name and "stock" in name): result["pe"] = val
        elif "book value" in name: result["bv"] = val
        elif "eps" in name: result["eps"] = val
        elif "roce" in name: result["roce"] = val
        elif "roe" in name: result["roe"] = val
    return result

# ══════════════════════════════════════════════════════════════════════════════
section("TARGET STOCK TESTS — 3 Stocks")

all_results = {}

for symbol, bse_code, isin in STOCKS:
    sub(f"{symbol}  BSE:{bse_code}  ISIN:{isin}")
    r = {}

    # ── A. Price ────────────────────────────────────────────────────────────────
    print(f"\n  {B}A — Price/Quote{RESET}")
    price = None

    # A-L1: NSE
    try:
        with NSE(download_folder="/tmp") as nse:
            q = nse.equityQuote(symbol)
        p = q.get("close") or q.get("lastPrice") or q.get("LTP")
        if p:
            price = float(p)
            ok("A1 NSE equityQuote", f"₹{price}")
            r["price_source"] = "NSE L1"
        else:
            warn("A1 NSE equityQuote", f"returned but no price — keys={list(q.keys())[:6]}")
    except Exception as e:
        fail("A1 NSE equityQuote", str(e)[:60])

    # A-L2: BSE
    if price is None:
        try:
            with BSE(download_folder="/tmp") as bse:
                q = bse.quote(bse_code)
            p = safe_float(q.get("CurrentValue") or q.get("Last") or q.get("LTP"))
            if p:
                price = p
                ok("A2 BSE quote", f"₹{price}")
                r["price_source"] = "BSE L2"
            else:
                warn("A2 BSE quote", f"keys={list(q.keys())[:6]}")
        except Exception as e:
            fail("A2 BSE quote", str(e)[:60])

    # A-L3: yfinance
    if price is None:
        try:
            import yfinance as yf
            for ticker in [f"{symbol}.NS", f"{symbol}.BO", f"{bse_code}.BO"]:
                try:
                    info = yf.Ticker(ticker).fast_info
                    p = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                    if p and p > 0:
                        price = float(p)
                        ok(f"A3 yfinance {ticker}", f"₹{price}")
                        r["price_source"] = f"yfinance L3 ({ticker})"
                        break
                except: pass
            if price is None:
                fail("A3 yfinance all tickers", "no price")
        except Exception as e:
            fail("A3 yfinance", str(e)[:60])

    r["price"] = price

    # ── B. OHLCV ────────────────────────────────────────────────────────────────
    print(f"\n  {B}B — OHLCV (1-year daily){RESET}")
    ohlcv_df = None

    # B-L1: NSE library
    try:
        with NSE(download_folder="/tmp") as nse:
            raw = nse.fetch_equity_historical_data(symbol, from_date=FROM_DATE, to_date=TODAY)
        if isinstance(raw, list) and raw:
            df = pd.DataFrame(raw)
        elif isinstance(raw, pd.DataFrame) and not raw.empty:
            df = raw.copy()
        else:
            df = pd.DataFrame()

        if not df.empty:
            col_map = {c: NSE_OHLCV_COLS[c] for c in df.columns if c in NSE_OHLCV_COLS}
            df.rename(columns=col_map, inplace=True)
            for c in ["Open","High","Low","Close","Volume"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df.dropna(subset=[c for c in ["Open","High","Low","Close","Volume"] if c in df.columns], inplace=True)

        if not df.empty and len(df) >= 20:
            ohlcv_df = df
            ok("B1 NSE fetch_equity_historical_data", f"{len(df)} rows")
            r["ohlcv_source"] = "NSE L1"
        else:
            warn("B1 NSE", f"{len(df)} rows — insufficient" if not df.empty else "empty response")
    except Exception as e:
        fail("B1 NSE", str(e)[:60])

    # B-L2: yfinance .NS
    if ohlcv_df is None:
        import yfinance as yf
        for ticker_suffix, label in [(f"{symbol}.NS","L2 .NS"), (f"{symbol}.BO","L3 .BO"), (f"{bse_code}.BO","L4 BSE code.BO")]:
            try:
                df = yf.download(ticker_suffix, period="1y", interval="1d", progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if df is not None and not df.empty and len(df) >= 20:
                    ohlcv_df = df
                    ok(f"B yfinance {ticker_suffix}", f"{len(df)} rows  {label}")
                    r["ohlcv_source"] = f"yfinance {label} ({ticker_suffix})"
                    break
                else:
                    warn(f"B yfinance {ticker_suffix}", f"{len(df) if df is not None else 0} rows")
            except Exception as e:
                fail(f"B yfinance {ticker_suffix}", str(e)[:60])

    if ohlcv_df is None:
        fail("B OHLCV", "ALL LEVELS FAILED — no candle data")
    r["ohlcv_rows"] = len(ohlcv_df) if ohlcv_df is not None else 0

    # ── C. BSE Fundamentals ────────────────────────────────────────────────────
    print(f"\n  {B}C — BSE Fundamentals (equityMetaInfo){RESET}")
    meta = {}
    try:
        with BSE(download_folder="/tmp") as bse:
            meta = bse.equityMetaInfo(bse_code)
        ok("C1 equityMetaInfo", f"keys={list(meta.keys())[:6]}")
    except Exception as e:
        fail("C1 equityMetaInfo", str(e)[:60])

    fields = {
        "PE":  safe_float(meta.get("PE") or meta.get("ConPE")),
        "EPS": safe_float(meta.get("ConEPS") or meta.get("EPS")),
        "ROE": safe_float(meta.get("ConROE") or meta.get("ROE")),
        "PB":  safe_float(meta.get("PB")),
        "OPM": safe_float(meta.get("OPM")),
        "NPM": safe_float(meta.get("NPM")),
    }
    pb  = fields["PB"]
    bv  = round(price / pb, 2) if (pb and pb > 0 and price and price > 0) else None
    fields["BookValue"] = bv

    for fname, fval in fields.items():
        if fval is not None:
            ok(f"C  {fname}", str(fval))
        else:
            fail(f"C  {fname}", "None")
    r["bse_fields"] = {k: v for k, v in fields.items() if v is not None}

    # ── D. Screener ────────────────────────────────────────────────────────────
    print(f"\n  {B}D — Screener.in (slug → financials + ratios){RESET}")
    slug, company_id, slug_url = resolve_slug(symbol)
    print(f"    slug resolved: {symbol} → {slug}  (url={slug_url})")

    soup, used_url = fetch_screener(slug)
    if soup is None:
        fail("D2 page fetch", f"failed for slug={slug}")
        r["screener"] = "failed"
    else:
        ok("D2 page fetch", used_url)
        for sid, label in [("quarters","quarterly P&L"),("profit-loss","annual P&L"),
                            ("balance-sheet","balance sheet"),("cash-flow","cash flow")]:
            d = parse_table(soup, sid)
            if d.get("ok"): ok(f"D  {label}", f"{d['periods']} periods  {d['rows']} rows")
            else: fail(f"D  {label}", "missing")
        ratios = parse_ratios(soup)
        for rname, rval in ratios.items():
            if rval is not None: ok(f"D  Screener {rname.upper()}", str(rval))
            else: warn(f"D  Screener {rname.upper()}", "not in top-ratios")
        r["screener"] = "ok"

    time.sleep(2)

    # ── E. Technical Indicators ────────────────────────────────────────────────
    print(f"\n  {B}E — Technical Indicators (ta library){RESET}")
    if ohlcv_df is not None and all(c in ohlcv_df.columns for c in ["Open","High","Low","Close","Volume"]):
        try:
            import ta
            close  = ohlcv_df["Close"]
            high   = ohlcv_df["High"]
            low    = ohlcv_df["Low"]
            volume = ohlcv_df["Volume"]
            n = len(close)
            indicators = {}

            if n >= 20:
                indicators["SMA_20"]   = ta.trend.sma_indicator(close, 20).dropna()
                indicators["EMA_20"]   = ta.trend.ema_indicator(close, 20).dropna()
                indicators["RSI_14"]   = ta.momentum.rsi(close, 14).dropna()
                bb = ta.volatility.BollingerBands(close, 20, 2)
                indicators["BB_upper"] = bb.bollinger_hband().dropna()
                indicators["BB_lower"] = bb.bollinger_lband().dropna()
                indicators["ATR_14"]   = ta.volatility.average_true_range(high,low,close,14).dropna()
                indicators["OBV"]      = ta.volume.on_balance_volume(close,volume).dropna()

            if n >= 26:
                macd_obj = ta.trend.MACD(close, 12, 26, 9)
                indicators["MACD"]        = macd_obj.macd().dropna()
                indicators["MACD_signal"] = macd_obj.macd_signal().dropna()
                indicators["ADX_14"]      = ta.trend.ADXIndicator(high,low,close,14).adx().dropna()
                indicators["Stoch_K"]     = ta.momentum.StochasticOscillator(high,low,close,14).stoch().dropna()
                indicators["Williams_R"]  = ta.momentum.williams_r(high,low,close,14).dropna()
                indicators["ROC_12"]      = ta.momentum.roc(close,12).dropna()

            if n >= 50:
                indicators["SMA_50"]   = ta.trend.sma_indicator(close, 50).dropna()
                indicators["EMA_50"]   = ta.trend.ema_indicator(close, 50).dropna()

            if n >= 200:
                indicators["SMA_200"]  = ta.trend.sma_indicator(close, 200).dropna()
                indicators["EMA_200"]  = ta.trend.ema_indicator(close, 200).dropna()
            else:
                warn("SMA_200 / EMA_200", f"skipped — only {n} rows (need 200)")

            ok_count = 0
            for iname, series in indicators.items():
                if series is not None and len(series) > 0 and not series.isna().all():
                    ok(f"E  {iname}", f"last={round(float(series.iloc[-1]),2)}  n={len(series)}")
                    ok_count += 1
                else:
                    fail(f"E  {iname}", "empty")

            r["technicals_ok"] = ok_count
            print(f"    {G}→ {ok_count}/{len(indicators)} indicators computed{RESET}")
        except Exception as e:
            fail("E indicator compute", str(e)[:80])
            r["technicals_ok"] = 0
    else:
        warn("E indicators", f"SKIPPED — no valid OHLCV (rows={r['ohlcv_rows']})")
        r["technicals_ok"] = 0

    # ── F. Announcements ──────────────────────────────────────────────────────
    print(f"\n  {B}F — Announcements{RESET}")
    # F-L1: NSE market-wide filter
    try:
        with NSE(download_folder="/tmp") as nse:
            ann = nse.announcements()
        if isinstance(ann, list):
            filtered = [a for a in ann if str(a.get("symbol","")).upper() == symbol.upper()
                        or str(a.get("sm_isin","")) == isin]
            ok("F1 NSE announcements", f"{len(ann)} market-wide → {len(filtered)} for {symbol}")
            r["announcements_nse"] = len(filtered)
        else:
            warn("F1 NSE announcements", f"unexpected type: {type(ann)}")
    except Exception as e:
        fail("F1 NSE announcements", str(e)[:60])

    # F-L2: BSE per-stock
    try:
        with BSE(download_folder="/tmp") as bse:
            bann = bse.announcements(scripcode=bse_code)
        count = len(bann) if isinstance(bann, list) else (1 if bann else 0)
        ok("F2 BSE announcements", f"{count} items")
        r["announcements_bse"] = count
    except Exception as e:
        fail("F2 BSE announcements", str(e)[:60])

    # ── G. Shareholding ────────────────────────────────────────────────────────
    print(f"\n  {B}G — Shareholding{RESET}")
    try:
        with NSE(download_folder="/tmp") as nse:
            sh = nse.shareholding(symbol)
        if sh and (isinstance(sh, list) and len(sh) > 0) or (isinstance(sh, dict) and sh):
            ok("G1 NSE shareholding", f"type={type(sh).__name__}  len={len(sh) if hasattr(sh,'__len__') else 1}")
            r["shareholding"] = "NSE L1"
        else:
            warn("G1 NSE shareholding", "empty — trying Screener")
            r["shareholding"] = "empty"
    except Exception as e:
        fail("G1 NSE shareholding", str(e)[:60])
        r["shareholding"] = "failed"

    all_results[symbol] = r
    print()
    time.sleep(1)


# ══════════════════════════════════════════════════════════════════════════════
section("SUMMARY")

for symbol, bse_code, isin in STOCKS:
    r = all_results.get(symbol, {})
    print(f"\n  {B}{symbol}{RESET}  BSE:{bse_code}")
    rows = [
        ("Price",          r.get("price"), r.get("price_source","–")),
        ("OHLCV rows",     r.get("ohlcv_rows"), r.get("ohlcv_source","–")),
        ("BSE fields",     len(r.get("bse_fields",{})), str(list(r.get("bse_fields",{}).keys()))),
        ("Screener",       r.get("screener","–"), ""),
        ("Indicators",     r.get("technicals_ok","–"), ""),
        ("Announce NSE",   r.get("announcements_nse","–"), ""),
        ("Announce BSE",   r.get("announcements_bse","–"), ""),
        ("Shareholding",   r.get("shareholding","–"), ""),
    ]
    for label, val, note in rows:
        is_ok = val not in (None, 0, "–", "failed", "empty") and val != False
        col = G if is_ok else (Y if val == 0 else R)
        print(f"    {col}{label:<18}{RESET} {str(val):<10}  {note[:50]}")
