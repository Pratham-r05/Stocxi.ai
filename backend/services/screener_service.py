"""
screener_service.py — Scrape quarterly financials + key ratios from Screener.in.

Why scraping?
  Screener.in has the most reliable Indian quarterly P&L, balance sheet,
  cash flow, and shareholding data. No official API exists. Public pages
  need only a User-Agent header; no login required.

Strategy:
  1. Fetch BOTH consolidated and standalone URLs
  2. Compare the most recent period header from each (e.g. "Mar 2025" vs "Dec 2020")
  3. Use whichever page has more recent data — not always consolidated
  4. Rationale: small caps / NBFCs (e.g. QUESTCAP) may have stale consolidated
     data while standalone has current quarterly results up to present
  5. On timeout or any error → return empty dict (frontend shows "unavailable")
  6. Cached 7 days — screener data updates only at quarterly results

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
from functools import lru_cache
from typing import Any

import requests
import yaml
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

# ── Screener slug override config ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_screener_slug_overrides() -> dict[str, str]:
    """
    Load NSE symbol → Screener slug overrides from config/screener_slugs.yaml.

    Returns:
        Dict mapping uppercase NSE symbols to their Screener URL slugs.
        Returns empty dict if config file is missing or malformed.
    """
    import pathlib
    config_path = pathlib.Path(__file__).parent.parent.parent / "config" / "screener_slugs.yaml"
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return {str(k).upper(): str(v) for k, v in data.items()}
    except Exception as e:
        logger.debug("screener_slugs.yaml not found or malformed: %s", e)
        return {}


def _parse_company_website(soup) -> str | None:
    """Extract official company website from Screener company links."""
    try:
        links_wrap = soup.find("div", class_="company-links")
        if not links_wrap:
            return None

        for anchor in links_wrap.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            low = href.lower()
            # Exclude market/reference links; keep primary corporate website.
            if "bseindia.com" in low or "nseindia.com" in low or "screener.in" in low:
                continue
            if low.startswith("http://") or low.startswith("https://"):
                return href
    except Exception:
        pass
    return None


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


_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _most_recent_period(soup) -> tuple[int, int] | None:
    """
    Extract the most recent data period from the #quarters table headers.

    Screener period strings look like "Mar 2025", "Dec 2024", "TTM".
    Returns (year, month) tuple for comparison, or None if unparseable.
    "TTM" is treated as current month — always wins.
    """
    section = soup.find("section", {"id": "quarters"})
    if section is None:
        return None
    table = section.find("table")
    if table is None:
        return None
    thead = table.find("thead")
    if thead is None:
        return None
    header_row = thead.find("tr")
    if header_row is None:
        return None

    # Headers are newest-first after the label column
    headers = [th.get_text(strip=True) for th in header_row.find_all("th")[1:]]

    import datetime as _dt
    for h in headers:
        h_low = h.lower().strip()
        if "ttm" in h_low:
            now = _dt.date.today()
            return (now.year, now.month)
        # Match "Mar 2025", "Dec 2024" etc.
        m = re.match(r"([a-zA-Z]{3})\s+(\d{4})", h)
        if m:
            month_str = m.group(1).lower()
            year = int(m.group(2))
            month = _MONTH_MAP.get(month_str)
            if month:
                return (year, month)
    return None


def _parse_top_ratios(soup) -> dict:
    """
    Extract key ratios from Screener's #top-ratios section.
    Returns dict with: pe_ratio, market_cap, book_value, dividend_yield,
                       roce, roe, face_value, eps, sector, industry
    All values are None if not found — never raises.
    """
    result = {
        "pe_ratio": None, "market_cap": None, "book_value": None,
        "dividend_yield": None, "roce": None, "roe": None,
        "face_value": None, "eps": None, "sector": None, "industry": None,
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
                    # Screener market cap is in crores; normalize to rupees for API consistency.
                    val = to_float(raw)
                    result["market_cap"] = int(val * 1e7) if val is not None else None
                elif "book value" in name:
                    result["book_value"] = to_float(raw)
                elif "eps" in name:
                    result["eps"] = to_float(raw)
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

        # Sector / industry links in newer Screener layout expose semantic title attributes.
        try:
            sector_link = soup.select_one('a[title="Sector"]') or soup.select_one('a[title="Broad Sector"]')
            if sector_link:
                result["sector"] = sector_link.get_text(strip=True) or None
        except Exception:
            pass

        try:
            industry_link = soup.select_one('a[title="Industry"]') or soup.select_one('a[title="Broad Industry"]')
            if industry_link:
                result["industry"] = industry_link.get_text(strip=True) or result["industry"]
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


def _resolve_screener_slug(symbol: str) -> str:
    """
    Resolve the correct Screener.in URL slug for a given NSE symbol.

    Resolution order:
      1. config/screener_slugs.yaml — static overrides for known mismatches.
      2. Screener search API by NSE symbol (exact match).
      3. Screener search API by NSE company name (for stocks with different slugs).
      4. Raw symbol as-is (last resort).

    Args:
        symbol: NSE ticker symbol (e.g. "TATAMOTORS").

    Returns:
        Screener URL slug string (e.g. "TMCV", "eternal").
    """
    symbol = symbol.upper().strip()

    # 1. Static overrides
    overrides = _load_screener_slug_overrides()
    if symbol in overrides:
        slug = overrides[symbol]
        logger.debug("Screener slug override: %s → %s", symbol, slug)
        return slug

    skip = {"company", "consolidated", "standalone", ""}

    def _extract_slug(results: list) -> str | None:
        valid = [r for r in results if r.get("id") is not None]
        if not valid:
            return None
        url_path = valid[0].get("url", "")
        parts = [p for p in url_path.strip("/").split("/") if p not in skip]
        return parts[0] if parts else None

    # 2. Search by NSE symbol
    try:
        resp = requests.get(
            f"https://www.screener.in/api/company/search/?q={symbol}&v=3&fts=1",
            headers=_HEADERS, timeout=8,
        )
        if resp.status_code == 200:
            slug = _extract_slug(resp.json())
            if slug:
                logger.info("Screener slug resolved by symbol: %s → %s", symbol, slug)
                return slug
    except Exception as e:
        logger.debug("Screener symbol search failed for %s: %s", symbol, e)

    # 3. Fallback: look up NSE company name and search by that
    try:
        from backend.fetchers.nse_client import _get_nse, _run_sync
        import asyncio
        loop = asyncio.get_event_loop()
        nse = _get_nse()
        raw = loop.run_until_complete(_run_sync(nse.equityQuote, symbol))
        company_name = raw.get("companyName") or raw.get("name") if isinstance(raw, dict) else None
        if company_name:
            resp2 = requests.get(
                f"https://www.screener.in/api/company/search/?q={company_name}&v=3&fts=1",
                headers=_HEADERS, timeout=8,
            )
            if resp2.status_code == 200:
                slug = _extract_slug(resp2.json())
                if slug:
                    logger.info("Screener slug resolved by company name '%s': %s → %s",
                                company_name, symbol, slug)
                    return slug
    except Exception as e:
        logger.debug("Screener name-based slug resolution failed for %s: %s", symbol, e)

    logger.warning("Screener: no data found for %s", symbol)
    return symbol


def _fetch_screener(symbol: str) -> dict:
    """
    Sync fetch — runs in thread pool.
    Returns dict with keys: quarterly_results, annual_results, balance_sheet,
                            cash_flow, shareholding, mf_holdings.
    Returns empty sub-dicts on any failure (never raises).
    """
    symbol = symbol.upper().strip()
    slug = _resolve_screener_slug(symbol)

    # Fetch BOTH consolidated and standalone, then pick the one with more recent data.
    # Reason: small caps / NBFCs (e.g. QUESTCAP) can have stale consolidated pages
    # while standalone is current. Always comparing prevents silently returning
    # years-old data when fresh standalone data exists.
    candidate_urls = [
        f"https://www.screener.in/company/{slug}/consolidated/",
        f"https://www.screener.in/company/{slug}/",
    ]

    # (soup, url, most_recent_period_tuple)
    candidates: list[tuple] = []

    for url in candidate_urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 200:
                candidate = BeautifulSoup(resp.text, "lxml")
                if candidate.find("section", {"id": "quarters"}):
                    period = _most_recent_period(candidate)
                    candidates.append((candidate, url, period))
                    logger.debug(
                        f"Screener: {url} → most recent period: {period}"
                    )
                else:
                    logger.debug(f"Screener: {url} returned 200 but no #quarters table")
            else:
                logger.debug(f"Screener: {url} returned HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            logger.warning(f"Screener: timeout fetching {url} for {symbol}")
        except Exception as e:
            logger.warning(f"Screener: error fetching {url} for {symbol}: {e}")

    # Pick the candidate with the most recent period header.
    # If period is None (unparseable), treat as (0, 0) so any dated page wins.
    soup = None
    used_url = None

    if candidates:
        best = max(candidates, key=lambda c: c[2] if c[2] is not None else (0, 0))
        soup, used_url, best_period = best
        logger.info(
            f"Screener: using {used_url} for {symbol} "
            f"(most recent period: {best_period})"
        )

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

    ratios         = _parse_top_ratios(soup)
    annual_results = extract("profit-loss")

    # EPS fallback: if top-ratios didn't have EPS, pull the most recent value
    # from the annual P&L table (row label contains "eps").
    if ratios.get("eps") is None and annual_results:
        try:
            for row in annual_results.get("rows", []):
                label = (row.get("label") or "").lower()
                if "eps" in label:
                    values = [v for v in row.get("values", []) if v not in (None, "", "0")]
                    if values:
                        import re as _re
                        raw = str(values[-1]).replace(",", "")
                        m = _re.search(r"[-+]?\d+\.?\d*", raw)
                        if m:
                            ratios["eps"] = float(m.group())
                    break
        except Exception:
            pass

    return {
        "ratios":            ratios,
        "quarterly_results": extract("quarters"),
        "annual_results":    annual_results,
        "balance_sheet":     extract("balance-sheet"),
        "cash_flow":         extract("cash-flow"),
        "shareholding":      extract_shareholding(),
        "mf_holdings":       _extract_mf_holdings(symbol, soup, used_url),
        "website":           _parse_company_website(soup),
        "source_url":        used_url,
    }


async def get_financials(symbol: str) -> dict:
    """
    Async entry point — offloads sync HTTP + BS4 parse to thread pool.
    Returns financials dict. Never raises — returns empty sub-dicts on failure.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_screener, symbol)
