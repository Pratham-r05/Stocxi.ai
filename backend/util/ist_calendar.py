"""
ist_calendar.py — IST timezone helpers and NSE trading calendar.

All timestamps in Stocxi are stored and compared in IST (Asia/Kolkata, UTC+5:30).
Never use UTC naively for Indian market logic — NSE closes at 15:30 IST.

NSE holidays are hardcoded for 2024–2026.
Add next year's calendar each December from: https://www.nseindia.com/resources/exchange-communication-holidays
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# NSE market hours (IST)
MARKET_OPEN  = time(9, 15)
MARKET_CLOSE = time(15, 30)

# ── NSE Holidays (Exchange holidays — market fully closed) ────────────────────
# Source: NSE India official holiday list
# Format: date(YYYY, MM, DD)

_NSE_HOLIDAYS: frozenset[date] = frozenset([
    # 2024
    date(2024, 1, 22),   # Special holiday (Ram Mandir consecration)
    date(2024, 1, 26),   # Republic Day
    date(2024, 3, 8),    # Mahashivratri
    date(2024, 3, 25),   # Holi
    date(2024, 3, 29),   # Good Friday
    date(2024, 4, 11),   # Id-Ul-Fitr (Ramzan Eid)
    date(2024, 4, 14),   # Dr. Ambedkar Jayanti
    date(2024, 4, 17),   # Ram Navami
    date(2024, 4, 21),   # Mahavir Jayanti
    date(2024, 5, 23),   # Buddha Pournima
    date(2024, 6, 17),   # Eid ul-Adha (Bakri Eid)
    date(2024, 7, 17),   # Muharram
    date(2024, 8, 15),   # Independence Day
    date(2024, 10, 2),   # Mahatma Gandhi Jayanti
    date(2024, 10, 13),  # Dussehra
    date(2024, 11, 1),   # Diwali Laxmi Pujan
    date(2024, 11, 15),  # Gurunanak Jayanti
    date(2024, 12, 25),  # Christmas

    # 2025
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 26),   # Mahashivratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-Ul-Fitr (Ramzan Eid)
    date(2025, 4, 10),   # Shri Ram Navami
    date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 27),   # Ganesh Chaturthi
    date(2025, 10, 2),   # Mahatma Gandhi Jayanti
    date(2025, 10, 2),   # Dussehra (same date 2025)
    date(2025, 10, 20),  # Diwali Laxmi Pujan
    date(2025, 10, 21),  # Diwali Balipratipada
    date(2025, 11, 5),   # Gurunanak Jayanti
    date(2025, 12, 25),  # Christmas

    # 2026 — update when NSE publishes official list
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 20),   # Holi (approximate — verify with NSE)
    date(2026, 4, 3),    # Good Friday (approximate)
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 12, 25),  # Christmas
])


# ── Core helpers ───────────────────────────────────────────────────────────────

def now_ist() -> datetime:
    """Current datetime in IST."""
    return datetime.now(tz=IST)


def today_ist() -> date:
    """Today's date in IST."""
    return now_ist().date()


def to_ist(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to IST."""
    return dt.astimezone(IST)


def is_nse_holiday(d: date) -> bool:
    """Return True if the given date is an NSE exchange holiday."""
    return d in _NSE_HOLIDAYS


def is_weekend(d: date) -> bool:
    """Return True if date is Saturday (5) or Sunday (6)."""
    return d.weekday() >= 5


def is_trading_day(d: date) -> bool:
    """Return True if NSE trades on this date."""
    return not is_weekend(d) and not is_nse_holiday(d)


def last_trading_day(reference: date | None = None) -> date:
    """
    Return the most recent trading day on or before `reference`.
    Defaults to today IST.
    """
    d = reference or today_ist()
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def prev_trading_day(reference: date | None = None) -> date:
    """Return the trading day immediately before `reference`."""
    d = (reference or today_ist()) - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def is_market_open(dt: datetime | None = None) -> bool:
    """Return True if NSE is currently open (trading hours on a trading day, IST)."""
    now = to_ist(dt) if dt else now_ist()
    if not is_trading_day(now.date()):
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def trading_days_between(start: date, end: date) -> int:
    """Count trading days between start (inclusive) and end (inclusive)."""
    count = 0
    d = start
    while d <= end:
        if is_trading_day(d):
            count += 1
        d += timedelta(days=1)
    return count


def trading_days_ago(n: int, reference: date | None = None) -> date:
    """Return the date that is exactly n trading days before reference."""
    d = reference or today_ist()
    counted = 0
    while counted < n:
        d -= timedelta(days=1)
        if is_trading_day(d):
            counted += 1
    return d


def as_of_date_for_fetch(reference: date | None = None) -> date:
    """
    Return the correct as_of_date to use when fetching data.
    If today is a trading day and market is open, use yesterday's close.
    If market is closed today, use last completed trading day.
    This prevents accidentally using intraday partial data as a 'daily' bar.
    """
    today = reference or today_ist()
    if is_trading_day(today) and is_market_open():
        # Market still open — use previous completed day
        return prev_trading_day(today)
    return last_trading_day(today)
