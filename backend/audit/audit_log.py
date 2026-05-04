"""
audit_log.py — Immutable Append-Only Audit Log.

ARCHITECTURE §10 requirement:
  Every production analysis writes one row here.
  Rows are NEVER mutated after writing.
  Retained 7 years (legal defensibility).

Row schema:
  analysis_id, stock, profile_hash, as_of_date, data_hash, prompt_version,
  weight_version, model_id, full_input_nodes_json, full_prompt, full_raw_output,
  final_output, conflicts_resolved, created_at_ist

Storage (v1): JSONL file at backend/audit/runs/{YYYY-MM-DD}.jsonl
  — one JSON object per line, never re-opened for editing.
  — In production, this is replaced by Postgres append-only table.
  — The JSONL format matches the Postgres row shape for easy migration.

In production, set AUDIT_BACKEND env var to "postgres" to use the DB writer.
For now, the JSONL file writer is the canonical implementation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Storage path ───────────────────────────────────────────────────────────────

_AUDIT_DIR = Path(__file__).parent / "runs"


def _today_log_path() -> Path:
    from util.ist_calendar import now_ist
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today = now_ist().strftime("%Y-%m-%d")
    return _AUDIT_DIR / f"{today}.jsonl"


# ── Hash helpers ───────────────────────────────────────────────────────────────

def compute_data_hash(node_ids: list[str]) -> str:
    """SHA-256 of sorted node_id list. Deterministic cache key component."""
    canon = json.dumps(sorted(node_ids), separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def compute_profile_hash(profile_bucket: str) -> str:
    """Short hash of the profile bucket string."""
    return hashlib.sha256(profile_bucket.encode()).hexdigest()[:8]


# ── Row builder ────────────────────────────────────────────────────────────────

def build_row(
    *,
    analysis_id: str,
    stock: str,
    profile_bucket: str,
    as_of_date: str,
    node_ids: list[str],
    prompt_version: str,
    weight_version: str,
    model_id: str,
    input_nodes_json: str,       # full JSON of the node list sent to LLM
    full_prompt: str,            # rendered Jinja prompt (the actual string sent)
    full_raw_output: str,        # raw LLM response string (before JSON parsing)
    final_output: dict[str, Any], # AnalysisResult.model_dump()
    admin_view: dict[str, Any],   # full admin view dict from formatter
    conflicts_resolved: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a complete audit row dict."""
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "analysis_id":         analysis_id,
        "stock":               stock.upper(),
        "profile_bucket":      profile_bucket,
        "profile_hash":        compute_profile_hash(profile_bucket),
        "as_of_date":          as_of_date,
        "data_hash":           compute_data_hash(node_ids),
        "prompt_version":      prompt_version,
        "weight_version":      weight_version,
        "model_id":            model_id,
        "input_nodes_json":    input_nodes_json,
        "full_prompt":         full_prompt,
        "full_raw_output":     full_raw_output,
        "final_output":        final_output,
        "admin_view":          admin_view,
        "conflicts_resolved":  conflicts_resolved or [],
        "created_at_ist":      now_utc,  # stored as UTC ISO; label matches schema doc
    }


# ── Writer ─────────────────────────────────────────────────────────────────────

def write_row(row: dict[str, Any]) -> None:
    """
    Append one audit row to today's JSONL file.
    Atomic write — each row ends with newline.
    Never raises (audit failures must not crash analysis pipeline).
    """
    try:
        path = _today_log_path()
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        logger.debug("audit_log: wrote row %s to %s", row.get("analysis_id"), path.name)
    except Exception as e:
        logger.error("audit_log: FAILED to write row %s — %s", row.get("analysis_id"), e)


# ── Public API ─────────────────────────────────────────────────────────────────

def log_analysis(
    *,
    analysis_id: str,
    stock: str,
    profile_bucket: str,
    as_of_date: str,
    node_ids: list[str],
    prompt_version: str,
    weight_version: str,
    model_id: str,
    input_nodes_json: str,
    full_prompt: str,
    full_raw_output: str,
    final_output: dict[str, Any],
    admin_view: dict[str, Any],
    conflicts_resolved: list[dict] | None = None,
) -> str:
    """
    Build and write one audit row. Returns the data_hash for the cache key.
    Swallows all exceptions so audit failures never crash the pipeline.
    """
    row = build_row(
        analysis_id=analysis_id,
        stock=stock,
        profile_bucket=profile_bucket,
        as_of_date=as_of_date,
        node_ids=node_ids,
        prompt_version=prompt_version,
        weight_version=weight_version,
        model_id=model_id,
        input_nodes_json=input_nodes_json,
        full_prompt=full_prompt,
        full_raw_output=full_raw_output,
        final_output=final_output,
        admin_view=admin_view,
        conflicts_resolved=conflicts_resolved,
    )
    write_row(row)
    return row["data_hash"]


def read_row(analysis_id: str, log_date: str | None = None) -> dict[str, Any] | None:
    """
    Read one audit row by analysis_id.
    Scans today's log (or log_date if provided). O(n) — for debug use only.
    Returns None if not found.
    """
    if log_date:
        paths = [_AUDIT_DIR / f"{log_date}.jsonl"]
    else:
        paths = sorted(_AUDIT_DIR.glob("*.jsonl"), reverse=True)[:7]  # last 7 days

    for path in paths:
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if row.get("analysis_id") == analysis_id:
                        return row
        except Exception as e:
            logger.warning("audit_log: error reading %s — %s", path, e)
    return None
