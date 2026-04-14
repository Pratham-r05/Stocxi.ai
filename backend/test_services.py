"""
Quick smoke test for yfinance_service and screener_service.
Run from backend/ directory with conda stocxi env active:

    cd backend
    python test_services.py

Tests RELIANCE (large-cap NSE stock) — should always return data.
"""

import asyncio
import sys
import os

# Add backend dir to path so imports work without installing the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.yfinance_service import get_price_and_fundamentals
from services.screener_service import get_financials
from services.technicals_service import calculate_technicals


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


async def test_yfinance():
    section("TEST: yfinance_service — RELIANCE")
    try:
        data = await get_price_and_fundamentals("RELIANCE")
        print(f"✅ Symbol      : {data['symbol']}")
        print(f"✅ Exchange     : {data['exchange']}")
        print(f"✅ Company      : {data['company_name']}")
        print(f"✅ Price        : ₹{data['price']}")
        print(f"✅ Change       : {data['change']} ({data['change_percent']}%)")
        print(f"✅ Market Cap   : {data['market_cap']}")
        print(f"✅ PE Ratio     : {data['pe_ratio']}")
        print(f"✅ 52W High/Low : {data['week_52_high']} / {data['week_52_low']}")
        print(f"✅ Sector       : {data['sector']}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


async def test_yfinance_invalid():
    section("TEST: yfinance_service — INVALIDSYMBOL (should raise ValueError)")
    try:
        data = await get_price_and_fundamentals("INVALIDSYMBOL123")
        print(f"❌ Should have raised ValueError, got: {data}")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"❌ Wrong exception type: {type(e).__name__}: {e}")
        return False


async def test_screener():
    section("TEST: screener_service — RELIANCE")
    try:
        data = await get_financials("RELIANCE")
        qr = data.get("quarterly_results", {})
        bs = data.get("balance_sheet", {})
        cf = data.get("cash_flow", {})
        sh = data.get("shareholding", {})
        ratios = data.get("ratios", {})

        print(f"✅ Source URL         : {data.get('source_url')}")
        print(f"✅ Quarterly Headers  : {qr.get('headers', [])[:4]}...")
        print(f"✅ Quarterly Rows     : {len(qr.get('rows', []))} rows found")
        print(f"✅ Balance Sheet Rows : {len(bs.get('rows', []))} rows found")
        print(f"✅ Cash Flow Rows     : {len(cf.get('rows', []))} rows found")
        print(f"✅ Shareholding Rows  : {len(sh.get('rows', []))} rows found")
        print(f"✅ PE Ratio           : {ratios.get('pe_ratio')}")
        print(f"✅ Market Cap (Cr)    : {ratios.get('market_cap')}")
        print(f"✅ Book Value         : {ratios.get('book_value')}")
        print(f"✅ Dividend Yield     : {ratios.get('dividend_yield')}")
        print(f"✅ ROCE               : {ratios.get('roce')}")
        print(f"✅ ROE                : {ratios.get('roe')}")
        print(f"✅ Sector             : {ratios.get('sector')}")

        if not qr.get("rows"):
            print("⚠️  Quarterly results empty — screener layout may have changed")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


async def test_technicals():
    section("TEST: technicals_service — RELIANCE")
    try:
        data = await calculate_technicals("RELIANCE")

        if data.get("error"):
            print(f"⚠️  {data['error']}")
            return False

        print(f"✅ RSI(14)       : {data['rsi']} → {data['rsi_signal']}")
        print(f"✅ MACD          : {data['macd']} → {data['macd_signal']}")
        print(f"✅ ADX(14)       : {data['adx']} → {data['adx_signal']}")
        print(f"✅ ATR(14)       : {data['atr']}")
        print(f"✅ BB Upper/Lower: {data['bb_upper']} / {data['bb_lower']} → {data['bb_signal']}")
        print(f"✅ EMA 20/50/200 : {data['ema_20']} / {data['ema_50']} / {data['ema_200']}")
        print(f"✅ EMA Signal    : {data['ema_signal']}")
        print(f"✅ Overall Signal: {data['overall_signal']}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


async def main():
    results = []
    results.append(await test_yfinance())
    results.append(await test_yfinance_invalid())
    results.append(await test_screener())
    results.append(await test_technicals())

    section("SUMMARY")
    passed = sum(results)
    total = len(results)
    print(f"{'✅' if passed == total else '❌'} {passed}/{total} tests passed")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
