"""
symbol_service.py - canonical ticker handling.

Use this at API/service boundaries before any provider call.
"""

from __future__ import annotations


SYMBOL_ALIASES: dict[str, str] = {
    "ZOMATO": "ETERNAL",
    # Tata Motors demerger: old ticker now maps to passenger vehicles.
    "TATAMOTORS": "TMPV",
}


def canonicalize_symbol(symbol: str) -> str:
    """Return active provider-compatible ticker."""
    normalized = symbol.upper().strip()
    return SYMBOL_ALIASES.get(normalized, normalized)
