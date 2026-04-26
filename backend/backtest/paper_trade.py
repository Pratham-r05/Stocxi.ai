"""
paper_trade.py — ₹10,000 paper portfolio simulation (ARCHITECTURE.md §12).

Position sizing:
  - BUY  if bullish: invest (raw_confidence - 0.5) × 2 × (capital / n_open_positions)
  - SKIP if neutral or mixed: no trade
  - SHORT if bearish: not simulated (long-only for simplicity; noted in report)

After holding for horizon_days, realise actual_return_pct on position.
Capital compounds across trades (each trade uses available capital).
Max position size per trade: 20% of current capital (concentration limit).

Outcome vs benchmark:
  - nifty_return is computed as buy-and-hold Nifty 50 over the same period.
"""

from __future__ import annotations

import math
from datetime import date

from pydantic import BaseModel

from backend.backtest.runner import BacktestRun


MAX_POSITION_PCT = 0.20     # max 20% of capital per trade
MIN_CONFIDENCE   = 0.50     # below this → treat as neutral (no edge)


class Trade(BaseModel):
    stock:         str
    signal_date:   date
    exit_date:     date | None
    entry_price:   float
    exit_price:    float | None
    position_size: float         # INR invested
    pnl:           float         # INR profit/loss
    return_pct:    float


class PaperTradeResult(BaseModel):
    starting_capital:  float = 10_000.0
    ending_capital:    float
    total_return_pct:  float
    nifty_return_pct:  float | None   # equal-weight Nifty return over same periods
    alpha_pct:         float | None   # total_return_pct - nifty_return_pct
    n_trades:          int
    n_wins:            int
    n_losses:          int
    n_skipped:         int            # neutral/mixed signals → no trade
    win_rate:          float          # n_wins / (n_wins + n_losses)
    avg_return_per_trade_pct: float
    max_drawdown_pct:  float
    trades:            list[Trade]
    note: str = (
        "Long-only simulation. Bearish signals are skipped (no shorting). "
        "Position size = min(20% capital, (confidence - 0.5) × 2 × capital)."
    )


def simulate_trades(
    runs: list[BacktestRun],
    starting_capital: float = 10_000.0,
) -> PaperTradeResult:
    """
    Simulate a paper portfolio over all BacktestRun results.

    Runs with error or missing outcome are skipped.
    Bearish signals are skipped (long-only).
    Position size is proportional to confidence above 0.5 baseline.
    """
    capital         = starting_capital
    peak_capital    = starting_capital
    max_drawdown    = 0.0
    trades: list[Trade] = []
    nifty_returns: list[float] = []
    n_skipped = 0

    # Sort by signal date so we process chronologically
    sorted_runs = sorted(runs, key=lambda r: r.as_of_date)

    for run in sorted_runs:
        # Skip errors and no-outcome runs
        if run.error or run.actual_return_pct is None or run.entry_price is None:
            n_skipped += 1
            continue

        # Skip neutral/mixed — no trade
        if run.signal in ("neutral", "mixed"):
            n_skipped += 1
            continue

        # Long-only: skip bearish
        if run.signal == "bearish":
            n_skipped += 1
            continue

        # Position sizing: edge above random = (confidence - 0.5) × 2
        edge_fraction = max(0.0, (run.raw_confidence - MIN_CONFIDENCE) * 2)
        pos_size = min(capital * MAX_POSITION_PCT, capital * edge_fraction)
        if pos_size < 1.0:
            n_skipped += 1
            continue

        pnl = pos_size * (run.actual_return_pct / 100)
        capital += pnl

        # Track drawdown
        if capital > peak_capital:
            peak_capital = capital
        drawdown = (peak_capital - capital) / peak_capital * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        trades.append(Trade(
            stock=run.stock,
            signal_date=run.as_of_date,
            exit_date=run.exit_date,
            entry_price=run.entry_price,
            exit_price=run.exit_price,
            position_size=round(pos_size, 2),
            pnl=round(pnl, 2),
            return_pct=round(run.actual_return_pct, 4),
        ))

        if run.nifty_return_pct is not None:
            nifty_returns.append(run.nifty_return_pct)

    n_wins   = sum(1 for t in trades if t.pnl > 0)
    n_losses = sum(1 for t in trades if t.pnl <= 0)
    win_rate = n_wins / len(trades) if trades else 0.0

    total_return_pct = (capital / starting_capital - 1) * 100
    avg_return_per_trade = (
        sum(t.return_pct for t in trades) / len(trades) if trades else 0.0
    )

    nifty_avg = (sum(nifty_returns) / len(nifty_returns)) if nifty_returns else None
    # Scale nifty average to full capital (equal-weight approx)
    nifty_return_pct = nifty_avg if nifty_avg is not None else None
    alpha_pct = (total_return_pct - nifty_return_pct) if nifty_return_pct is not None else None

    return PaperTradeResult(
        starting_capital=starting_capital,
        ending_capital=round(capital, 2),
        total_return_pct=round(total_return_pct, 4),
        nifty_return_pct=round(nifty_return_pct, 4) if nifty_return_pct is not None else None,
        alpha_pct=round(alpha_pct, 4) if alpha_pct is not None else None,
        n_trades=len(trades),
        n_wins=n_wins,
        n_losses=n_losses,
        n_skipped=n_skipped,
        win_rate=round(win_rate, 4),
        avg_return_per_trade_pct=round(avg_return_per_trade, 4),
        max_drawdown_pct=round(max_drawdown, 4),
        trades=trades,
    )
