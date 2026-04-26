"""
sanitizer.py — Scrub node values before they enter any LLM prompt.

Two jobs:
  1. HTML / injection safety  — strip tags, scripts, imperative sentences
  2. Identity anonymization   — replace identifying tokens with neutral placeholders
                                so the LLM cannot guess the stock from context clues

Called by every agent before setting node.sanitized = True.
The anonymization map (real → placeholder) is built once per analysis run
and passed back to the Formatter for de-anonymization in the final output.

Nothing in this module does IO. Pure functions, no external dependencies
beyond the stdlib re module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape


# ── Anonymization map ─────────────────────────────────────────────────────────

@dataclass
class AnonMap:
    """
    Holds the real→placeholder mapping for one analysis run.
    Built once by build_anon_map(), used by scrub_text(), reversed by restore_text().
    """
    stock: str                          # real ticker, e.g. RELIANCE
    stock_token: str = "STOCK_A"

    sector: str = ""
    sector_token: str = "SECTOR_X"

    # extra_names: list of (real_name, placeholder) tuples
    # e.g. [("Mukesh Ambani", "PROMOTER_A"), ("Jio", "BRAND_A")]
    extra: list[tuple[str, str]] = field(default_factory=list)

    def all_pairs(self) -> list[tuple[str, str]]:
        """Return all (real, placeholder) pairs ordered longest-first to avoid partial replacement."""
        pairs = [(self.stock, self.stock_token)]
        # Also handle common variations (e.g. "Reliance Industries" alongside "RELIANCE")
        if self.sector:
            pairs.append((self.sector, self.sector_token))
        pairs.extend(self.extra)
        # Sort longest real-token first — prevents "Jio" replacing inside "Jio Financial"
        return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def build_anon_map(
    stock: str,
    sector: str = "",
    promoter_names: list[str] | None = None,
    exec_names: list[str] | None = None,
    brand_names: list[str] | None = None,
    subsidiary_names: list[str] | None = None,
    peer_names: list[str] | None = None,
) -> AnonMap:
    """
    Build the anonymization map for one analysis run.
    Call this once in the Orchestrator before passing nodes to the Analysis Agent.

    Args:
        stock:            NSE ticker, e.g. "RELIANCE"
        sector:           Sector string from user profile, e.g. "Energy & Oil"
        promoter_names:   List of promoter/owner names
        exec_names:       CEO, CFO, MD names
        brand_names:      Product/brand names (Jio, Reliance Retail)
        subsidiary_names: Subsidiary company names
        peer_names:       Top 3 peer company names

    Returns:
        AnonMap with all mappings ready.
    """
    extra: list[tuple[str, str]] = []

    _counter: dict[str, int] = {}

    def _next_token(prefix: str) -> str:
        _counter[prefix] = _counter.get(prefix, 0) + 1
        n = _counter[prefix] - 1
        # A–Z then AA–ZZ — never overflows to symbols
        if n < 26:
            suffix = chr(ord("A") + n)
        else:
            suffix = chr(ord("A") + (n // 26) - 1) + chr(ord("A") + (n % 26))
        return f"{prefix}_{suffix}"

    for name in (promoter_names or []):
        if name.strip():
            extra.append((name.strip(), _next_token("PROMOTER")))

    for name in (exec_names or []):
        if name.strip():
            extra.append((name.strip(), _next_token("EXEC")))

    for name in (brand_names or []):
        if name.strip():
            extra.append((name.strip(), _next_token("BRAND")))

    for name in (subsidiary_names or []):
        if name.strip():
            extra.append((name.strip(), _next_token("SUBSIDIARY")))

    for name in (peer_names or []):
        if name.strip():
            extra.append((name.strip(), _next_token("PEER")))

    return AnonMap(stock=stock, sector=sector, extra=extra)


# ── Text scrubbing ─────────────────────────────────────────────────────────────

# Patterns for imperative/injection sentences to strip from news bodies
_IMPERATIVE_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(previous|above|all|prior)\b"),
    re.compile(r"(?i)\bforget\s+(everything|all|the above)\b"),
    re.compile(r"(?i)\byou\s+(must|should|need to|have to)\s+buy\b"),
    re.compile(r"(?i)\b(buy|sell|invest)\s+now\b"),
    re.compile(r"(?i)\bclick\s+here\b"),
    re.compile(r"(?i)\bsubscribe\s+(now|today)\b"),
    re.compile(r"(?i)\bact\s+(fast|now|immediately|quickly)\b"),
    re.compile(r"(?i)\b(don't|do not)\s+(miss|wait)\b"),
    re.compile(r"(?i)\blimited\s+time\s+offer\b"),
]

# Market-cap bucket thresholds (in crores)
_MCAP_BUCKETS = [
    (500_000, "Mega-cap"),
    (100_000, "Large-cap"),
    (25_000,  "Mid-cap"),
    (0,       "Small-cap"),
]


def strip_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    text = unescape(text)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def strip_imperative_sentences(text: str) -> str:
    """Remove sentences containing injection / promotional language."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean = []
    for sentence in sentences:
        if not any(p.search(sentence) for p in _IMPERATIVE_PATTERNS):
            clean.append(sentence)
    return " ".join(clean)


def scrub_text(text: str, anon_map: AnonMap) -> str:
    """
    Apply identity anonymization to a piece of text.
    Replaces real names/tickers/brands with neutral placeholders.
    Case-insensitive, longest match first.
    """
    for real, placeholder in anon_map.all_pairs():
        if real:
            pattern = re.compile(re.escape(real), re.IGNORECASE)
            text = pattern.sub(placeholder, text)
    return text


def restore_text(text: str, anon_map: AnonMap) -> str:
    """
    Reverse anonymization — replace placeholders with real names.
    Uses longest-placeholder-first order to prevent partial matches
    (e.g. PROMOTER_AA replaced before PROMOTER_A).
    """
    pairs = sorted(anon_map.all_pairs(), key=lambda p: -len(p[1]))
    for real, placeholder in pairs:
        text = text.replace(placeholder, real)
    return text


def bucket_market_cap(value_cr: float) -> str:
    """Convert absolute market cap (crores) to a bucket string."""
    for threshold, label in _MCAP_BUCKETS:
        if value_cr >= threshold:
            return label
    return "Small-cap (<₹25k cr)"


def sanitize_node_value(value: str, anon_map: AnonMap) -> str:
    """
    Full sanitization pipeline for a node's display value.
    1. Strip HTML
    2. Remove imperative sentences
    3. Apply identity anonymization
    4. Wrap in safe delimiters for news bodies
    """
    value = strip_html(value)
    value = strip_imperative_sentences(value)
    value = scrub_text(value, anon_map)
    return value


def sanitize_news_body(body: str, anon_map: AnonMap, max_tokens: int = 400) -> str:
    """
    Sanitize a full news article body before it enters an LLM prompt.
    Truncates to max_tokens (approximate word count) and wraps in delimiters.
    """
    body = strip_html(body)
    body = strip_imperative_sentences(body)
    body = scrub_text(body, anon_map)

    # Approximate truncation by word count (1 token ≈ 0.75 words)
    words = body.split()
    max_words = int(max_tokens * 0.75)
    if len(words) > max_words:
        body = " ".join(words[:max_words]) + "…"

    return f"<<<NEWS_BODY_START>>>{body}<<<NEWS_BODY_END>>>"
