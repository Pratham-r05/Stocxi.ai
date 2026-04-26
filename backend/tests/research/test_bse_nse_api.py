"""
test_bse_nse_api.py — Standalone test for BennyThadikaran's BSE + NSE libraries.

Tests every method relevant to Stocxi's data needs:
  - Price & fundamentals
  - OHLCV / historical data
  - Corporate announcements
  - Shareholding
  - Annual reports / results
  - MF / institutional holdings (via delivery/bhavcopy)
  - Board meetings

Run with:
    conda run -n datatest python test_bse_nse_api.py

Test symbol: RELIANCE (NSE) / BSE code 500325
"""

import json
import traceback
from datetime import date, timedelta

# ── colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(label, note=""):
    print(f"  {GREEN}✓{RESET} {label}" + (f"  {YELLOW}({note}){RESET}" if note else ""))

def fail(label, err):
    print(f"  {RED}✗{RESET} {label}  {RED}{err}{RESET}")

def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

def peek(data, n=3):
    """Return a short preview of any data structure."""
    if isinstance(data, dict):
        keys = list(data.keys())[:n]
        return "{" + ", ".join(f"{k}: ..." for k in keys) + ("..." if len(data) > n else "") + "}"
    if isinstance(data, list):
        return f"[{len(data)} items]  first: {json.dumps(data[0], default=str)[:120]}" if data else "[]"
    return str(data)[:200]

NSE_SYMBOL = "RELIANCE"
BSE_CODE   = "500325"
TODAY      = date.today()
FROM_DATE  = TODAY - timedelta(days=60)

results = {}   # label → True/False

# ══════════════════════════════════════════════════════════════════════════════
#  NSE TESTS
# ══════════════════════════════════════════════════════════════════════════════
section("NSE — BennyThadikaran/NseIndiaApi")

from nse import NSE

with NSE(download_folder="/tmp") as nse:

    # 1. Market status
    try:
        s = nse.status()
        ok("status()", peek(s))
        results["NSE.status"] = True
    except Exception as e:
        fail("status()", e); results["NSE.status"] = False

    # 2. Equity quote (current price + fundamentals metadata)
    try:
        q = nse.equityQuote(NSE_SYMBOL)
        price = q.get("priceInfo", {}).get("lastPrice") or q.get("lastPrice")
        ok("equityQuote(RELIANCE)", f"lastPrice={price}")
        results["NSE.equityQuote"] = True
    except Exception as e:
        fail("equityQuote(RELIANCE)", e); results["NSE.equityQuote"] = False

    # 3. Equity meta info
    try:
        m = nse.equityMetaInfo(NSE_SYMBOL)
        ok("equityMetaInfo(RELIANCE)", peek(m))
        results["NSE.equityMetaInfo"] = True
    except Exception as e:
        fail("equityMetaInfo(RELIANCE)", e); results["NSE.equityMetaInfo"] = False

    # 4. Historical equity data (OHLCV)
    try:
        h = nse.fetch_equity_historical_data(
            NSE_SYMBOL, from_date=FROM_DATE, to_date=TODAY
        )
        ok("fetch_equity_historical_data(60d)", peek(h))
        results["NSE.fetch_equity_historical_data"] = True
    except Exception as e:
        fail("fetch_equity_historical_data(60d)", e)
        results["NSE.fetch_equity_historical_data"] = False

    # 5. Shareholding
    try:
        sh = nse.shareholding(NSE_SYMBOL)
        ok("shareholding(RELIANCE)", peek(sh))
        results["NSE.shareholding"] = True
    except Exception as e:
        fail("shareholding(RELIANCE)", e); results["NSE.shareholding"] = False

    # 6. Corporate announcements
    try:
        ann = nse.announcements()
        ok("announcements()", peek(ann))
        results["NSE.announcements"] = True
    except Exception as e:
        fail("announcements()", e); results["NSE.announcements"] = False

    # 7. Corporate actions (dividends, splits, bonus)
    try:
        ca = nse.actions(symbol=NSE_SYMBOL)
        ok("actions(RELIANCE)", peek(ca))
        results["NSE.actions"] = True
    except Exception as e:
        fail("actions(RELIANCE)", e); results["NSE.actions"] = False

    # 8. Board meetings
    try:
        bm = nse.boardMeetings(symbol=NSE_SYMBOL)
        ok("boardMeetings(RELIANCE)", peek(bm))
        results["NSE.boardMeetings"] = True
    except Exception as e:
        fail("boardMeetings(RELIANCE)", e); results["NSE.boardMeetings"] = False

    # 9. Annual reports
    try:
        ar = nse.annual_reports(NSE_SYMBOL)
        ok("annual_reports(RELIANCE)", peek(ar))
        results["NSE.annual_reports"] = True
    except Exception as e:
        fail("annual_reports(RELIANCE)", e); results["NSE.annual_reports"] = False

    # 10. Gainers / Losers
    try:
        g = nse.gainers(by="securities")
        ok("gainers()", peek(g))
        results["NSE.gainers"] = True
    except Exception as e:
        fail("gainers()", e); results["NSE.gainers"] = False

    # 11. Advance / Decline
    try:
        ad = nse.advanceDecline()
        ok("advanceDecline()", peek(ad))
        results["NSE.advanceDecline"] = True
    except Exception as e:
        fail("advanceDecline()", e); results["NSE.advanceDecline"] = False

    # 12. Bhavcopy (daily OHLCV dump — useful for batch ops)
    try:
        bv = nse.equityBhavcopy(TODAY - timedelta(days=1))
        ok("equityBhavcopy(yesterday)", f"type={type(bv).__name__}")
        results["NSE.equityBhavcopy"] = True
    except Exception as e:
        fail("equityBhavcopy(yesterday)", e); results["NSE.equityBhavcopy"] = False

    # 13. Delivery bhavcopy
    try:
        db = nse.deliveryBhavcopy(TODAY - timedelta(days=1))
        ok("deliveryBhavcopy(yesterday)", f"type={type(db).__name__}")
        results["NSE.deliveryBhavcopy"] = True
    except Exception as e:
        fail("deliveryBhavcopy(yesterday)", e); results["NSE.deliveryBhavcopy"] = False

    # 14. Block deals
    try:
        bd = nse.blockDeals()
        ok("blockDeals()", peek(bd))
        results["NSE.blockDeals"] = True
    except Exception as e:
        fail("blockDeals()", e); results["NSE.blockDeals"] = False

    # 15. Bulk deals
    try:
        bk = nse.bulkdeals()
        ok("bulkdeals()", peek(bk))
        results["NSE.bulkdeals"] = True
    except Exception as e:
        fail("bulkdeals()", e); results["NSE.bulkdeals"] = False

    # 16. Option chain
    try:
        oc = nse.optionChain(NSE_SYMBOL)
        ok("optionChain(RELIANCE)", peek(oc))
        results["NSE.optionChain"] = True
    except Exception as e:
        fail("optionChain(RELIANCE)", e); results["NSE.optionChain"] = False

    # 17. Holidays
    try:
        hol = nse.holidays()
        ok("holidays()", peek(hol))
        results["NSE.holidays"] = True
    except Exception as e:
        fail("holidays()", e); results["NSE.holidays"] = False

    # 18. List stocks by index (NIFTY 50)
    try:
        idx = nse.listEquityStocksByIndex("NIFTY 50")
        ok("listEquityStocksByIndex(NIFTY 50)", peek(idx))
        results["NSE.listEquityStocksByIndex"] = True
    except Exception as e:
        fail("listEquityStocksByIndex(NIFTY 50)", e)
        results["NSE.listEquityStocksByIndex"] = False

    # 19. Historical VIX
    try:
        vix = nse.fetch_historical_vix_data(FROM_DATE, TODAY)
        ok("fetch_historical_vix_data(60d)", peek(vix))
        results["NSE.fetch_historical_vix_data"] = True
    except Exception as e:
        fail("fetch_historical_vix_data(60d)", e)
        results["NSE.fetch_historical_vix_data"] = False

    # 20. lookup / search
    try:
        lu = nse.lookup("RELIANCE")
        ok("lookup('RELIANCE')", peek(lu))
        results["NSE.lookup"] = True
    except Exception as e:
        fail("lookup('RELIANCE')", e); results["NSE.lookup"] = False

# ══════════════════════════════════════════════════════════════════════════════
#  BSE TESTS
# ══════════════════════════════════════════════════════════════════════════════
section("BSE — BennyThadikaran/BseIndiaApi")

from bse import BSE

with BSE(download_folder="/tmp") as bse:

    # 1. Get scrip code from symbol
    try:
        code = bse.getScripCode(NSE_SYMBOL)
        ok("getScripCode(RELIANCE)", f"code={code}")
        BSE_CODE = str(code) if code else BSE_CODE
        results["BSE.getScripCode"] = True
    except Exception as e:
        fail("getScripCode(RELIANCE)", e); results["BSE.getScripCode"] = False

    # 2. Equity quote (OHLC)
    try:
        q = bse.quote(BSE_CODE)
        ok("quote(500325)", peek(q))
        results["BSE.quote"] = True
    except Exception as e:
        fail("quote(500325)", e); results["BSE.quote"] = False

    # 3. Equity meta info
    try:
        m = bse.equityMetaInfo(BSE_CODE)
        ok("equityMetaInfo(500325)", peek(m))
        results["BSE.equityMetaInfo"] = True
    except Exception as e:
        fail("equityMetaInfo(500325)", e); results["BSE.equityMetaInfo"] = False

    # 4. Trading stats
    try:
        ts = bse.getScripTradingStats(BSE_CODE)
        ok("getScripTradingStats(500325)", peek(ts))
        results["BSE.getScripTradingStats"] = True
    except Exception as e:
        fail("getScripTradingStats(500325)", e); results["BSE.getScripTradingStats"] = False

    # 5. 12-month price + volume
    try:
        pv = bse.equityPriceVolumeT12M(BSE_CODE)
        ok("equityPriceVolumeT12M(500325)", peek(pv))
        results["BSE.equityPriceVolumeT12M"] = True
    except Exception as e:
        fail("equityPriceVolumeT12M(500325)", e); results["BSE.equityPriceVolumeT12M"] = False

    # 6. Weekly high/low
    try:
        whl = bse.quoteWeeklyHL(BSE_CODE)
        ok("quoteWeeklyHL(500325)", peek(whl))
        results["BSE.quoteWeeklyHL"] = True
    except Exception as e:
        fail("quoteWeeklyHL(500325)", e); results["BSE.quoteWeeklyHL"] = False

    # 7. Corporate actions (dividends, splits, bonus, rights)
    try:
        ca = bse.actions(scripcode=int(BSE_CODE))
        ok("actions(500325)", peek(ca))
        results["BSE.actions"] = True
    except Exception as e:
        fail("actions(500325)", e); results["BSE.actions"] = False

    # 8. Corporate announcements
    try:
        ann = bse.announcements(scripcode=BSE_CODE)
        ok("announcements(500325)", peek(ann))
        results["BSE.announcements"] = True
    except Exception as e:
        fail("announcements(500325)", e); results["BSE.announcements"] = False

    # 9. Result calendar (earnings dates)
    try:
        rc = bse.resultCalendar()
        ok("resultCalendar()", peek(rc))
        results["BSE.resultCalendar"] = True
    except Exception as e:
        fail("resultCalendar()", e); results["BSE.resultCalendar"] = False

    # 10. Results snapshot (quarterly numbers)
    try:
        rs = bse.resultsSnapshot(scripcode=BSE_CODE)
        ok("resultsSnapshot(500325)", peek(rs))
        results["BSE.resultsSnapshot"] = True
    except Exception as e:
        fail("resultsSnapshot(500325)", e); results["BSE.resultsSnapshot"] = False

    # 11. Near 52-week high/low
    try:
        n52 = bse.near52WeekHighLow()
        ok("near52WeekHighLow()", peek(n52))
        results["BSE.near52WeekHighLow"] = True
    except Exception as e:
        fail("near52WeekHighLow()", e); results["BSE.near52WeekHighLow"] = False

    # 12. Gainers
    try:
        g = bse.gainers(by="index", name="BSE500")
        ok("gainers(BSE500)", peek(g))
        results["BSE.gainers"] = True
    except Exception as e:
        fail("gainers(BSE500)", e); results["BSE.gainers"] = False

    # 13. Losers
    try:
        lo = bse.losers(by="index", name="BSE500")
        ok("losers(BSE500)", peek(lo))
        results["BSE.losers"] = True
    except Exception as e:
        fail("losers(BSE500)", e); results["BSE.losers"] = False

    # 14. Bhavcopy report (daily OHLCV dump)
    try:
        bv = bse.bhavcopyReport(TODAY - timedelta(days=1))
        ok("bhavcopyReport(yesterday)", f"type={type(bv).__name__}")
        results["BSE.bhavcopyReport"] = True
    except Exception as e:
        fail("bhavcopyReport(yesterday)", e); results["BSE.bhavcopyReport"] = False

    # 15. Delivery report
    try:
        dr = bse.deliveryReport(TODAY - timedelta(days=1))
        ok("deliveryReport(yesterday)", f"type={type(dr).__name__}")
        results["BSE.deliveryReport"] = True
    except Exception as e:
        fail("deliveryReport(yesterday)", e); results["BSE.deliveryReport"] = False

    # 16. List securities
    try:
        ls = bse.listSecurities(segment="equity")
        ok("listSecurities(equity)", peek(ls))
        results["BSE.listSecurities"] = True
    except Exception as e:
        fail("listSecurities(equity)", e); results["BSE.listSecurities"] = False

    # 17. Lookup / search
    try:
        lu = bse.lookup("RELIANCE")
        ok("lookup('RELIANCE')", peek(lu))
        results["BSE.lookup"] = True
    except Exception as e:
        fail("lookup('RELIANCE')", e); results["BSE.lookup"] = False

# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
section("SUMMARY")

passed = [k for k, v in results.items() if v]
failed = [k for k, v in results.items() if not v]

print(f"\n  {GREEN}PASSED ({len(passed)}){RESET}")
for k in passed:
    print(f"    {GREEN}✓{RESET} {k}")

print(f"\n  {RED}FAILED ({len(failed)}){RESET}")
for k in failed:
    print(f"    {RED}✗{RESET} {k}")

print(f"\n  Total: {len(results)}  |  Pass rate: {100*len(passed)//len(results)}%\n")
