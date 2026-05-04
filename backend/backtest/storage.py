"""
storage.py — JSONL persistence for backtest runs and reports.

Backtest results are the input for Milestone 6 (calibration/refit_weights.py).
Each run is saved as one JSON object per line in a dated JSONL file.

Layout:
    backend/backtest/results/
        {YYYY-MM-DD}_{run_id}.jsonl     ← one file per backtest run
        reports/
            {YYYY-MM-DD}_{run_id}.json  ← BacktestReport JSON

Append-only — never overwrite existing files.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backtest.runner import BacktestRun
    from backtest.metrics import BacktestReport

logger = logging.getLogger(__name__)

_BASE    = Path(__file__).parents[2] / "backtest" / "results"
_REPORTS = _BASE / "reports"


def _ensure_dirs() -> None:
    _BASE.mkdir(parents=True, exist_ok=True)
    _REPORTS.mkdir(parents=True, exist_ok=True)


def save_runs(runs: list[BacktestRun], run_id: str | None = None) -> Path:
    """
    Append all BacktestRuns to a JSONL file.

    Returns the Path of the written file.
    """
    _ensure_dirs()
    run_id  = run_id or datetime.utcnow().strftime("%H%M%S")
    today   = date.today().isoformat()
    path    = _BASE / f"{today}_{run_id}.jsonl"

    try:
        with path.open("a", encoding="utf-8") as fh:
            for run in runs:
                line = run.model_dump(mode="json")
                fh.write(json.dumps(line, default=str) + "\n")
        logger.info("storage: saved %d runs → %s", len(runs), path)
    except Exception as exc:
        logger.error("storage: failed to save runs — %s", exc)

    return path


def load_runs(path: Path) -> list[BacktestRun]:
    """Load all BacktestRuns from a JSONL file (for calibration input)."""
    from backtest.runner import BacktestRun

    runs: list[BacktestRun] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    runs.append(BacktestRun(**json.loads(line)))
    except Exception as exc:
        logger.error("storage: failed to load runs from %s — %s", path, exc)
    return runs


def save_report(report: BacktestReport, run_id: str | None = None) -> Path:
    """Save a BacktestReport as a JSON file."""
    _ensure_dirs()
    run_id = run_id or datetime.utcnow().strftime("%H%M%S")
    today  = date.today().isoformat()
    path   = _REPORTS / f"{today}_{run_id}.json"

    try:
        path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
        logger.info("storage: saved report → %s", path)
    except Exception as exc:
        logger.error("storage: failed to save report — %s", exc)

    return path


def list_run_files() -> list[Path]:
    """Return all JSONL run files, sorted by date (newest first)."""
    if not _BASE.exists():
        return []
    return sorted(_BASE.glob("*.jsonl"), reverse=True)
