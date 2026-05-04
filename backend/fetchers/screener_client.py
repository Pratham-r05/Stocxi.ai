"""
screener_client.py — Async wrapper around the Screener.in scraper.

Screener.in provides the most reliable Indian quarterly P&L, balance sheet,
cash flow, and shareholding data. No official API — scrapes public pages.

Source ID: "screener_in" (config/sources.yaml, priority 2 for fundamentals).
Confidence: 0.85 (L2 — verified scraper).

Key logic (already tested and fixed in screener_service.py):
  - Fetch BOTH consolidated and standalone pages for every company.
  - Compare the most-recent period header from each (#quarters table).
  - Use whichever page has fresher data — NOT always consolidated.
  - Rationale: small caps / NBFCs (e.g. QUESTCAP) can have Dec 2020
    consolidated data while standalone has Mar 2025 quarterly results.

Delegate: This client delegates to the existing screener_service.get_financials()
which contains all the tested scraping + parsing logic. The client's role is
to wrap the result in the standard FetchResult contract.

Data returned (keys in payload):
  ratios            → PE, market cap, book value, EPS, ROCE, ROE, dividend yield
  quarterly_results → {headers, rows} — quarterly P&L
  annual_results    → {headers, rows} — annual P&L
  balance_sheet     → {headers, rows}
  cash_flow         → {headers, rows}
  shareholding      → {headers, rows} — promoter/FII/DII breakdown
  mf_holdings       → {headers, rows} — mutual fund holdings drill-down
  website           → company website URL
  source_url        → which Screener page was used (consolidated or standalone)
"""

from __future__ import annotations

import logging
from typing import Any

from services import screener_service

logger = logging.getLogger(__name__)

SOURCE_ID  = "screener_in"
CONFIDENCE = 0.85


async def fetch_financials(symbol: str) -> dict[str, Any]:
    """
    Fetch financial statements + key ratios from Screener.in.

    Delegates to screener_service.get_financials() which:
      1. Resolves the Screener slug via their search API.
      2. Fetches both consolidated and standalone pages.
      3. Picks the page with the most recent period header.
      4. Parses quarterly P&L, annual P&L, balance sheet, cash flow,
         shareholding, and top-ratios sections.

    Args:
        symbol: NSE ticker in uppercase (e.g. "RELIANCE").

    Returns:
        Dict with keys: ratios, quarterly_results, annual_results,
        balance_sheet, cash_flow, shareholding, mf_holdings,
        website, source_url.

    Raises:
        ValueError: if Screener returns no usable data for the symbol.
    """
    symbol = symbol.upper().strip()
    data = await screener_service.get_financials(symbol)

    # screener_service never raises — it returns empty dicts on failure.
    # Promote to an exception if we got nothing useful, so WaterfallRunner
    # can fall through to the next level.
    if not _has_useful_data(data):
        raise ValueError(
            f"Screener.in returned no usable financial data for '{symbol}'. "
            "Stock may not be listed on Screener or page structure changed."
        )

    data["symbol"] = symbol
    return data


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_useful_data(data: dict) -> bool:
    """
    Return True if the Screener response contains at least one populated section.

    A response with all empty dicts means Screener had no data for this symbol
    (e.g. recently listed, BSE-only stock, or scrape failure).
    """
    useful_keys = ("quarterly_results", "annual_results", "ratios", "balance_sheet")
    return any(bool(data.get(k)) for k in useful_keys)
