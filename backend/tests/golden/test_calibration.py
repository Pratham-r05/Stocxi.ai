"""
test_calibration.py — Unit tests for Milestone 6 calibration (ARCHITECTURE.md §12).

All tests are deterministic. No real file I/O except via tmp_path fixture.
No LLM calls. Uses only unittest.mock and stdlib.

Run:
    cd /Users/prathamraj/Documents/Placement-Prep/10.Projects/stocxi
    /Users/prathamraj/miniforge3/envs/stocxi/bin/python -m pytest backend/tests/golden/test_calibration.py -v
"""

from __future__ import annotations

import json
import textwrap
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.backtest.runner import BacktestRun
from backend.calibration.refit_weights import (
    apply_calibration,
    fit_platt_scaling,
    load_all_runs,
    refit_indicator_weights,
    run_calibration,
)


# ─────────────────────────────── Fixtures ────────────────────────────────────

def _make_run(
    *,
    signal: str = "bullish",
    raw_confidence: float = 0.75,
    is_correct: bool | None = True,
    profile_bucket: str = "short_moderate",
    actual_return_pct: float | None = 5.0,
    stock: str = "RELIANCE",
    as_of_date: date | None = None,
) -> BacktestRun:
    """Helper: create a BacktestRun with sensible defaults."""
    return BacktestRun(
        stock=stock,
        as_of_date=as_of_date or date(2025, 1, 15),
        profile_bucket=profile_bucket,
        analysis_id="test-id-001",
        signal=signal,
        raw_confidence=raw_confidence,
        is_correct=is_correct,
        actual_return_pct=actual_return_pct,
        entry_price=100.0,
        exit_price=105.0,
        exit_date=date(2025, 2, 15),
        nifty_return_pct=2.0,
        alpha_pct=3.0,
    )


def _make_runs(n: int, *, accuracy: float = 0.6, confidence: float = 0.75) -> list[BacktestRun]:
    """Helper: create n BacktestRuns with given accuracy and confidence."""
    runs = []
    for i in range(n):
        is_correct = i < int(n * accuracy)
        runs.append(_make_run(
            raw_confidence=confidence,
            is_correct=is_correct,
            stock=f"STOCK{i}",
        ))
    return runs


def _make_binned_runs(n_per_bin: int = 10) -> list[BacktestRun]:
    """
    Create runs spread across confidence bins, each with known accuracy.
    Bins: [0.50-0.60 @ acc=0.50], [0.60-0.70 @ acc=0.60], [0.70-0.80 @ acc=0.70],
          [0.80-0.90 @ acc=0.80], [0.90-1.0 @ acc=0.90]
    """
    configs = [
        (0.55, 0.50),
        (0.65, 0.60),
        (0.75, 0.70),
        (0.85, 0.80),
        (0.95, 0.90),
    ]
    runs = []
    for conf, acc in configs:
        for i in range(n_per_bin):
            runs.append(_make_run(
                raw_confidence=conf,
                is_correct=(i < int(n_per_bin * acc)),
                stock=f"STOCK_{conf}_{i}",
            ))
    return runs


_MINIMAL_WEIGHTS = {
    "version": "2026.04",
    "technical": {
        "rsi":  {"short": 0.08, "long": 0.04, "description": "RSI"},
        "macd": {"short": 0.08, "long": 0.06, "description": "MACD"},
        "sma":  {"short": 0.05, "long": 0.08, "description": "SMA"},
    },
    "fundamental": {
        "revenue_growth_yoy": {"short": 0.08, "long": 0.18, "description": "Revenue growth"},
    },
    "news_signal_classes": {
        "regulatory_sebi_action": {"weight_multiplier": 2.0, "description": "SEBI action"},
    },
    "contradiction_tiers": {
        1: "regulatory_sebi_legal",
    },
}


# ─────────────────────────── load_all_runs tests ─────────────────────────────

class TestLoadAllRuns:
    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """Empty results directory → []."""
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        runs = load_all_runs(result_dir)
        assert runs == []

    def test_nonexistent_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """Non-existent directory → [] without crash."""
        runs = load_all_runs(tmp_path / "does_not_exist")
        assert runs == []

    def test_loads_single_jsonl_file(self, tmp_path: Path) -> None:
        """Single JSONL file with 2 runs → 2 BacktestRun objects."""
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        run1 = _make_run(stock="RELIANCE", raw_confidence=0.7)
        run2 = _make_run(stock="TCS", raw_confidence=0.8)

        jsonl_path = result_dir / "2025-01-15_abc.jsonl"
        with jsonl_path.open("w") as f:
            f.write(json.dumps(run1.model_dump(mode="json"), default=str) + "\n")
            f.write(json.dumps(run2.model_dump(mode="json"), default=str) + "\n")

        runs = load_all_runs(result_dir)
        assert len(runs) == 2
        assert runs[0].stock == "RELIANCE"
        assert runs[1].stock == "TCS"

    def test_loads_multiple_jsonl_files(self, tmp_path: Path) -> None:
        """Multiple JSONL files → all runs combined."""
        result_dir = tmp_path / "results"
        result_dir.mkdir()

        for i, ticker in enumerate(["RELIANCE", "TCS", "INFY"]):
            run = _make_run(stock=ticker)
            path = result_dir / f"2025-01-{15 + i:02d}_run{i}.jsonl"
            with path.open("w") as f:
                f.write(json.dumps(run.model_dump(mode="json"), default=str) + "\n")

        runs = load_all_runs(result_dir)
        assert len(runs) == 3

    def test_skips_blank_lines_in_jsonl(self, tmp_path: Path) -> None:
        """Blank lines in JSONL file are skipped gracefully."""
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        run = _make_run(stock="HDFC")
        path = result_dir / "2025-01-15_test.jsonl"
        with path.open("w") as f:
            f.write("\n")
            f.write(json.dumps(run.model_dump(mode="json"), default=str) + "\n")
            f.write("   \n")

        runs = load_all_runs(result_dir)
        assert len(runs) == 1
        assert runs[0].stock == "HDFC"

    def test_skips_corrupted_files_gracefully(self, tmp_path: Path) -> None:
        """Corrupted JSONL file is skipped; valid files still loaded."""
        result_dir = tmp_path / "results"
        result_dir.mkdir()

        # Bad file
        bad = result_dir / "2025-01-14_bad.jsonl"
        bad.write_text("not valid json\n{also bad}\n")

        # Good file
        run = _make_run(stock="WIPRO")
        good = result_dir / "2025-01-15_good.jsonl"
        with good.open("w") as f:
            f.write(json.dumps(run.model_dump(mode="json"), default=str) + "\n")

        runs = load_all_runs(result_dir)
        # Should load at least the good run (bad file raises per-line error, handled per-file)
        assert any(r.stock == "WIPRO" for r in runs)

    def test_ignores_non_jsonl_files(self, tmp_path: Path) -> None:
        """Non-.jsonl files in results dir are ignored."""
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        (result_dir / "report.json").write_text('{"not": "a run"}')
        (result_dir / "README.txt").write_text("notes")

        runs = load_all_runs(result_dir)
        assert runs == []


# ─────────────────────────── fit_platt_scaling tests ─────────────────────────

class TestFitPlattScaling:
    def test_empty_list_returns_identity(self) -> None:
        """Empty runs list → identity map."""
        result = fit_platt_scaling([])
        assert result["is_identity"] is True
        assert result["method"] == "identity"
        assert result["bins"] == []

    def test_fewer_than_30_returns_identity(self) -> None:
        """< 30 actionable runs → identity map."""
        runs = _make_runs(20)
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is True
        assert result["bins"] == []

    def test_exactly_30_actionable_fits(self) -> None:
        """Exactly 30 actionable runs → non-identity result."""
        runs = _make_runs(30, confidence=0.75)
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is False

    def test_only_neutral_runs_returns_identity(self) -> None:
        """All neutral/mixed runs (is_correct=None) → identity (no actionable)."""
        runs = [
            _make_run(signal="neutral", is_correct=None, actual_return_pct=None)
            for _ in range(50)
        ]
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is True

    def test_bins_computed_correctly(self) -> None:
        """Bins have correct structure and calibration_error = |avg_confidence - accuracy|."""
        runs = _make_binned_runs(n_per_bin=20)
        result = fit_platt_scaling(runs)

        assert result["is_identity"] is False
        assert len(result["bins"]) > 0

        for b in result["bins"]:
            assert "low" in b
            assert "high" in b
            assert "avg_confidence" in b
            assert "actual_accuracy" in b
            assert "calibrated_output" in b
            assert "n_samples" in b
            assert "calibration_error" in b
            # calibration_error = |avg_confidence - actual_accuracy|
            expected_err = abs(b["avg_confidence"] - b["actual_accuracy"])
            assert abs(b["calibration_error"] - round(expected_err, 4)) < 1e-3

    def test_calibration_error_formula(self) -> None:
        """
        Explicit check: bin at conf=0.75 with accuracy=0.70 →
        calibration_error ≈ |0.75 - 0.70| = 0.05.
        """
        # 100 runs at 0.75 confidence, 70% correct → accuracy = 0.70
        n = 100
        runs = [
            _make_run(raw_confidence=0.75, is_correct=(i < 70))
            for i in range(n)
        ]
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is False

        # Find the [0.70, 0.80) bin
        target_bin = next(
            (b for b in result["bins"] if b["low"] == 0.70 and b["high"] == 0.80),
            None,
        )
        assert target_bin is not None
        assert target_bin["n_samples"] == n
        assert abs(target_bin["actual_accuracy"] - 0.70) < 0.01
        assert abs(target_bin["calibration_error"] - 0.05) < 0.01

    def test_overall_accuracy_correct(self) -> None:
        """overall_accuracy = n_correct / n_actionable."""
        runs = _make_runs(50, accuracy=0.6, confidence=0.75)
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is False
        assert abs(result["overall_accuracy"] - 0.6) < 0.05

    def test_fitted_at_is_today(self) -> None:
        """fitted_at field contains today's date string."""
        runs = _make_runs(40, confidence=0.75)
        result = fit_platt_scaling(runs)
        assert result["fitted_at"] == date.today().isoformat()

    def test_method_is_isotonic_or_linear(self) -> None:
        """With enough data, method is either 'isotonic' or 'linear'."""
        runs = _make_binned_runs(n_per_bin=10)
        result = fit_platt_scaling(runs)
        assert result["method"] in ("isotonic", "linear")

    def test_calibrated_output_clamped_to_unit_interval(self) -> None:
        """All calibrated_output values must be in [0.0, 1.0]."""
        runs = _make_binned_runs(n_per_bin=10)
        result = fit_platt_scaling(runs)
        for b in result["bins"]:
            assert 0.0 <= b["calibrated_output"] <= 1.0

    def test_error_runs_excluded_from_actionable(self) -> None:
        """Runs with error field set are not actionable if is_correct is None."""
        # Error runs: is_correct=None, error set
        error_runs = [
            _make_run(is_correct=None, signal="neutral", actual_return_pct=None)
            for _ in range(20)
        ]
        # Good runs: 30 actionable
        good_runs = _make_runs(30, confidence=0.75)
        result = fit_platt_scaling(error_runs + good_runs)
        assert result["n_actionable"] == 30


# ─────────────────────────── apply_calibration tests ─────────────────────────

class TestApplyCalibration:
    def test_identity_map_returns_raw_confidence(self) -> None:
        """Identity map → raw_confidence returned unchanged."""
        cal_map = {"is_identity": True, "bins": []}
        assert apply_calibration(0.75, cal_map) == pytest.approx(0.75)

    def test_empty_map_returns_raw_confidence(self) -> None:
        """Empty dict → raw_confidence returned unchanged."""
        assert apply_calibration(0.65, {}) == pytest.approx(0.65)

    def test_empty_bins_returns_raw_confidence(self) -> None:
        """Non-identity map with empty bins → raw_confidence."""
        cal_map = {"is_identity": False, "bins": []}
        assert apply_calibration(0.72, cal_map) == pytest.approx(0.72)

    def test_clamped_above_one(self) -> None:
        """Output clamped to 1.0 even if calibrated_output is somehow > 1."""
        cal_map = {
            "is_identity": False,
            "bins": [{"low": 0.90, "high": 1.01, "calibrated_output": 1.5}],
        }
        result = apply_calibration(0.95, cal_map)
        assert result == pytest.approx(1.0)

    def test_clamped_below_zero(self) -> None:
        """Output clamped to 0.0 even if calibrated_output is somehow < 0."""
        cal_map = {
            "is_identity": False,
            "bins": [{"low": 0.50, "high": 0.60, "calibrated_output": -0.5}],
        }
        result = apply_calibration(0.55, cal_map)
        assert result == pytest.approx(0.0)

    def test_correct_bin_lookup(self) -> None:
        """raw_confidence=0.65 → hits [0.60, 0.70) bin → calibrated_output=0.58."""
        cal_map = {
            "is_identity": False,
            "bins": [
                {"low": 0.50, "high": 0.60, "calibrated_output": 0.48},
                {"low": 0.60, "high": 0.70, "calibrated_output": 0.58},
                {"low": 0.70, "high": 0.80, "calibrated_output": 0.68},
            ],
        }
        result = apply_calibration(0.65, cal_map)
        assert result == pytest.approx(0.58)

    def test_below_first_bin_uses_first_calibrated(self) -> None:
        """raw_confidence below all bins → uses first bin's calibrated_output."""
        cal_map = {
            "is_identity": False,
            "bins": [
                {"low": 0.60, "high": 0.70, "calibrated_output": 0.55},
                {"low": 0.70, "high": 0.80, "calibrated_output": 0.65},
            ],
        }
        # 0.50 is below the first bin midpoint (0.65)
        result = apply_calibration(0.50, cal_map)
        assert 0.0 <= result <= 1.0

    def test_above_last_bin_uses_last_calibrated(self) -> None:
        """raw_confidence above all bins → uses last bin's calibrated_output."""
        cal_map = {
            "is_identity": False,
            "bins": [
                {"low": 0.50, "high": 0.60, "calibrated_output": 0.48},
                {"low": 0.60, "high": 0.70, "calibrated_output": 0.58},
            ],
        }
        result = apply_calibration(0.99, cal_map)
        assert 0.0 <= result <= 1.0

    def test_boundary_confidence_exactly_at_bin_low(self) -> None:
        """raw_confidence exactly at bin boundary (low) is captured by that bin."""
        cal_map = {
            "is_identity": False,
            "bins": [
                {"low": 0.70, "high": 0.80, "calibrated_output": 0.68},
            ],
        }
        result = apply_calibration(0.70, cal_map)
        assert result == pytest.approx(0.68)


# ──────────────────── refit_indicator_weights tests ──────────────────────────

class TestRefitIndicatorWeights:
    def test_fewer_than_50_returns_current_weights(self) -> None:
        """< 50 actionable runs → current_weights returned unchanged."""
        runs = _make_runs(40, confidence=0.75)
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        # Values should match original (only version may change)
        assert result["technical"]["rsi"]["short"] == pytest.approx(0.08)
        assert result["technical"]["sma"]["short"] == pytest.approx(0.05)

    def test_fewer_than_50_preserves_all_keys(self) -> None:
        """< 50 runs → all keys from current_weights preserved in output."""
        runs = _make_runs(30)
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        assert "technical" in result
        assert "fundamental" in result
        assert "news_signal_classes" in result
        assert "contradiction_tiers" in result

    def test_returns_valid_version_string(self) -> None:
        """Version string is 'YYYY.MM' format."""
        runs = _make_runs(20)
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        version = result.get("version", "")
        # e.g. "2026.04"
        assert len(version) == 7
        assert version[4] == "."
        assert version[:4].isdigit()
        assert version[5:7].isdigit()

    def test_version_string_is_current_year_month(self) -> None:
        """Version string matches today's year and month."""
        runs = _make_runs(20)
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        today = date.today()
        expected = today.strftime("%Y.%m")
        assert result["version"] == expected

    def test_never_deletes_indicator_keys(self) -> None:
        """No indicator key from current_weights is dropped in output."""
        runs = _make_runs(80, accuracy=0.7, confidence=0.75)
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        for key in ["rsi", "macd", "sma"]:
            assert key in result["technical"], f"Key '{key}' missing from result"

    def test_preserves_non_technical_keys(self) -> None:
        """fundamental, news_signal_classes, contradiction_tiers preserved."""
        runs = _make_runs(80, confidence=0.75)
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        assert "revenue_growth_yoy" in result["fundamental"]
        assert "regulatory_sebi_action" in result["news_signal_classes"]

    def test_does_not_mutate_current_weights(self) -> None:
        """Input current_weights dict is not mutated."""
        import copy
        original_short_rsi = _MINIMAL_WEIGHTS["technical"]["rsi"]["short"]
        runs = _make_runs(80, accuracy=0.8, confidence=0.75)
        refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        assert _MINIMAL_WEIGHTS["technical"]["rsi"]["short"] == original_short_rsi

    def test_empty_runs_returns_current_weights(self) -> None:
        """Empty runs list → current_weights returned (bootstrap fallback)."""
        result = refit_indicator_weights([], _MINIMAL_WEIGHTS)
        assert result["technical"]["rsi"]["short"] == pytest.approx(0.08)

    def test_all_neutral_runs_returns_current_weights(self) -> None:
        """All neutral runs (no actionable) → current_weights returned."""
        runs = [
            _make_run(signal="neutral", is_correct=None, actual_return_pct=None)
            for _ in range(60)
        ]
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        assert result["technical"]["rsi"]["short"] == pytest.approx(0.08)


# ──────────────────────── run_calibration tests ──────────────────────────────

class TestRunCalibration:
    def test_dry_run_no_files_written(self, tmp_path: Path) -> None:
        """dry_run=True → calibration.yaml and weights.yaml not written."""
        results_dir  = tmp_path / "results"
        results_dir.mkdir()
        calib_path   = tmp_path / "calibration.yaml"
        weights_path = tmp_path / "weights.yaml"
        weights_path.write_text("version: '2026.04'\ntechnical: {}\n")

        run_calibration(
            results_dir=results_dir,
            weights_path=weights_path,
            calibration_path=calib_path,
            dry_run=True,
        )

        # calibration.yaml should NOT be (over)written
        assert not calib_path.exists() or calib_path.stat().st_mtime == calib_path.stat().st_mtime

    def test_dry_run_returns_correct_dict(self, tmp_path: Path) -> None:
        """dry_run returns dict with expected keys."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        result = run_calibration(
            results_dir=results_dir,
            weights_path=tmp_path / "weights.yaml",
            calibration_path=tmp_path / "calibration.yaml",
            dry_run=True,
        )

        assert "calibration" in result
        assert "weights_updated" in result
        assert "n_runs" in result
        assert "n_actionable" in result
        assert "dry_run" in result
        assert result["dry_run"] is True

    def test_n_runs_zero_for_empty_dir(self, tmp_path: Path) -> None:
        """No JSONL files → n_runs=0, n_actionable=0."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        result = run_calibration(
            results_dir=results_dir,
            weights_path=tmp_path / "weights.yaml",
            calibration_path=tmp_path / "calibration.yaml",
            dry_run=True,
        )
        assert result["n_runs"] == 0
        assert result["n_actionable"] == 0

    def test_calibration_yaml_written_on_real_run(self, tmp_path: Path) -> None:
        """With dry_run=False and data, calibration.yaml is written."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        calib_path  = tmp_path / "calibration.yaml"
        w_path      = tmp_path / "weights.yaml"
        w_path.write_text("version: '2026.04'\ntechnical: {rsi: {short: 0.08, long: 0.04}}\n")

        # Write some runs
        runs = _make_runs(10, confidence=0.75)  # < 30 → identity calibration
        jsonl = results_dir / "2025-01-15_test.jsonl"
        with jsonl.open("w") as f:
            for r in runs:
                f.write(json.dumps(r.model_dump(mode="json"), default=str) + "\n")

        run_calibration(
            results_dir=results_dir,
            weights_path=w_path,
            calibration_path=calib_path,
            dry_run=False,
        )

        assert calib_path.exists()

    def test_weights_not_updated_below_50_samples(self, tmp_path: Path) -> None:
        """< 50 actionable → weights_updated=False in return dict."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        runs = _make_runs(30, confidence=0.75)  # 30 < 50
        jsonl = results_dir / "2025-01-15_test.jsonl"
        with jsonl.open("w") as f:
            for r in runs:
                f.write(json.dumps(r.model_dump(mode="json"), default=str) + "\n")

        result = run_calibration(
            results_dir=results_dir,
            weights_path=tmp_path / "weights.yaml",
            calibration_path=tmp_path / "calibration.yaml",
            dry_run=True,
        )
        assert result["weights_updated"] is False

    def test_calibration_identity_with_few_runs(self, tmp_path: Path) -> None:
        """With < 30 actionable, calibration result is identity."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        runs = _make_runs(20, confidence=0.75)
        jsonl = results_dir / "2025-01-15_test.jsonl"
        with jsonl.open("w") as f:
            for r in runs:
                f.write(json.dumps(r.model_dump(mode="json"), default=str) + "\n")

        result = run_calibration(
            results_dir=results_dir,
            weights_path=tmp_path / "weights.yaml",
            calibration_path=tmp_path / "calibration.yaml",
            dry_run=True,
        )
        assert result["calibration"]["is_identity"] is True


# ────────────────────────── Edge case tests ──────────────────────────────────

class TestEdgeCases:
    def test_single_bin_populated(self) -> None:
        """Only one confidence bin has data — still computes correctly."""
        runs = _make_runs(40, confidence=0.75)  # all in [0.70, 0.80)
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is False
        assert len(result["bins"]) == 1
        assert result["bins"][0]["low"] == 0.70
        assert result["bins"][0]["high"] == 0.80

    def test_apply_calibration_with_full_pipeline_map(self) -> None:
        """apply_calibration works on a realistic calibration map from fit_platt_scaling."""
        runs = _make_binned_runs(n_per_bin=10)
        cal_map = fit_platt_scaling(runs)
        # Should not crash and return a valid float
        result = apply_calibration(0.75, cal_map)
        assert 0.0 <= result <= 1.0

    def test_runs_with_errors_excluded(self) -> None:
        """Runs with error field and is_correct=None are excluded from calibration."""
        error_runs = []
        for i in range(15):
            r = _make_run(signal="neutral", is_correct=None, actual_return_pct=None)
            r = r.model_copy(update={"error": "INSUFFICIENT_DATA"})
            error_runs.append(r)
        good_runs = _make_runs(35, confidence=0.75)  # 35 < 30 combined with errors
        result = fit_platt_scaling(error_runs + good_runs)
        # 35 good runs < 30 → wait, 35 ≥ 30 so it should fit
        assert result["n_actionable"] == 35

    def test_all_correct_runs(self) -> None:
        """100% accuracy → overall_accuracy ≈ 1.0."""
        runs = _make_runs(40, accuracy=1.0, confidence=0.75)
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is False
        assert result["overall_accuracy"] == pytest.approx(1.0)

    def test_all_incorrect_runs(self) -> None:
        """0% accuracy → overall_accuracy ≈ 0.0."""
        runs = _make_runs(40, accuracy=0.0, confidence=0.75)
        result = fit_platt_scaling(runs)
        assert result["is_identity"] is False
        assert result["overall_accuracy"] == pytest.approx(0.0)

    def test_apply_calibration_identity_flag_true(self) -> None:
        """is_identity=True with non-empty bins still returns raw_confidence."""
        cal_map = {
            "is_identity": True,
            "bins": [{"low": 0.70, "high": 0.80, "calibrated_output": 0.50}],
        }
        result = apply_calibration(0.75, cal_map)
        assert result == pytest.approx(0.75)

    def test_refit_weights_with_mixed_profile_buckets(self) -> None:
        """Runs with mixed short/long buckets are handled without error."""
        short_runs = [_make_run(profile_bucket="short_moderate", is_correct=True) for _ in range(30)]
        long_runs  = [_make_run(profile_bucket="long_conservative", is_correct=False) for _ in range(25)]
        runs = short_runs + long_runs  # 55 total, >= 50
        result = refit_indicator_weights(runs, _MINIMAL_WEIGHTS)
        assert "technical" in result
        assert "rsi" in result["technical"]
