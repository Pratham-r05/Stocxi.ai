"""
output_instructions.py — Load horizon-specific output instruction .md files.

The analysis pipeline uses two sets of instruction files:
  1. 00_kg_shorthand_book.md — read BEFORE graph analysis (node reference + HFBP edges + signal rules)
  2. 01/02/03 horizon files   — read AFTER graph analysis (output format per investor horizon)

This module loads these files from the project root and caches them in memory.
Files are read once at module import; restart the process to pick up changes.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Project root ──────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parents[1].parent  # backend/analysis/ → stocxi/

# ── Instruction file paths ────────────────────────────────────────────────────

SHORTHAND_BOOK_PATH = _PROJECT_ROOT / "00_kg_shorthand_book.md"

HORIZON_FILE_MAP: dict[str, Path] = {
    "short":  _PROJECT_ROOT / "01_short_term_output.md",
    "medium": _PROJECT_ROOT / "02_medium_term_output.md",
    "long":   _PROJECT_ROOT / "03_long_term_output.md",
}

# ── In-memory cache (loaded once) ─────────────────────────────────────────────

_shorthand_cache: str | None = None
_horizon_cache: dict[str, str] = {}


def load_shorthand_book() -> str:
    """Load and cache 00_kg_shorthand_book.md. Read once, cache forever."""
    global _shorthand_cache
    if _shorthand_cache is not None:
        return _shorthand_cache

    if not SHORTHAND_BOOK_PATH.exists():
        logger.warning("output_instructions: shorthand book not found at %s", SHORTHAND_BOOK_PATH)
        _shorthand_cache = ""
        return ""

    _shorthand_cache = SHORTHAND_BOOK_PATH.read_text(encoding="utf-8")
    logger.info("output_instructions: loaded shorthand book (%d chars)", len(_shorthand_cache))
    return _shorthand_cache


def load_horizon_instructions(horizon: str) -> str:
    """Load and cache the horizon-specific output instruction file.

    Args:
        horizon: One of "short", "medium", "long".

    Returns:
        The .md file content as a string. Empty string if file not found.
    """
    if horizon in _horizon_cache:
        return _horizon_cache[horizon]

    path = HORIZON_FILE_MAP.get(horizon)
    if path is None:
        logger.warning("output_instructions: unknown horizon '%s'", horizon)
        _horizon_cache[horizon] = ""
        return ""

    if not path.exists():
        logger.warning("output_instructions: horizon file not found at %s", path)
        _horizon_cache[horizon] = ""
        return ""

    content = path.read_text(encoding="utf-8")
    _horizon_cache[horizon] = content
    logger.info("output_instructions: loaded %s horizon instructions (%d chars)", horizon, len(content))
    return content


def reload() -> None:
    """Force reload all instruction files from disk."""
    global _shorthand_cache
    _shorthand_cache = None
    _horizon_cache.clear()
    logger.info("output_instructions: cache cleared, files will reload on next access")