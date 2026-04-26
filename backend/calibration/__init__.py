"""
backend/calibration — Quarterly calibration and indicator weight refitting.

Public API:
    load_all_runs          — load all backtest JSONL run files
    fit_platt_scaling      — isotonic/linear mapping: raw_confidence → actual accuracy
    apply_calibration      — apply calibration map at inference time
    refit_indicator_weights — refit technical/fundamental weights from backtest outcomes
    run_calibration        — full pipeline (load → fit → write)

Usage:
    from backend.calibration import run_calibration
    result = run_calibration(dry_run=True)
"""

from backend.calibration.refit_weights import (
    load_all_runs,
    fit_platt_scaling,
    apply_calibration,
    refit_indicator_weights,
    run_calibration,
)

__all__ = [
    "load_all_runs",
    "fit_platt_scaling",
    "apply_calibration",
    "refit_indicator_weights",
    "run_calibration",
]
