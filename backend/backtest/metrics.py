"""
metrics.py — Aggregate backtest runs into calibration-ready metrics (ARCHITECTURE.md §12).

Key output:
  - accuracy_by_confidence_bin: actual win rate per confidence bucket
  - calibration_error: |bin_midpoint - actual_accuracy| → input for Platt scaling (M6)
  - nifty_excess_return: alpha over benchmark
  - success_bar check: calibration error < 5pp AND alpha > 0

Neutral/mixed signals and error runs are excluded from accuracy stats.
"""

from __future__ import annotations

from pydantic import BaseModel

from backtest.runner import BacktestRun
from backtest.universe import SURVIVORSHIP_BIAS_DISCLAIMER


# ── Confidence bins for calibration ───────────────────────────────────────────

_BINS: list[tuple[float, float]] = [
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.80),
    (0.80, 0.90),
    (0.90, 1.01),
]


class ConfidenceBin(BaseModel):
    low:               float
    high:              float
    n_predictions:     int
    n_correct:         int
    accuracy:          float    # n_correct / n_predictions
    avg_confidence:    float    # mean raw_confidence in this bin
    calibration_error: float    # |avg_confidence - accuracy|


class BacktestReport(BaseModel):
    # Overall counts
    n_total:          int
    n_actionable:     int    # bullish + bearish (excludes neutral/mixed/error)
    n_correct:        int
    n_incorrect:      int
    overall_accuracy: float

    # Calibration
    confidence_bins:      list[ConfidenceBin]
    mean_calibration_error: float   # average |conf - accuracy| across bins
    passes_calibration:   bool      # all bins within ±5pp (ARCHITECTURE §12 success bar)

    # Benchmark
    mean_alpha_pct:       float | None   # average stock alpha vs Nifty
    pct_with_positive_alpha: float | None

    # Breakdowns
    accuracy_by_signal:   dict[str, float]   # "bullish": 0.65, "bearish": 0.58
    accuracy_by_bucket:   dict[str, float]   # "short_moderate": 0.62, ...
    accuracy_by_sector:   dict[str, float]   # populated only if sector info provided

    # Success check (ARCHITECTURE §12)
    passes_success_bar: bool

    survivorship_disclaimer: str = SURVIVORSHIP_BIAS_DISCLAIMER


def compute_metrics(
    runs: list[BacktestRun],
    sector_map: dict[str, str] | None = None,   # {stock: sector}
) -> BacktestReport:
    """
    Aggregate list[BacktestRun] into BacktestReport.

    Args:
        runs:       Output of run_backtest()
        sector_map: Optional {nse_symbol: sector_label} for sector breakdown
    """
    actionable = [
        r for r in runs
        if r.is_correct is not None          # has a definitive outcome
        and r.actual_return_pct is not None
    ]

    n_correct   = sum(1 for r in actionable if r.is_correct)
    n_incorrect = sum(1 for r in actionable if not r.is_correct)
    overall_acc = n_correct / len(actionable) if actionable else 0.0

    # ── Confidence bins ────────────────────────────────────────────────────────
    bins: list[ConfidenceBin] = []
    for lo, hi in _BINS:
        bucket = [r for r in actionable if lo <= r.raw_confidence < hi]
        if not bucket:
            continue
        n_c    = sum(1 for r in bucket if r.is_correct)
        acc    = n_c / len(bucket)
        avg_c  = sum(r.raw_confidence for r in bucket) / len(bucket)
        cal_err = abs(avg_c - acc)
        bins.append(ConfidenceBin(
            low=lo, high=hi,
            n_predictions=len(bucket), n_correct=n_c,
            accuracy=round(acc, 4), avg_confidence=round(avg_c, 4),
            calibration_error=round(cal_err, 4),
        ))

    mean_cal_err = (sum(b.calibration_error for b in bins) / len(bins)) if bins else 0.0
    passes_cal   = all(b.calibration_error <= 0.05 for b in bins)

    # ── Alpha stats ────────────────────────────────────────────────────────────
    alphas = [r.alpha_pct for r in actionable if r.alpha_pct is not None]
    mean_alpha        = sum(alphas) / len(alphas) if alphas else None
    pct_pos_alpha     = (sum(1 for a in alphas if a > 0) / len(alphas)) if alphas else None

    # ── By-signal breakdown ────────────────────────────────────────────────────
    acc_by_signal: dict[str, float] = {}
    for sig in ("bullish", "bearish"):
        grp = [r for r in actionable if r.signal == sig]
        if grp:
            acc_by_signal[sig] = round(sum(1 for r in grp if r.is_correct) / len(grp), 4)

    # ── By-profile-bucket breakdown ────────────────────────────────────────────
    acc_by_bucket: dict[str, float] = {}
    buckets_seen = {r.profile_bucket for r in actionable}
    for b in buckets_seen:
        grp = [r for r in actionable if r.profile_bucket == b]
        if grp:
            acc_by_bucket[b] = round(sum(1 for r in grp if r.is_correct) / len(grp), 4)

    # ── By-sector breakdown ────────────────────────────────────────────────────
    acc_by_sector: dict[str, float] = {}
    if sector_map:
        sectors_seen = set(sector_map.values())
        for sec in sectors_seen:
            grp = [r for r in actionable if sector_map.get(r.stock) == sec]
            if grp:
                acc_by_sector[sec] = round(sum(1 for r in grp if r.is_correct) / len(grp), 4)

    passes_success = (
        passes_cal
        and mean_alpha is not None
        and mean_alpha > 0
    )

    return BacktestReport(
        n_total=len(runs),
        n_actionable=len(actionable),
        n_correct=n_correct,
        n_incorrect=n_incorrect,
        overall_accuracy=round(overall_acc, 4),
        confidence_bins=bins,
        mean_calibration_error=round(mean_cal_err, 4),
        passes_calibration=passes_cal,
        mean_alpha_pct=round(mean_alpha, 4) if mean_alpha is not None else None,
        pct_with_positive_alpha=round(pct_pos_alpha, 4) if pct_pos_alpha is not None else None,
        accuracy_by_signal=acc_by_signal,
        accuracy_by_bucket=acc_by_bucket,
        accuracy_by_sector=acc_by_sector,
        passes_success_bar=passes_success,
    )
