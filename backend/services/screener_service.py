"""
screener_service.py — Scrape quarterly financials + key ratios from Screener.in.

Why scraping?
  Screener.in has the most reliable Indian quarterly P&L, balance sheet,
  cash flow, and shareholding data. No official API exists. Public pages
  need only a User-Agent header; no login required.

Strategy (from AI_CONTEXT.md):
  1. Try consolidated URL first (most companies have it)
  2. Fallback to standalone URL if consolidated returns 404 / empty tables
  3. On timeout or any error → return empty dict (frontend shows "unavailable")
  4. Cached 7 days — screener data updates only at quarterly results

Tables extracted (by HTML id):
  #top-ratios           → PE ratio, market cap, book value, dividend yield, ROCE, ROE
  #quarters             → quarterly P&L
  #profit-loss          → annual P&L (YoY)
  #balance-sheet        → balance sheet
  #cash-flow            → cash flow statement
  #shareholding         → shareholding pattern
  #mutual-fund-holdings → MF holdings breakdown

Golden rule: every extraction is try/excepted. Returns None on failure.
Runs sync requests in a thread pool.
"""

import asyncio
import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Screener blocks requests with default Python UA; this mimics a real browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_TIMEOUT = 10  # seconds — from AI_CONTEXT.md; return empty on breach


def _parse_table(table) -> dict:
    """
    Convert a Screener.in HTML table into a dict:
      {
        "headers": ["Mar 2022", "Jun 2022", ...],
        "rows": [
          {"label": "Revenue", "values": [12345, 13456, ...]},
          ...
        ]
      }

    Screener tables have:
      - First <th> in each <tr> = row label (e.g. "Revenue", "Net Profit")
      - Remaining <td>s = period values (newest on left)
    """
    if table is None:
        return {}

    # Extract column headers from thead
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        if header_row:
            # Skip first th (it's the row-label column header, usually empty)
            headers = [th.get_text(strip=True) for th in header_row.find_all("th")[1:]]

    # Extract data rows from tbody
    rows = []
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            if not label:
                continue
            values = []
            for cell in cells[1:]:
                text = cell.get_text(strip=True).replace(",", "").replace("%", "").strip()
                try:
                    values.append(float(text))
                except ValueError:
                    # Non-numeric cells (e.g. "—", "N/A") stored as-is
                    values.append(text if text else None)
            rows.append({"label": label, "values": values})

    return {"headers": headers, "rows": rows}


def _parse_top_ratios(soup) -> dict:
    """
    Extract key ratios from Screener's #top-ratios section.
    Returns dict with: pe_ratio, market_cap, book_value, dividend_yield,
                       roce, roe, face_value, sector, industry
    All values are None if not found — never raises.
    """
    result = {
        "pe_ratio": None, "market_cap": None, "book_value": None,
        "dividend_yield": None, "roce": None, "roe": None,
        "face_value": None, "sector": None, "industry": None,
    }
    try:
        ratios_ul = soup.find("ul", {"id": "top-ratios"})
        if not ratios_ul:
            return result

        # Each <li> has a <span class="name"> and a <span class="nowrap value"> (or similar)
        for li in ratios_ul.find_all("li"):
            try:
                name_el  = li.find("span", class_="name")
                value_el = li.find("span", class_="nowrap value") or li.find("span", class_="value")
                if not name_el or not value_el:
                    continue

                name  = name_el.get_text(strip=True).lower()
                # Value may contain nested spans and suffixes like "Cr." — get raw text
                raw   = value_el.get_text(strip=True)

                def to_float(s: str):
                    """Extract first number from strings like '1,77,604 Cr.' or '23.2%'"""
                    import re
                    s = s.replace(",", "")
                    m = re.search(r"[-+]?\d+\.?\d*", s)
                    return float(m.group()) if m else None

                if "stock p/e" in name or ("p/e" in name and "stock" in name):
                    result["pe_ratio"] = to_float(raw)
                elif "market cap" in name or "mkt cap" in name:
                    result["market_cap"] = to_float(raw)  # in Cr
                elif "book value" in name:
                    result["book_value"] = to_float(raw)
                elif "dividend yield" in name:
                    result["dividend_yield"] = to_float(raw)
                elif "roce" in name:
                    result["roce"] = to_float(raw)
                elif "roe" in name:
                    result["roe"] = to_float(raw)
                elif "face value" in name:
                    result["face_value"] = to_float(raw)
            except Exception:
                continue

        # Sector: screener shows it as a breadcrumb link in .company-info or similar
        try:
            # Try company-info section (varies by screener version)
            info_section = soup.find("div", class_="company-info")
            if info_section:
                links = info_section.find_all("a", href=True)
                sector_links = [a.get_text(strip=True) for a in links
                                if "/screens/" in (a.get("href") or "")]
                if sector_links:
                    result["sector"] = sector_links[0]
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"Screener top-ratios parse error: {e}")

    return result


def _extract_mf_holdings(symbol: str, soup, referer_url: str | None) -> dict:
    """
    Fetch mutual fund holdings from Screener investor drilldown API.

    Screener exposes investor-level data via:
      /api/3/{companyId}/investors/domestic_institutions/quarterly/

    We filter rows whose investor names include "mutual fund"/"mutual funds".
    Returns {}
    on any failure to keep this service fully non-fatal.
    """
    try:
        company_id = None
        root = soup.find(attrs={"data-company-id": True})
        if root:
            company_id = root.get("data-company-id")

        if not company_id:
            html = str(soup)
            m = re.search(r'data-company-id="(\d+)"', html)
            if m:
                company_id = m.group(1)

        if not company_id:
            return {}

        api_url = f"https://www.screener.in/api/3/{company_id}/investors/domestic_institutions/quarterly/"
        headers = dict(_HEADERS)
        headers["Accept"] = "application/json, text/plain, */*"
        if referer_url:
            headers["Referer"] = referer_url

        resp = requests.get(api_url, headers=headers, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return {}

        data = resp.json()
        if not isinstance(data, dict) or not data:
            return {}

        mf_items: list[tuple[str, dict]] = []
        for investor_name, series in data.items():
            if not isinstance(investor_name, str) or not isinstance(series, dict):
                continue
            low_name = investor_name.lower()
            if "mutual fund" in low_name or "mutual funds" in low_name:
                mf_items.append((investor_name, series))

        if not mf_items:
            return {}

        # Build period headers from first mutual-fund series, excluding metadata keys.
        headers_list = [k for k in mf_items[0][1].keys() if k != "setAttributes"]

        rows = []
        for investor_name, series in mf_items:
            values = []
            for period in headers_list:
                val = series.get(period)
                try:
                    values.append(float(val) if val not in (None, "") else None)
                except Exception:
                    values.append(val)
            rows.append({"label": investor_name, "values": values})

        return {
            "headers": headers_list,
            "rows": rows,
        }
    except Exception as e:
        logger.warning(f"Screener MF holdings parse error for {symbol}: {e}")
        return {}


def _fetch_screener(symbol: str) -> dict:
    """
    Sync fetch — runs in thread pool.
    Returns dict with keys: quarterly_results, annual_results, balance_sheet,
                            cash_flow, shareholding, mf_holdings.
    Returns empty sub-dicts on any failure (never raises).
    """
    symbol = symbol.upper().strip()

    # Try consolidated first, then standalone
    urls = [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]

    soup = None
    used_url = None

    for url in urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 200:
                candidate = BeautifulSoup(resp.text, "lxml")
                # Confirm we got real data — check if #quarters table exists
                if candidate.find("section", {"id": "quarters"}):
                    soup = candidate
                    used_url = url
                    logger.info(f"Screener: fetched {symbol} from {url}")
                    break
                else:
                    logger.debug(f"Screener: {url} returned 200 but no #quarters table")
            else:
                logger.debug(f"Screener: {url} returned HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            logger.warning(f"Screener: timeout fetching {url} for {symbol}")
        except Exception as e:
            logger.warning(f"Screener: error fetching {url} for {symbol}: {e}")

    if soup is None:
        logger.warning(f"Screener: no data found for {symbol}")
        return {
            "quarterly_results": {},
            "balance_sheet": {},
            "cash_flow": {},
            "shareholding": {},
            "source_url": None,
        }

    # ── Extract all 4 tables ───────────────────────────────────────────────────
    def extract(section_id: str) -> dict:
        section = soup.find("section", {"id": section_id})
        if section is None:
            return {}
        table = section.find("table")
        return _parse_table(table)

    # Shareholding section uses a different structure — extract differently
    def extract_shareholding() -> dict:
        section = soup.find("section", {"id": "shareholding"})
        if section is None:
            return {}
        table = section.find("table")
        return _parse_table(table)

    return {
        "ratios":            _parse_top_ratios(soup),   # PE, market cap, sector, etc.
        "quarterly_results": extract("quarters"),
        "annual_results":    extract("profit-loss"),    # annual P&L (YoY)
        "balance_sheet":     extract("balance-sheet"),
        "cash_flow":         extract("cash-flow"),
        "shareholding":      extract_shareholding(),
        "mf_holdings":       _extract_mf_holdings(symbol, soup, used_url),
        "source_url":        used_url,
    }


async def get_financials(symbol: str) -> dict:
    """
    Async entry point — offloads sync HTTP + BS4 parse to thread pool.
    Returns financials dict. Never raises — returns empty sub-dicts on failure.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_screener, symbol)
