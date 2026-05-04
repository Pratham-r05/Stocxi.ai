"""
refit_weights.py — Calibration and indicator weight refitting (ARCHITECTURE.md §12).

Quarterly job:
  1. load_all_runs()      — gather all backtest JSONL files
  2. fit_platt_scaling()  — isotonic/linear mapping from raw_confidence → actual accuracy
  3. refit_indicator_weights() — update weights using logistic regression proxy
  4. Write config/calibration.yaml and config/weights.yaml

Success bar (ARCHITECTURE §12):
  - Calibrated confidence within ±5pp of actual accuracy per bin
  - Nifty-excess return > 0 net of costs

Usage:
    from calibration.refit_weights import run_calibration
    result = run_calibration(dry_run=True)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

logger = logging.getLogger(__name__)

# ── Optional sklearn import ────────────────────────────────────────────────────
try:
    from sklearn.isotonic import IsotonicRegression
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    logger.info("calibration: sklearn not available; using numpy linear fallback")

# ── Default paths ──────────────────────────────────────────────────────────────
_RESULTS_DIR     = Path(__file__).parents[2] / "backtest" / "results"
_WEIGHTS_PATH    = Path(__file__).parents[2] / "config" / "weights.yaml"
_CALIB_PATH      = Path(__file__).parents[2] / "config" / "calibration.yaml"

# ── Confidence bins (mirrors metrics.py) ──────────────────────────────────────
_BINS: list[tuple[float, float]] = [
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.80),
    (0.80, 0.90),
    (0.90, 1.01),
]

# Momentum indicator names that get bumped when short-term accuracy is high
_MOMENTUM_INDICATORS = {"rsi", "macd", "stochastic", "williams_r", "roc"}

# Minimum samples thresholds
_MIN_PLATT   = 30   # below this, return identity calibration map
_MIN_REFIT   = 50   # below this, keep current weights unchanged


# ── Public API ─────────────────────────────────────────────────────────────────

def load_all_runs(results_dir: Path | None = None) -> list:
    """
    Load all JSONL run files from backend/backtest/results/.
    Returns [] if no files found or on any error.
    """
    from backtest.runner import BacktestRun

    base = results_dir or _RESULTS_DIR
    runs: list[BacktestRun] = []

    try:
        if not base.exists():
            logger.info("calibration: results dir does not exist yet — %s", base)
            return []

        files = sorted(base.glob("*.jsonl"), reverse=True)
        logger.info("calibration: found %d JSONL files in %s", len(files), base)

        for path in files:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            runs.append(BacktestRun(**json.loads(line)))
            except Exception as exc:
                logger.warning("calibration: skipping %s — %s", path, exc)

    except Exception as exc:
        logger.error("calibration: load_all_runs error — %s", exc)

    logger.info("calibration: loaded %d total runs", len(runs))
    return runs


def fit_platt_scaling(runs: list) -> dict:
    """
    Fit isotonic regression (or linear fallback) from raw_confidence → actual accuracy.
    Uses only actionable runs (is_correct is not None).

    Returns dict with:
        method: "identity" | "isotonic" | "linear"
        bins: list of bin dicts
        overall_accuracy: float
        fitted_at: str (ISO date)
        is_identity: bool (True when < MIN_PLATT samples)
    """
    today = date.today().isoformat()

    # Filter to actionable runs only (bullish/bearish with known outcome)
    actionable = [r for r in runs if r.is_correct is not None]

    if len(actionable) < _MIN_PLATT:
        logger.info(
            "calibration: only %d actionable runs (< %d) — returning identity map",
            len(actionable), _MIN_PLATT,
        )
        return {
            "method": "identity",
            "bins": [],
            "overall_accuracy": None,
            "fitted_at": today,
            "is_identity": True,
            "n_actionable": len(actionable),
        }

    # ── Compute per-bin statistics ─────────────────────────────────────────────
    overall_correct = sum(1 for r in actionable if r.is_correct)
    overall_acc     = overall_correct / len(actionable)

    bin_stats: list[dict] = []
    for lo, hi in _BINS:
        bucket = [r for r in actionable if lo <= r.raw_confidence < hi]
        if not bucket:
            continue

        n_correct     = sum(1 for r in bucket if r.is_correct)
        accuracy      = n_correct / len(bucket)
        avg_confidence = sum(r.raw_confidence for r in bucket) / len(bucket)
        calibration_error = abs(avg_confidence - accuracy)

        bin_stats.append({
            "low":              lo,
            "high":             hi,
            "avg_confidence":   round(avg_confidence, 4),
            "actual_accuracy":  round(accuracy, 4),
            "n_samples":        len(bucket),
            "calibration_error": round(calibration_error, 4),
            # calibrated_output will be filled after fitting
        })

    # ── Fit isotonic / linear mapping ─────────────────────────────────────────
    if len(bin_stats) >= 2:
        x_vals = np.array([b["avg_confidence"] for b in bin_stats])
        y_vals = np.array([b["actual_accuracy"] for b in bin_stats])

        if _SKLEARN_AVAILABLE:
            try:
                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(x_vals, y_vals)
                calibrated = iso.predict(x_vals).tolist()
                method = "isotonic"
            except Exception as exc:
                logger.warning("calibration: isotonic fit failed (%s) — using linear", exc)
                calibrated = _linear_fit_predict(x_vals, y_vals)
                method = "linear"
        else:
            calibrated = _linear_fit_predict(x_vals, y_vals)
            method = "linear"
    else:
        # Only one bin — no interpolation possible, use accuracy directly
        calibrated = [b["actual_accuracy"] for b in bin_stats]
        method = "linear"

    # Attach calibrated_output to each bin
    for i, b in enumerate(bin_stats):
        b["calibrated_output"] = round(float(np.clip(calibrated[i], 0.0, 1.0)), 4)

    return {
        "method": method,
        "bins": bin_stats,
        "overall_accuracy": round(overall_acc, 4),
        "fitted_at": today,
        "is_identity": False,
        "n_actionable": len(actionable),
    }


def refit_indicator_weights(
    runs: list,
    current_weights: dict,
    sector_map: dict[str, str] | None = None,
) -> dict:
    """
    Fit logistic regression proxy to estimate indicator importance per horizon.

    Since BacktestRun doesn't store per-indicator feature vectors, this uses
    profile_bucket (horizon proxy) + accuracy-based scaling to adjust weights.

    If < 50 actionable runs, returns current_weights unchanged (bootstrap fallback).

    Returns new weights dict (same structure as weights.yaml, updated version string).
    Version string: "YYYY.MM" based on today's date.
    NEVER deletes any indicator from the dict.
    """
    import copy

    actionable = [r for r in runs if r.is_correct is not None]

    today = date.today()
    version_str = today.strftime("%Y.%m")

    if len(actionable) < _MIN_REFIT:
        logger.info(
            "calibration: only %d actionable runs (< %d) — keeping current weights",
            len(actionable), _MIN_REFIT,
        )
        # Return a deep copy with updated version string
        new_weights = copy.deepcopy(current_weights)
        new_weights["version"] = version_str
        return new_weights

    # ── Split by horizon (short vs long) ──────────────────────────────────────
    short_runs = [r for r in actionable if "short" in r.profile_bucket]
    long_runs  = [r for r in actionable if "long"  in r.profile_bucket]

    short_acc = (
        sum(1 for r in short_runs if r.is_correct) / len(short_runs)
        if short_runs else 0.0
    )
    long_acc = (
        sum(1 for r in long_runs if r.is_correct) / len(long_runs)
        if long_runs else 0.0
    )

    logger.info(
        "calibration: short_acc=%.3f (n=%d), long_acc=%.3f (n=%d)",
        short_acc, len(short_runs), long_acc, len(long_runs),
    )

    # ── Compute scaling ratios ────────────────────────────────────────────────
    # Baseline: 0.5 accuracy = neutral (no scaling)
    # If accuracy > 0.6, bump momentum indicators proportionally
    # Cap scaling at ±20% to avoid runaway weights
    short_scale = _compute_momentum_scale(short_acc)
    long_scale  = _compute_momentum_scale(long_acc)

    new_weights = _deep_copy_weights(current_weights)
    new_weights["version"] = version_str

    # ── Apply scaling to technical indicators ─────────────────────────────────
    technical = new_weights.get("technical", {})
    for indicator, cfg in technical.items():
        if not isinstance(cfg, dict):
            continue
        if indicator in _MOMENTUM_INDICATORS:
            if "short" in cfg and short_scale != 1.0:
                cfg["short"] = round(float(cfg["short"]) * short_scale, 6)
            if "long" in cfg and long_scale != 1.0:
                cfg["long"] = round(float(cfg["long"]) * long_scale, 6)

    logger.info(
        "calibration: weights updated — short_scale=%.3f, long_scale=%.3f",
        short_scale, long_scale,
    )
    return new_weights


def apply_calibration(raw_confidence: float, calibration_map: dict) -> float:
    """
    Map raw_confidence to calibrated_confidence using stored calibration_map.

    Uses bin lookup with linear interpolation between bin midpoints.
    If no bins or identity mapping, returns raw_confidence unchanged.
    Clamps output to [0.0, 1.0].
    """
    # Guard: identity or empty
    if not calibration_map:
        return float(np.clip(raw_confidence, 0.0, 1.0))
    if calibration_map.get("is_identity", False):
        return float(np.clip(raw_confidence, 0.0, 1.0))

    bins = calibration_map.get("bins", [])
    if not bins:
        return float(np.clip(raw_confidence, 0.0, 1.0))

    # ── Exact bin lookup ───────────────────────────────────────────────────────
    for b in bins:
        lo = b.get("low", 0.0)
        hi = b.get("high", 1.01)
        if lo <= raw_confidence < hi:
            # Linear interpolation between this bin's midpoint and neighbors
            return float(np.clip(b.get("calibrated_output", raw_confidence), 0.0, 1.0))

    # ── Out-of-range: interpolate from bin midpoints ───────────────────────────
    midpoints   = [(b["low"] + b["high"]) / 2 for b in bins]
    calibrateds = [b.get("calibrated_output", (b["low"] + b["high"]) / 2) for b in bins]

    if raw_confidence <= midpoints[0]:
        return float(np.clip(calibrateds[0], 0.0, 1.0))
    if raw_confidence >= midpoints[-1]:
        return float(np.clip(calibrateds[-1], 0.0, 1.0))

    # Linear interpolation between nearest midpoints
    for i in range(len(midpoints) - 1):
        if midpoints[i] <= raw_confidence <= midpoints[i + 1]:
            t = (raw_confidence - midpoints[i]) / (midpoints[i + 1] - midpoints[i])
            interpolated = calibrateds[i] + t * (calibrateds[i + 1] - calibrateds[i])
            return float(np.clip(interpolated, 0.0, 1.0))

    return float(np.clip(raw_confidence, 0.0, 1.0))


def run_calibration(
    results_dir: Path | None = None,
    weights_path: Path | None = None,
    calibration_path: Path | None = None,
    sector_map: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Full calibration pipeline:
      1. load_all_runs()
      2. fit_platt_scaling()
      3. refit_indicator_weights()
      4. Write config/calibration.yaml (unless dry_run)
      5. Write updated config/weights.yaml (unless dry_run or < 50 samples)

    Returns dict with calibration results and status flags.
    """
    w_path = weights_path    or _WEIGHTS_PATH
    c_path = calibration_path or _CALIB_PATH

    # ── 1. Load runs ───────────────────────────────────────────────────────────
    all_runs  = load_all_runs(results_dir)
    n_runs    = len(all_runs)
    actionable = [r for r in all_runs if r.is_correct is not None]
    n_actionable = len(actionable)

    # ── 2. Fit calibration ─────────────────────────────────────────────────────
    calibration_result = fit_platt_scaling(all_runs)

    # ── 3. Load current weights and refit ─────────────────────────────────────
    current_weights: dict = {}
    try:
        if w_path.exists():
            current_weights = yaml.safe_load(w_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("calibration: could not load weights.yaml — %s", exc)

    weights_updated = False
    new_weights = refit_indicator_weights(all_runs, current_weights, sector_map)

    # Determine if weights actually changed (only update if >= MIN_REFIT)
    if n_actionable >= _MIN_REFIT:
        weights_updated = True

    # ── 4 & 5. Write files ─────────────────────────────────────────────────────
    if not dry_run:
        _write_calibration_yaml(c_path, calibration_result, n_runs, n_actionable)
        if weights_updated:
            _write_weights_yaml(w_path, new_weights)
    else:
        logger.info("calibration: dry_run=True — skipping file writes")

    return {
        "calibration":    calibration_result,
        "weights_updated": weights_updated,
        "n_runs":         n_runs,
        "n_actionable":   n_actionable,
        "dry_run":        dry_run,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _linear_fit_predict(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Simple linear regression y = a + b*x, used as sklearn fallback."""
    if len(x) < 2:
        return y.tolist()
    try:
        # np.polyfit returns [b, a] for degree=1
        coeffs = np.polyfit(x, y, 1)
        predicted = np.polyval(coeffs, x)
        return predicted.tolist()
    except Exception:
        return y.tolist()


def _compute_momentum_scale(accuracy: float) -> float:
    """
    Compute multiplicative scale factor for momentum indicators.
    accuracy > 0.6 → scale > 1.0 (bump); accuracy < 0.5 → scale < 1.0 (dampen).
    Clamped to [0.80, 1.20] to avoid runaway weights.
    """
    if accuracy <= 0.0:
        return 1.0
    # Linear scale: 0.5 accuracy = 1.0 scale; 1.0 accuracy = 1.2 scale; 0.0 = 0.8
    scale = 0.8 + (accuracy * 0.4)  # at acc=0.5 → 1.0; at acc=1.0 → 1.2; at acc=0.0 → 0.8
    return float(np.clip(scale, 0.80, 1.20))


def _deep_copy_weights(weights: dict) -> dict:
    """Deep copy a nested dict (weights.yaml structure). Preserves ALL keys."""
    import copy
    return copy.deepcopy(weights)


def _write_calibration_yaml(path: Path, calibration: dict, n_runs: int, n_actionable: int) -> None:
    """Write calibration results to YAML file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()

        doc = {
            "version":         f"{date.today().strftime('%Y.%m')}.a",
            "method":          calibration.get("method", "identity"),
            "is_identity":     calibration.get("is_identity", True),
            "fitted_at":       calibration.get("fitted_at") if not calibration.get("is_identity") else None,
            "n_runs_used":     n_runs,
            "n_actionable":    n_actionable,
            "overall_accuracy": calibration.get("overall_accuracy"),
            "bins":            calibration.get("bins", []),
        }

        header = (
            "# calibration.yaml — Platt/isotonic scaling map (raw_confidence → calibrated_confidence)\n"
            "# Generated by: backend/calibration/refit_weights.py\n"
            "# Updated: quarterly after each backtest run\n"
            "# Format: bins list; apply_calibration() in refit_weights.py uses this at inference\n\n"
        )
        path.write_text(header + yaml.dump(doc, default_flow_style=False, allow_unicode=True), encoding="utf-8")
        logger.info("calibration: wrote calibration.yaml → %s", path)
    except Exception as exc:
        logger.error("calibration: failed to write calibration.yaml — %s", exc)


def _write_weights_yaml(path: Path, weights: dict) -> None:
    """Write updated weights to YAML, preserving all keys."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# weights.yaml — Signal weight table (auto-updated by calibration)\n"
            "# RULE: After v1, only updated by backend/calibration/refit_weights.py\n"
            "#       Never hand-edit this file.\n\n"
        )
        path.write_text(header + yaml.dump(weights, default_flow_style=False, allow_unicode=True), encoding="utf-8")
        logger.info("calibration: wrote weights.yaml → %s", path)
    except Exception as exc:
        logger.error("calibration: failed to write weights.yaml — %s", exc)
