"""
schedule.py — Generate quarterly point-in-time backtest dates.

Each date is:
  - A trading day on NSE (not weekend, not holiday)
  - The last trading day of a calendar quarter, going back N quarters
  - At least MIN_HISTORY_DAYS before `ref_date` so data exists

Usage:
    dates = generate_backtest_dates(n=12)
    # → 12 quarterly dates spanning ~3 years, most recent first
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.util.ist_calendar import is_trading_day, last_trading_day


MIN_HISTORY_DAYS = 30   # minimum days of history a signal_date must have before today


def _quarter_end(d: date) -> date:
    """Return the last calendar day of the quarter containing d."""
    q_end_month = ((d.month - 1) // 3 + 1) * 3  # 3, 6, 9, or 12
    if q_end_month in (3, 12):
        day = 31
    elif q_end_month in (6, 9):
        day = 30
    else:
        day = 31
    return date(d.year, q_end_month, day)


def _prev_quarter_end(d: date) -> date:
    """Return the last calendar day of the quarter before d's quarter."""
    first_of_quarter = date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)
    return first_of_quarter - timedelta(days=1)


def generate_backtest_dates(
    n: int = 12,
    ref_date: date | None = None,
) -> list[date]:
    """
    Return up to n quarterly trading dates going back from ref_date.

    Dates are the last trading day of each calendar quarter (Q-end).
    The most recent date is at least MIN_HISTORY_DAYS before ref_date
    so that outcome prices can always be fetched.

    Returns dates in ascending order (oldest first).
    """
    ref = ref_date or date.today()
    cutoff = ref - timedelta(days=MIN_HISTORY_DAYS)

    dates: list[date] = []
    # Start from the quarter before the cutoff quarter
    cursor = _prev_quarter_end(cutoff)

    while len(dates) < n and cursor > date(2019, 1, 1):
        qe_trading = last_trading_day(cursor)
        if qe_trading <= cutoff:
            dates.append(qe_trading)
        cursor = _prev_quarter_end(cursor)

    return list(reversed(dates))  # oldest first
