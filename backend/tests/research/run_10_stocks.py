"""
run_10_stocks.py — Ad-hoc runner: test all 7 Phase-2 services across 10 stocks.

Prints a coverage table: which services returned nodes, how many, what source won.

Run:
  cd stocxi
  python -m backend.tests.research.run_10_stocks
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import date
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from backend.schemas.messages import UserProfile, Horizon, Risk

PROFILE  = UserProfile(horizon=Horizon.short, risk=Risk.moderate)
AS_OF    = date.today()

STOCKS = [
    "RELIANCE",    # large cap — energy / conglomerate
    "TCS",         # large cap — IT services
    "HDFCBANK",    # large cap — private banking
    "SUNPHARMA",   # large cap — pharmaceuticals
    "TATAMOTORS",  # large cap — automobiles
    "ETERNAL",     # mid cap  — new-age consumer tech (food delivery, Zomato)
    "IRCTC",       # mid cap  — PSU / travel / tourism
    "DMART",       # mid cap  — retail / FMCG distribution
    "COALINDIA",   # large cap — mining / commodities (PSU)
    "NESTLEIND",   # large cap — FMCG / packaged foods
]

SERVICES = ["price", "ohlcv", "ratios", "financials", "shareholding", "technicals", "announcements"]

COL_W = 22   # column width for service columns


async def run_price(symbol: str) -> dict:
    from backend.services.price_service import get_price
    nodes = await get_price(symbol, AS_OF, PROFILE)
    return {"count": len(nodes), "source": nodes[0].source if nodes else "—"}


async def run_ohlcv(symbol: str) -> dict:
    import pandas as pd
    from backend.services.ohlcv_service import get_ohlcv
    df = await get_ohlcv(symbol, AS_OF)
    return {"count": len(df), "source": "nse/yf" if not df.empty else "—"}


async def run_ratios(symbol: str) -> dict:
    from backend.services.ratios_service import get_ratios
    nodes = await get_ratios(symbol, AS_OF, PROFILE)
    return {"count": len(nodes), "source": nodes[0].source if nodes else "—"}


async def run_financials(symbol: str) -> dict:
    from backend.services.financials_service import get_financials
    nodes = await get_financials(symbol, AS_OF, PROFILE)
    return {"count": len(nodes), "source": nodes[0].source if nodes else "—"}


async def run_shareholding(symbol: str) -> dict:
    from backend.services.shareholding_service import get_shareholding
    nodes = await get_shareholding(symbol, AS_OF, PROFILE)
    return {"count": len(nodes), "source": nodes[0].source if nodes else "—"}


async def run_technicals(symbol: str) -> dict:
    from backend.services.technicals_service import get_technicals
    nodes = await get_technicals(symbol, as_of_date=AS_OF, profile=PROFILE)
    return {"count": len(nodes), "source": "ta_lib" if nodes else "—"}


async def run_announcements(symbol: str) -> dict:
    from backend.services.announcements_service import get_announcements
    nodes = await get_announcements(symbol, AS_OF, PROFILE)
    return {"count": len(nodes), "source": "nse+bse" if nodes else "—"}


RUNNERS = {
    "price":         run_price,
    "ohlcv":         run_ohlcv,
    "ratios":        run_ratios,
    "financials":    run_financials,
    "shareholding":  run_shareholding,
    "technicals":    run_technicals,
    "announcements": run_announcements,
}


async def probe_stock(symbol: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for svc, fn in RUNNERS.items():
        try:
            r = await fn(symbol)
            results[svc] = r
        except Exception as exc:
            results[svc] = {"count": 0, "source": f"ERR:{exc!s:.25}"}
    return results


def fmt_cell(r: dict) -> str:
    if r["source"] == "—":
        return "✗ 0".ljust(COL_W)
    cnt  = r["count"]
    src  = r["source"][:12]
    cell = f"✓ {cnt} [{src}]"
    return cell.ljust(COL_W)


async def main() -> None:
    print(f"\nPhase 2.8 — 10-stock coverage run  ({AS_OF})")
    print("=" * (14 + COL_W * len(SERVICES) + len(SERVICES)))

    # Header
    header = "Stock".ljust(14) + "".join(s.ljust(COL_W) for s in SERVICES)
    print(header)
    print("-" * len(header))

    totals: dict[str, int] = {s: 0 for s in SERVICES}

    for symbol in STOCKS:
        print(f"  {symbol:<12}", end="", flush=True)
        res = await probe_stock(symbol)
        row = symbol.ljust(14)
        for svc in SERVICES:
            r = res[svc]
            row += fmt_cell(r)
            if r["count"] > 0:
                totals[svc] += 1
        print(row)

    # Summary
    print("-" * len(header))
    summary = "Coverage".ljust(14)
    for svc in SERVICES:
        cell = f"{totals[svc]}/10"
        summary += cell.ljust(COL_W)
    print(summary)
    print()

    # Per-service detail
    print("Detail: sources used per service")
    print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())
