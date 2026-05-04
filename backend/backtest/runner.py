"""
runner.py — Backtest orchestration loop (ARCHITECTURE.md §12).

For each (stock, as_of_date) pair:
  1. Build a FetchRequest with that historical as_of_date
  2. Call orchestrator.run() — agents fetch point-in-time data, LLM analyses
  3. Record signal + confidence as BacktestRun
  4. Fetch actual outcome (price N days later)
  5. Mark correct/incorrect

Point-in-time guarantee:
  - FetchRequest.as_of_date propagates to all agents.
  - technicals_service slices OHLCV to ≤ as_of_date.
  - Outcome prices are fetched AFTER the run — no lookahead.

Usage (run a small test batch, no real LLM calls needed if orchestrator is mocked):
    config = BacktestConfig(
        stocks=["RELIANCE", "TCS"],
        dates=generate_backtest_dates(n=3),
        profile=UserProfile(horizon=Horizon.short, risk=Risk.moderate),
        horizon_days=30,
    )
    runs = asyncio.run(run_backtest(config))
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel

from schemas.messages import FetchRequest, Horizon, Risk, UserProfile
from backtest.outcomes import fetch_outcome, signal_is_correct
from agents.orchestrator import InsufficientDataError

logger = logging.getLogger(__name__)


# ── Data models ────────────────────────────────────────────────────────────────

class BacktestConfig(BaseModel):
    stocks:       list[str]
    dates:        list[date]
    profile:      UserProfile
    horizon_days: int = 30          # calendar days to hold (30 = short, 90 = long)
    concurrency:  int = 3           # max parallel orchestrator calls
    skip_outcome: bool = False      # True = don't fetch prices (dry-run)


class BacktestRun(BaseModel):
    stock:          str
    as_of_date:     date
    profile_bucket: str
    analysis_id:    str

    # Signal from orchestrator
    signal:          str           # bullish / bearish / neutral / mixed
    raw_confidence:  float

    # Outcome (None until filled)
    entry_price:      float | None = None
    exit_price:       float | None = None
    exit_date:        date  | None = None
    actual_return_pct: float | None = None
    nifty_return_pct: float | None = None
    alpha_pct:        float | None = None
    is_correct:       bool  | None = None   # None for neutral/mixed (no trade)

    # Error capture
    error: str | None = None


# ── Single-run helper ──────────────────────────────────────────────────────────

async def _run_one(
    stock: str,
    as_of_date: date,
    profile: UserProfile,
    horizon_days: int,
    skip_outcome: bool,
    sem: asyncio.Semaphore,
) -> BacktestRun:
    """Run one (stock, date) pair. Never raises — captures errors in BacktestRun.error."""
    from agents.orchestrator import run as orch_run

    async with sem:
        analysis_id = str(uuid.uuid4())
        request = FetchRequest(
            stock=stock,
            as_of_date=as_of_date,
            profile=profile,
            request_id=analysis_id,
        )

        try:
            result, _ = await orch_run(request)
            signal         = result.overall_signal
            raw_confidence = result._internal_draft.raw_confidence if result._internal_draft else 0.5
        except InsufficientDataError as exc:
            logger.warning("backtest: INSUFFICIENT_DATA %s/%s — %s", stock, as_of_date, exc)
            return BacktestRun(
                stock=stock, as_of_date=as_of_date,
                profile_bucket=profile.bucket, analysis_id=analysis_id,
                signal="neutral", raw_confidence=0.0,
                error=f"INSUFFICIENT_DATA: {exc}",
            )
        except Exception as exc:
            logger.warning("backtest: orchestrator error %s/%s — %s", stock, as_of_date, exc)
            return BacktestRun(
                stock=stock, as_of_date=as_of_date,
                profile_bucket=profile.bucket, analysis_id=analysis_id,
                signal="neutral", raw_confidence=0.0,
                error=str(exc),
            )

        run = BacktestRun(
            stock=stock, as_of_date=as_of_date,
            profile_bucket=profile.bucket, analysis_id=analysis_id,
            signal=signal, raw_confidence=raw_confidence,
        )

        if skip_outcome or signal in ("neutral", "mixed"):
            return run

        outcome = fetch_outcome(stock, as_of_date, horizon_days)
        if outcome is None:
            run.error = "outcome_unavailable"
            return run

        run.entry_price       = outcome["entry_price"]
        run.exit_price        = outcome["exit_price"]
        run.exit_date         = outcome["exit_date"]
        run.actual_return_pct = outcome["return_pct"]
        run.nifty_return_pct  = outcome["nifty_return_pct"]
        run.alpha_pct         = outcome["alpha_pct"]
        run.is_correct        = signal_is_correct(signal, outcome["return_pct"])

        logger.info(
            "backtest: %s/%s — signal=%s correct=%s ret=%.2f%% alpha=%.2f%%",
            stock, as_of_date, signal, run.is_correct,
            run.actual_return_pct or 0, run.alpha_pct or 0,
        )
        return run


# ── Public entry point ─────────────────────────────────────────────────────────

async def run_backtest(config: BacktestConfig) -> list[BacktestRun]:
    """
    Run the full backtest grid: len(stocks) × len(dates) analyses.

    Concurrency is capped at config.concurrency (default 3) to stay within
    LLM rate limits on the free tier. For a paid key, raise to 10–20.

    Returns list[BacktestRun] — includes failed runs with error field set.
    """
    total = len(config.stocks) * len(config.dates)
    logger.info(
        "backtest: starting %d stocks × %d dates = %d analyses (concurrency=%d)",
        len(config.stocks), len(config.dates), total, config.concurrency,
    )

    sem = asyncio.Semaphore(config.concurrency)
    tasks = [
        _run_one(stock, d, config.profile, config.horizon_days, config.skip_outcome, sem)
        for stock in config.stocks
        for d in config.dates
    ]

    runs = await asyncio.gather(*tasks)
    ok   = sum(1 for r in runs if r.error is None)
    logger.info("backtest: done — %d/%d succeeded", ok, total)
    return list(runs)
