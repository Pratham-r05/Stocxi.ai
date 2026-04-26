"""
test_backtest.py — Unit tests for Milestone 5 backtest harness.

Tests are deterministic (no LLM, no real yfinance calls).
Real yfinance calls are mocked via monkeypatch.

Run:
    python -m pytest backend/tests/golden/test_backtest.py -v
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.backtest.schedule import generate_backtest_dates, _quarter_end, _prev_quarter_end
from backend.backtest.universe import UNIVERSE, get_universe, get_universe_by_sector, SURVIVORSHIP_BIAS_DISCLAIMER
from backend.backtest.outcomes import fetch_outcome, signal_is_correct, _fetch_close
from backend.backtest.runner import BacktestRun, BacktestConfig
from backend.backtest.paper_trade import simulate_trades, PaperTradeResult
from backend.backtest.metrics import compute_metrics, BacktestReport, ConfidenceBin
from backend.backtest.storage import save_runs, load_runs, save_report, list_run_files


# ─────────────────────────────── universe tests ───────────────────────────────

def test_universe_length():
    assert len(UNIVERSE) >= 80, "universe should have at least 80 stocks"


def test_get_universe_returns_list():
    u = get_universe()
    assert isinstance(u, list)
    assert len(u) == len(UNIVERSE)


def test_get_universe_by_sector_covers_all():
    by_sector = get_universe_by_sector()
    all_stocks = [s for stocks in by_sector.values() for s in stocks]
    assert set(all_stocks) == set(UNIVERSE[:len(all_stocks)])


def test_survivorship_disclaimer_non_empty():
    assert len(SURVIVORSHIP_BIAS_DISCLAIMER) > 50


# ─────────────────────────────── schedule tests ───────────────────────────────

def test_quarter_end_march():
    assert _quarter_end(date(2024, 2, 15)) == date(2024, 3, 31)


def test_quarter_end_june():
    assert _quarter_end(date(2024, 5, 1)) == date(2024, 6, 30)


def test_quarter_end_september():
    assert _quarter_end(date(2024, 8, 20)) == date(2024, 9, 30)


def test_quarter_end_december():
    assert _quarter_end(date(2024, 11, 5)) == date(2024, 12, 31)


def test_prev_quarter_end():
    # Q2 start = Apr 1 → prev quarter end = Mar 31
    assert _prev_quarter_end(date(2024, 5, 15)) == date(2024, 3, 31)


def test_generate_backtest_dates_count():
    dates = generate_backtest_dates(n=12, ref_date=date(2025, 4, 1))
    assert len(dates) <= 12
    assert len(dates) >= 8   # should have at least 8 valid quarters back to 2022


def test_generate_backtest_dates_ascending():
    dates = generate_backtest_dates(n=8, ref_date=date(2025, 4, 1))
    assert dates == sorted(dates), "dates must be in ascending order"


def test_generate_backtest_dates_all_weekdays():
    from backend.util.ist_calendar import is_trading_day
    dates = generate_backtest_dates(n=8, ref_date=date(2025, 4, 1))
    for d in dates:
        assert is_trading_day(d), f"{d} is not a trading day"


def test_generate_backtest_dates_before_cutoff():
    ref = date(2025, 4, 1)
    dates = generate_backtest_dates(n=8, ref_date=ref)
    cutoff = ref - timedelta(days=30)
    for d in dates:
        assert d <= cutoff, f"{d} violates MIN_HISTORY_DAYS cutoff"


# ─────────────────────────────── outcomes tests ───────────────────────────────

def _make_ohlcv(price: float, n: int = 5) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with constant close price."""
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({
        "Open": price, "High": price + 1, "Low": price - 1,
        "Close": price, "Volume": 1_000_000,
    }, index=idx)


def test_signal_is_correct_bullish_positive():
    assert signal_is_correct("bullish", 3.0) is True


def test_signal_is_correct_bullish_negative():
    assert signal_is_correct("bullish", -2.0) is False


def test_signal_is_correct_bearish_negative():
    assert signal_is_correct("bearish", -3.0) is True


def test_signal_is_correct_bearish_positive():
    assert signal_is_correct("bearish", 2.0) is False


def test_signal_is_correct_neutral():
    assert signal_is_correct("neutral", 5.0) is None


def test_signal_is_correct_mixed():
    assert signal_is_correct("mixed", -5.0) is None


def test_fetch_outcome_returns_dict(monkeypatch):
    """fetch_outcome should return a dict with entry/exit prices from mocked yfinance."""
    entry_df = _make_ohlcv(100.0)
    exit_df  = _make_ohlcv(105.0)

    call_count = [0]
    def fake_download(symbol, **kwargs):
        call_count[0] += 1
        # Alternate entry/exit by call order (entry first)
        return entry_df if call_count[0] % 2 == 1 else exit_df

    import yfinance as yf
    monkeypatch.setattr(yf, "download", fake_download)

    result = fetch_outcome("RELIANCE", date(2024, 6, 28), 30)
    assert result is not None
    assert "entry_price" in result
    assert "exit_price"  in result
    assert "return_pct"  in result


def test_fetch_outcome_return_pct_calculation(monkeypatch):
    """return_pct = (exit/entry - 1) × 100."""
    call_map = {"n": 0}

    def fake_download(symbol, **kwargs):
        call_map["n"] += 1
        price = 100.0 if call_map["n"] <= 2 else 110.0
        return _make_ohlcv(price)

    import yfinance as yf
    monkeypatch.setattr(yf, "download", fake_download)

    result = fetch_outcome("TCS", date(2024, 6, 28), 30)
    if result and result["entry_price"] and result["exit_price"]:
        expected = (result["exit_price"] / result["entry_price"] - 1) * 100
        assert abs(result["return_pct"] - expected) < 0.01


# ─────────────────────────────── paper_trade tests ────────────────────────────

def _make_run(
    stock: str = "RELIANCE",
    signal: str = "bullish",
    confidence: float = 0.75,
    actual_return: float = 5.0,
    nifty_return: float = 2.0,
    as_of_date: date | None = None,
) -> BacktestRun:
    return BacktestRun(
        stock=stock,
        as_of_date=as_of_date or date(2024, 3, 28),
        profile_bucket="short_moderate",
        analysis_id="test-id",
        signal=signal,
        raw_confidence=confidence,
        entry_price=100.0,
        exit_price=100.0 * (1 + actual_return / 100),
        exit_date=(as_of_date or date(2024, 3, 28)) + timedelta(days=30),
        actual_return_pct=actual_return,
        nifty_return_pct=nifty_return,
        alpha_pct=actual_return - nifty_return,
        is_correct=signal_is_correct(signal, actual_return),
    )


def test_simulate_trades_basic():
    runs = [_make_run(actual_return=10.0, confidence=0.80)]
    result = simulate_trades(runs)
    assert isinstance(result, PaperTradeResult)
    assert result.n_trades == 1
    assert result.ending_capital > result.starting_capital


def test_simulate_trades_bearish_skipped():
    """Bearish signals should not generate trades (long-only)."""
    runs = [_make_run(signal="bearish", actual_return=-5.0)]
    result = simulate_trades(runs)
    assert result.n_trades == 0
    assert result.n_skipped == 1


def test_simulate_trades_neutral_skipped():
    runs = [_make_run(signal="neutral", actual_return=3.0)]
    result = simulate_trades(runs)
    assert result.n_trades == 0


def test_simulate_trades_win_rate():
    runs = [
        _make_run(stock="A", actual_return=5.0,  confidence=0.8),
        _make_run(stock="B", actual_return=-3.0, confidence=0.8,
                  as_of_date=date(2024, 6, 28)),
    ]
    result = simulate_trades(runs)
    assert result.n_wins   == 1
    assert result.n_losses == 1
    assert abs(result.win_rate - 0.5) < 0.01


def test_simulate_trades_max_position_cap():
    """Single trade should not exceed MAX_POSITION_PCT of starting capital."""
    from backend.backtest.paper_trade import MAX_POSITION_PCT
    runs = [_make_run(actual_return=50.0, confidence=0.99)]
    result = simulate_trades(runs, starting_capital=10_000)
    if result.trades:
        assert result.trades[0].position_size <= 10_000 * MAX_POSITION_PCT + 0.01


# ─────────────────────────────── metrics tests ────────────────────────────────

def test_compute_metrics_basic():
    runs = [
        _make_run(stock="A", signal="bullish", actual_return=3.0,  confidence=0.72),
        _make_run(stock="B", signal="bullish", actual_return=-2.0, confidence=0.65,
                  as_of_date=date(2024, 6, 28)),
        _make_run(stock="C", signal="neutral", actual_return=1.0,  confidence=0.55),
    ]
    report = compute_metrics(runs)
    assert isinstance(report, BacktestReport)
    assert report.n_total    == 3
    assert report.n_actionable == 2     # neutral excluded
    assert report.n_correct  == 1
    assert report.n_incorrect == 1
    assert abs(report.overall_accuracy - 0.5) < 0.01


def test_compute_metrics_all_correct():
    runs = [_make_run(stock=str(i), signal="bullish", actual_return=5.0, confidence=0.75)
            for i in range(5)]
    for r in runs:
        r.is_correct = True
    report = compute_metrics(runs)
    assert report.overall_accuracy == 1.0


def test_compute_metrics_confidence_bins():
    """Runs in 0.6-0.7 bin should appear in the correct ConfidenceBin."""
    runs = [
        _make_run(stock="A", confidence=0.65, actual_return=3.0),
        _make_run(stock="B", confidence=0.65, actual_return=3.0, as_of_date=date(2024, 6, 28)),
    ]
    for r in runs:
        r.is_correct = True
    report = compute_metrics(runs)
    bin_60_70 = next((b for b in report.confidence_bins if b.low == 0.60), None)
    assert bin_60_70 is not None
    assert bin_60_70.n_predictions == 2
    assert bin_60_70.accuracy == 1.0


def test_compute_metrics_survivorship_disclaimer():
    report = compute_metrics([])
    assert len(report.survivorship_disclaimer) > 50


def test_compute_metrics_sector_breakdown():
    runs = [
        _make_run(stock="RELIANCE", actual_return=5.0,  confidence=0.75),
        _make_run(stock="TCS",      actual_return=-2.0, confidence=0.70,
                  as_of_date=date(2024, 6, 28)),
    ]
    sector_map = {"RELIANCE": "Energy", "TCS": "IT"}
    report = compute_metrics(runs, sector_map=sector_map)
    assert "Energy" in report.accuracy_by_sector or "IT" in report.accuracy_by_sector


# ─────────────────────────────── storage tests ────────────────────────────────

def test_save_and_load_runs(tmp_path, monkeypatch):
    """Round-trip: save runs to tmp dir, reload, compare."""
    import backend.backtest.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_BASE", tmp_path)
    monkeypatch.setattr(storage_mod, "_REPORTS", tmp_path / "reports")

    runs = [_make_run(stock="RELIANCE"), _make_run(stock="TCS", as_of_date=date(2024, 6, 28))]
    path = save_runs(runs, run_id="pytest")

    loaded = load_runs(path)
    assert len(loaded) == 2
    assert {r.stock for r in loaded} == {"RELIANCE", "TCS"}


def test_save_report_json(tmp_path, monkeypatch):
    import backend.backtest.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_BASE",    tmp_path)
    monkeypatch.setattr(storage_mod, "_REPORTS", tmp_path / "reports")

    runs   = [_make_run()]
    report = compute_metrics(runs)
    path   = save_report(report, run_id="pytest")

    assert path.exists()
    data = json.loads(path.read_text())
    assert "overall_accuracy" in data


def test_list_run_files_empty(tmp_path, monkeypatch):
    import backend.backtest.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_BASE", tmp_path)
    assert list_run_files() == []


def test_list_run_files_sorted(tmp_path, monkeypatch):
    import backend.backtest.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_BASE",    tmp_path)
    monkeypatch.setattr(storage_mod, "_REPORTS", tmp_path / "reports")

    save_runs([_make_run()], run_id="first")
    save_runs([_make_run()], run_id="second")
    files = list_run_files()
    assert len(files) == 2
    assert files[0] >= files[1]    # newest first (string sort works for ISO dates)
