"""
announcements_service.py — Fetch recent corporate announcements.

Source strategy:
    1. NSE corporate-announcements API via nsepython.nsefetch (primary)
    2. BSE public API fallback (kept for resilience)

Why NSE primary:
    - Reliable JSON responses in our runtime through nsepython session handling
    - Direct symbol filtering by NSE ticker

Caching: 2 hours (same TTL as news — announcements update infrequently)

Error strategy:
    - Any upstream failure → return empty list (never crashes endpoints)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds
_ANNOUNCE_MAX_AGE_DAYS = 60  # only show announcements within 2 months


def _is_recent_announcement(date_str: str) -> bool:
    """Return True if announcement date is within _ANNOUNCE_MAX_AGE_DAYS."""
    if not date_str:
        return True  # keep if date unknown
    try:
        # Handles ISO format "2026-04-16T19:30:36" and "2026-04-16T19:30:36Z"
        dt_str = date_str.rstrip("Z")
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=_ANNOUNCE_MAX_AGE_DAYS)
        return dt >= cutoff
    except Exception:
        return True  # keep on parse failure

# BSE blocks plain Python UA — mimic a browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
}


def _parse_nse_dt(value: str) -> str:
    """Convert NSE datetime strings like 13042026231734 to ISO-like format."""
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%d%m%Y%H%M%S")
        return dt.isoformat()
    except Exception:
        return value


def _fetch_from_nse(symbol: str, limit: int) -> list[dict]:
    """
    Fetch announcements from NSE corporate announcements API via nsepython.
    Returns normalized list with consistent fields.
    """
    from nsepython import nsefetch  # type: ignore

    url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}"
    raw = nsefetch(url)
    if not isinstance(raw, list):
        return []

    filtered = [
        item for item in raw
        if isinstance(item, dict) and str(item.get("symbol", "")).upper() == symbol
    ]

    results = []
    for item in filtered[: max(limit * 3, 30)]:
        subject = (item.get("desc") or item.get("attchmntText") or "No subject").strip()
        date = _parse_nse_dt(str(item.get("dt") or ""))
        pdf_url = item.get("attchmntFile")
        company_name = item.get("sm_name")
        category = (item.get("desc") or "").strip()

        results.append(
            {
                "title": subject,
                "subject": subject,
                "date": date,
                "category": category,
                "pdf_url": pdf_url,
                "source": "NSE",
                "symbol": symbol,
                "company_name": company_name,
            }
        )

    return results[:limit]


async def _get_bse_code(symbol: str, client: httpx.AsyncClient) -> str | None:
    """
    Resolve NSE ticker → BSE scrip code via BSE's company search API.
    Returns the 6-digit BSE code as a string, or None if not found.
    """
    url = (
        "https://api.bseindia.com/BseIndiaAPI/api/GetCompanySearch/w"
        f"?stype=EQ&value={symbol}"
    )
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # BSE returns a list of matching companies
        companies = data if isinstance(data, list) else data.get("Table", [])
        if not companies:
            logger.warning(f"Announcements: BSE code not found for {symbol}")
            return None

        # First result is usually the exact match
        # Fields vary: SECURITY_CODE or scrip_cd or Code
        first = companies[0]
        code = (
            first.get("SECURITY_CODE") or
            first.get("scrip_cd") or
            first.get("Code") or
            first.get("SecurityCode")
        )
        return str(code) if code else None

    except Exception as e:
        logger.warning(f"Announcements: BSE code lookup failed for {symbol}: {e}")
        return None


async def _get_announcements(bse_code: str, client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch recent corporate announcements for a BSE scrip code.
    Returns list of cleaned announcement dicts.
    """
    url = (
        "https://api.bseindia.com/BseIndiaAPI/api/AnnGetAnnouncementsQuarter/w"
        f"?scrip_cd={bse_code}&strCat=-1&strType=C&Year=&Month=&FDT=&TDT="
    )
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # BSE wraps results in "Table" key
        raw_list = data.get("Table", data) if isinstance(data, dict) else data
        if not isinstance(raw_list, list):
            return []

        results = []
        for item in raw_list[:20]:  # cap at 20 most recent
            # Normalise field names — BSE API field names differ across endpoints
            subject = (
                item.get("HEADLINE") or
                item.get("SUBJECT") or
                item.get("Headline") or
                item.get("Subject") or
                "No subject"
            )
            date = (
                item.get("News_submission_dt") or
                item.get("DT_TM") or
                item.get("Date") or
                ""
            )
            category = (
                item.get("CATEGORYNAME") or
                item.get("Category") or
                item.get("NEWSSUB") or
                ""
            )
            # PDF attachment link (optional)
            attachment = item.get("ATTACHMENTNAME") or item.get("AttachmentName") or ""
            pdf_url = (
                f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attachment}"
                if attachment else None
            )

            results.append({
                "subject":  subject.strip(),
                "date":     date.strip(),
                "category": category.strip(),
                "pdf_url":  pdf_url,
                "bse_code": bse_code,
            })

        return results

    except Exception as e:
        logger.warning(f"Announcements: fetch failed for BSE code {bse_code}: {e}")
        return []


async def get_announcements(symbol: str, limit: int = 10) -> list[dict]:
    """
    Public async entry point.
    Returns list of recent BSE announcements for the given NSE symbol.
    Returns empty list if BSE code not found or API fails — never raises.

    Args:
        symbol: NSE ticker (e.g. "RELIANCE", "TCS")
        limit: Max announcements to return (default 10)
    """
    symbol = symbol.upper().strip()

    # Stage 1: NSE primary via nsepython
    try:
        loop = asyncio.get_event_loop()
        nse_items = await loop.run_in_executor(None, _fetch_from_nse, symbol, limit)
        if nse_items:
            nse_items = [a for a in nse_items if _is_recent_announcement(a.get("date", ""))]
            logger.info(f"Announcements: {len(nse_items)} recent items for {symbol} (NSE)")
            return nse_items
    except Exception as e:
        logger.warning(f"Announcements: NSE fetch failed for {symbol}: {e}")

    # Stage 2: BSE fallback
    async with httpx.AsyncClient() as client:
        bse_code = await _get_bse_code(symbol, client)
        if not bse_code:
            return []

        announcements = await _get_announcements(bse_code, client)

    normalized = []
    for item in announcements[:limit]:
        date_val = item.get("date", "")
        if not _is_recent_announcement(date_val):
            continue  # skip announcements older than 60 days
        subject = (item.get("subject") or "No subject").strip()
        normalized.append(
            {
                "title": subject,
                "subject": subject,
                "date": date_val,
                "category": item.get("category"),
                "pdf_url": item.get("pdf_url"),
                "source": "BSE",
                "symbol": symbol,
                "company_name": None,
                "bse_code": item.get("bse_code"),
            }
        )

    logger.info(f"Announcements: {len(normalized)} recent items for {symbol} (BSE {bse_code})")
    return normalized
