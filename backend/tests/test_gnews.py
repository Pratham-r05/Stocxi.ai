"""
test_gnews.py — Test gnews as a news source for Indian stocks.

Status: TESTING (2026-04-27)
gnews wraps Google News RSS with a clean Python API.
Pros: Free, no API key, India filter, decent coverage.
Cons: No full article content (Google News redirect URLs), title+description only.

Run:  conda run -n stocxi python backend/tests/test_gnews.py
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from gnews import GNews

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

TEST_STOCKS = [
    ("RELIANCE", "Reliance Industries"),
    ("TCS", "Tata Consultancy Services"),
    ("HDFCBANK", "HDFC Bank"),
    ("INFY", "Infosys"),
    ("BAJAJFINSV", "Bajaj Finserv"),
    ("NESTLEIND", "Nestle India"),
    ("TATACHEM", "Tata Chemicals"),
]

MAX_ARTICLES = 10
MAX_AGE_DAYS = 7

# ── Relevance filter (same as news_service.py) ───────────────────────────────

_NAME_STOPWORDS: frozenset[str] = frozenset([
    "limited", "ltd", "india", "group", "co", "company", "plc",
    "bank", "finance", "financial", "services", "technologies", "tech",
    "industries", "industry", "enterprises", "holdings", "ventures",
    "corp", "corporation", "international", "global",
])


def _is_relevant(title: str, symbol: str, company_name: str) -> bool:
    """Check if headline is about the target stock."""
    low = title.lower()
    sym = symbol.lower()

    if re.search(r"\b" + re.escape(sym) + r"\b", low):
        return True

    if company_name:
        core_words = [
            w for w in company_name.lower().split()
            if len(w) >= 4 and w not in _NAME_STOPWORDS
        ]
        if not core_words:
            return False
        check = core_words[:2]
        return all(re.search(r"\b" + re.escape(w) + r"\b", low) for w in check)

    return False


# ── Signal classifier ─────────────────────────────────────────────────────────

_CLASS_KEYWORDS: list[tuple[str, list[str]]] = [
    ("regulatory_sebi_action", ["sebi", "penalty", "investigation", "ban"]),
    ("fraud_allegation",       ["fraud", "scam", "irregularity", "manipulation"]),
    ("credit_rating_change",   ["downgrade", "upgrade", "crisil", "icra", "credit rating"]),
    ("leadership_change",      ["ceo", "cfo", "managing director", "resignation", "appoints"]),
    ("ma_event",               ["merger", "acquisition", "takeover", "demerger"]),
    ("major_contract",         ["bags order", "wins contract", "secures deal", "order win"]),
    ("dividend_or_buyback",    ["dividend", "buyback", "bonus share"]),
    ("earnings_result",        ["quarterly results", "q4", "q3", "eps", "profit", "revenue"]),
    ("analyst_action",         ["analyst", "target price", "brokerage", "buy rating", "sell rating"]),
]


def _classify(title: str) -> str:
    low = title.lower()
    for cls, keywords in _CLASS_KEYWORDS:
        if any(kw in low for kw in keywords):
            return cls
    pos = {"profit", "growth", "record", "strong", "beat", "surge", "rally", "rise", "gain"}
    neg = {"loss", "decline", "fall", "miss", "drop", "cut", "penalty", "plunge"}
    words = set(re.findall(r"\b\w+\b", low))
    if len(words & pos) > len(words & neg):
        return "generic_positive"
    if len(words & neg) > len(words & pos):
        return "generic_negative"
    return "generic_neutral"


# ── Test functions ────────────────────────────────────────────────────────────

def test_gnews_fetch() -> dict[str, Any]:
    """Test gnews fetch for all test stocks."""
    print("\n" + "=" * 70)
    print("TEST 1: gnews fetch (India, English, 7 days)")
    print("=" * 70)

    gn = GNews(language="en", country="India", max_results=MAX_ARTICLES, period="7d")
    results = {}

    for symbol, company_name in TEST_STOCKS:
        # Search with company name for better relevance
        query = f"{symbol} {company_name}" if company_name else symbol
        articles = gn.get_news(query)

        # Filter for relevance
        relevant = [a for a in articles if _is_relevant(a.get("title", ""), symbol, company_name)]

        results[symbol] = {
            "raw_count": len(articles),
            "relevant_count": len(relevant),
            "articles": relevant,
        }

        print(f"\n  {symbol:15s} → {len(articles):2d} raw, {len(relevant):2d} relevant")
        for art in relevant[:3]:
            title = art.get("title", "")[:70]
            pub = art.get("published date", "N/A")
            src = art.get("publisher", {}).get("title", "N/A")
            print(f"    • [{src}] {title}...")
            print(f"      {pub}")

    total_relevant = sum(r["relevant_count"] for r in results.values())
    total_raw = sum(r["raw_count"] for r in results.values())
    print(f"\n  Totals: {total_raw} raw → {total_relevant} relevant across {len(TEST_STOCKS)} stocks")

    return results


def test_data_quality(results: dict[str, Any]) -> None:
    """Check what fields gnews provides vs what the pipeline needs."""
    print("\n" + "=" * 70)
    print("TEST 2: Data quality check")
    print("=" * 70)

    # Pick first article with content
    sample = None
    for sym, data in results.items():
        if data["articles"]:
            sample = data["articles"][0]
            break

    if not sample:
        print("  No articles to inspect")
        return

    print("\n  gnews article fields:")
    for k, v in sample.items():
        val = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
        print(f"    {k:20s}: {val}")

    print("\n  Pipeline requirements vs gnews:")
    print("    title          : ✓ (present)")
    print("    description    : ✓ (present, but often duplicates title)")
    print("    content        : ✗ (NOT available — Google News redirect URLs)")
    print("    link/url       : ✓ (present, but Google News redirect)")
    print("    published date : ✓ (present)")
    print("    publisher      : ✓ (present with name + href)")
    print("    source_id      : ✗ (not provided, needs to be set manually)")
    print("    sentiment      : ✗ (not provided)")

    print("\n  Gap: No article body content.")
    print("  Impact: LLM summarization works with title+description only.")
    print("  This is the SAME limitation as Google News RSS (existing L2 fallback).")


def test_signal_classification(results: dict[str, Any]) -> None:
    """Classify signal types across all fetched articles."""
    print("\n" + "=" * 70)
    print("TEST 3: Signal classification")
    print("=" * 70)

    class_counts: dict[str, int] = {}
    for sym, data in results.items():
        for art in data["articles"]:
            title = art.get("title", "")
            cls = _classify(title)
            class_counts[cls] = class_counts.get(cls, 0) + 1

    print("\n  Signal class distribution:")
    for cls, count in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f"    {cls:30s}: {count}")

    high_signal = sum(
        class_counts.get(c, 0)
        for c in ["earnings_result", "regulatory_sebi_action", "ma_event",
                   "leadership_change", "credit_rating_change", "major_contract"]
    )
    total = sum(class_counts.values())
    print(f"\n  High-signal articles: {high_signal}/{total} ({100*high_signal/max(total,1):.0f}%)")


def test_format_comparison() -> None:
    """Compare gnews vs newsdata.io vs Google News RSS."""
    print("\n" + "=" * 70)
    print("TEST 4: Source comparison")
    print("=" * 70)

    print("""
  ┌─────────────────┬────────────┬──────────────┬────────────────┐
  │ Field           │ newsdata.io│ gnews        │ Google RSS     │
  ├─────────────────┼────────────┼──────────────┼────────────────┤
  │ title           │ ✓          │ ✓            │ ✓              │
  │ description     │ ✓ (rich)   │ ~ (often dup)│ ~ (variable)   │
  │ content         │ ✓ (partial)│ ✗            │ ✗              │
  │ link            │ ✓ (direct) │ ~ (redirect) │ ~ (redirect)   │
  │ pubDate         │ ✓          │ ✓            │ ✓              │
  │ source_name     │ ✓          │ ✓ (publisher)│ ✓ (source tag) │
  │ source_id       │ ✓          │ ✗ (manual)   │ ✗ (manual)     │
  │ sentiment       │ ✓ (paid)   │ ✗            │ ✗              │
  │ API key needed  │ YES (free) │ NO           │ NO             │
  │ Rate limit      │ 200/day    │ None*        │ None*          │
  │ India coverage  │ Good       │ Good         │ Inconsistent   │
  │ Confidence      │ 0.80       │ ~0.50-0.70   │ 0.50           │
  └─────────────────┴────────────┴──────────────┴────────────────┘
  * Google may rate-limit if too many rapid requests
    """)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  GNEWS NEWS SOURCE TEST                                         ║")
    print("║  Testing gnews as replacement/addition for newsdata.io          ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    results = test_gnews_fetch()
    test_data_quality(results)
    test_signal_classification(results)
    test_format_comparison()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_relevant = sum(r["relevant_count"] for r in results.values())
    stocks_with_news = sum(1 for r in results.values() if r["relevant_count"] > 0)

    print(f"  Stocks with news: {stocks_with_news}/{len(TEST_STOCKS)}")
    print(f"  Total relevant articles: {total_relevant}")
    print()
    print("  Verdict:")
    if stocks_with_news >= 5 and total_relevant >= 20:
        print("  ✓ gnews is a VIABLE news source for Indian stocks")
        print("  ✓ Can be used as L1 or L2 in the news pipeline")
        print("  ✗ No article body content (same as Google News RSS)")
        print("  ✗ Google News redirect URLs (not direct publisher links)")
    elif stocks_with_news >= 3:
        print("  ~ gnews has PARTIAL coverage for Indian stocks")
        print("  ~ Could supplement but not replace newsdata.io")
    else:
        print("  ✗ gnews has POOR coverage — not viable as primary source")


if __name__ == "__main__":
    main()
