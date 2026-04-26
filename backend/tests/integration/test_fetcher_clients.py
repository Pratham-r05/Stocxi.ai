"""
test_fetcher_clients.py — Integration tests for Phase 1 fetcher clients.

Tests live network calls against 3 canonical stocks:
  RELIANCE  — large cap, NSE+BSE, full data coverage
  IRCTC     — mid cap, NSE+BSE, government sector
  QUESTCAP  — small cap / NBFC, known screener standalone/consolidated edge case

Each test verifies:
  1. The call succeeds (no exception).
  2. The returned dict contains the expected top-level keys.
  3. Critical numeric fields are not None (e.g. price > 0).

Run with:
  cd stocxi
  python -m pytest backend/tests/integration/test_fetcher_clients.py -v

These tests hit live APIs — mark as slow / skip in CI if no network.
Set STOCXI_INTEGRATION=1 to enable; skipped by default.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

import pytest

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# ── Skip guard ────────────────────────────────────────────────────────────────
pytestmark = pytest.mark.skipif(
    os.getenv("STOCXI_INTEGRATION") != "1",
    reason="Integration tests require STOCXI_INTEGRATION=1 and live network",
)

TEST_STOCKS = ["RELIANCE", "IRCTC", "QUESTCAP"]
TODAY = date.today()
FROM_DATE = TODAY - timedelta(days=90)


# ── base.py ───────────────────────────────────────────────────────────────────

class TestWaterfallRunner:
    """Tests for WaterfallRunner in base.py."""

    @pytest.mark.asyncio
    async def test_waterfall_returns_first_ok(self):
        from backend.fetchers.base import waterfall, FetchResult

        async def good():
            return {"key": "value"}

        result = await waterfall.run([
            ("test_source", 1.0, good),
        ], request_id="test-001")

        assert result.ok is True
        assert result.source_id == "test_source"
        assert result.confidence == 1.0
        assert result.payload == {"key": "value"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_waterfall_skips_failed_levels(self):
        from backend.fetchers.base import waterfall, FetchResult

        call_order = []

        async def fail_src():
            call_order.append("fail")
            raise RuntimeError("intentional failure")

        async def ok_src():
            call_order.append("ok")
            return {"data": 42}

        result = await waterfall.run([
            ("failing_source", 0.5, fail_src),
            ("ok_source", 0.9, ok_src),
        ])

        assert result.ok is True
        assert result.source_id == "ok_source"
        assert call_order == ["fail", "ok"]

    @pytest.mark.asyncio
    async def test_waterfall_raises_when_all_fail(self):
        from backend.fetchers.base import waterfall, WaterfallFailure

        async def fail():
            raise ValueError("always fails")

        with pytest.raises(WaterfallFailure) as exc_info:
            await waterfall.run([
                ("src_a", 1.0, fail),
                ("src_b", 0.7, fail),
            ])

        assert len(exc_info.value.errors) == 2
        assert exc_info.value.errors[0][0] == "src_a"
        assert exc_info.value.errors[1][0] == "src_b"

    @pytest.mark.asyncio
    async def test_fetch_result_success_factory(self):
        from backend.fetchers.base import FetchResult

        r = FetchResult.success("nse_library", 1.0, {"a": 1}, request_id="r1")
        assert r.ok is True
        assert r.source_id == "nse_library"
        assert r.confidence == 1.0
        assert r.payload == {"a": 1}
        assert r.error is None
        assert r.request_id == "r1"

    @pytest.mark.asyncio
    async def test_fetch_result_failure_factory(self):
        from backend.fetchers.base import FetchResult

        r = FetchResult.failure("bse_library", 1.0, "timeout")
        assert r.ok is False
        assert r.payload is None
        assert r.error == "timeout"


# ── nse_client.py ─────────────────────────────────────────────────────────────

class TestNseClient:
    """Integration tests for nse_client.py — requires live NSE API."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", TEST_STOCKS)
    async def test_fetch_quote(self, symbol: str):
        from backend.fetchers import nse_client

        result = await nse_client.fetch_quote(symbol)

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol
        assert isinstance(result.get("close"), float)
        assert result["close"] > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["RELIANCE", "IRCTC"])
    async def test_fetch_ohlcv(self, symbol: str):
        from backend.fetchers import nse_client

        result = await nse_client.fetch_ohlcv(symbol, FROM_DATE, TODAY)

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol
        rows = result.get("rows", [])
        assert len(rows) > 10, f"Expected >10 OHLCV rows, got {len(rows)}"

        # Verify row structure
        row = rows[0]
        assert "date" in row
        assert isinstance(row.get("close"), float)
        assert row["close"] > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["RELIANCE", "TCS"])
    async def test_fetch_shareholding(self, symbol: str):
        from backend.fetchers import nse_client

        result = await nse_client.fetch_shareholding(symbol)

        assert isinstance(result, dict)
        # At minimum we expect promoter percentage
        assert "promoter" in result or "_raw" in result

    @pytest.mark.asyncio
    async def test_fetch_announcements_reliance(self):
        from backend.fetchers import nse_client

        result = await nse_client.fetch_announcements("RELIANCE")

        assert isinstance(result, dict)
        assert "items" in result
        # Items may be empty if no recent announcements — that's OK

    @pytest.mark.asyncio
    async def test_fetch_board_meetings_reliance(self):
        from backend.fetchers import nse_client

        result = await nse_client.fetch_board_meetings("RELIANCE")

        assert isinstance(result, dict)
        assert "meetings" in result

    @pytest.mark.asyncio
    async def test_fetch_actions_reliance(self):
        from backend.fetchers import nse_client

        result = await nse_client.fetch_actions("RELIANCE")

        assert isinstance(result, dict)
        assert "actions" in result


# ── bse_client.py ─────────────────────────────────────────────────────────────

class TestBseClient:
    """Integration tests for bse_client.py — requires live BSE API."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", TEST_STOCKS)
    async def test_resolve_scrip_code(self, symbol: str):
        from backend.fetchers import bse_client

        code = await bse_client.resolve_scrip_code(symbol)

        assert isinstance(code, str)
        assert code.isdigit(), f"BSE scrip code should be numeric, got '{code}'"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["RELIANCE", "IRCTC"])
    async def test_fetch_quote(self, symbol: str):
        from backend.fetchers import bse_client

        result = await bse_client.fetch_quote(symbol)

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol
        assert isinstance(result.get("close"), float)
        assert result["close"] > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["RELIANCE", "IRCTC"])
    async def test_fetch_meta_info(self, symbol: str):
        from backend.fetchers import bse_client

        result = await bse_client.fetch_meta_info(symbol)

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol
        # At least one ratio should be non-None
        ratio_keys = ["pe", "eps", "roe", "pb"]
        assert any(result.get(k) is not None for k in ratio_keys), \
            f"All fundamental ratios None for {symbol}: {result}"

    @pytest.mark.asyncio
    async def test_fetch_weekly_hl_reliance(self):
        from backend.fetchers import bse_client

        result = await bse_client.fetch_weekly_hl("RELIANCE")

        assert isinstance(result, dict)
        assert result.get("high_52w") is not None
        assert result.get("low_52w") is not None
        assert result["high_52w"] >= result["low_52w"]

    @pytest.mark.asyncio
    async def test_fetch_results_snapshot_reliance(self):
        from backend.fetchers import bse_client

        result = await bse_client.fetch_results_snapshot("RELIANCE")

        assert isinstance(result, dict)
        periods = result.get("periods", [])
        assert len(periods) > 0, "Expected at least 1 results period"

    @pytest.mark.asyncio
    async def test_fetch_result_calendar(self):
        from backend.fetchers import bse_client

        result = await bse_client.fetch_result_calendar()

        assert isinstance(result, dict)
        assert "events" in result
        # Calendar may be empty between quarters — that's OK


# ── screener_client.py ────────────────────────────────────────────────────────

class TestScreenerClient:
    """Integration tests for screener_client.py — requires live Screener.in access."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", TEST_STOCKS)
    async def test_fetch_financials_has_key_sections(self, symbol: str):
        from backend.fetchers import screener_client

        result = await screener_client.fetch_financials(symbol)

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol

        # At least quarterly results OR ratios should be present
        has_data = bool(result.get("quarterly_results")) or bool(result.get("ratios"))
        assert has_data, f"Screener returned no usable data for {symbol}"

    @pytest.mark.asyncio
    async def test_questcap_uses_freshest_page(self):
        """
        QUESTCAP is the canonical edge case — consolidated has Dec 2020 data
        while standalone has current quarterly results. Verify we pick standalone.
        """
        from backend.fetchers import screener_client

        result = await screener_client.fetch_financials("QUESTCAP")

        assert isinstance(result, dict)
        # source_url should NOT be the consolidated URL
        source_url = result.get("source_url") or ""
        assert "consolidated" not in source_url.lower() or source_url == "", \
            f"QUESTCAP should use standalone page, got: {source_url}"

    @pytest.mark.asyncio
    async def test_screener_raises_for_unknown_symbol(self):
        """Unknown symbols should raise ValueError (not silently return empty dict)."""
        from backend.fetchers import screener_client

        with pytest.raises(ValueError, match="no usable financial data"):
            await screener_client.fetch_financials("FAKESYMBOL999XYZ")


# ── yfinance_client.py ────────────────────────────────────────────────────────

class TestYfinanceClient:
    """Integration tests for yfinance_client.py — requires network access."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["RELIANCE", "IRCTC"])
    async def test_fetch_ohlcv(self, symbol: str):
        from backend.fetchers import yfinance_client

        result = await yfinance_client.fetch_ohlcv(symbol, FROM_DATE, TODAY)

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol
        rows = result.get("rows", [])
        assert len(rows) > 10, f"Expected >10 OHLCV rows, got {len(rows)}"
        assert result.get("ticker_used") is not None

        row = rows[0]
        assert row.get("close") is not None
        assert row["close"] > 0

    @pytest.mark.asyncio
    async def test_alt_ticker_zomato(self):
        """ZOMATO → ETERNAL.NS is in alt_tickers.yaml — verify fallback works."""
        from backend.fetchers import yfinance_client

        result = await yfinance_client.fetch_ohlcv("ZOMATO", FROM_DATE, TODAY)

        assert isinstance(result, dict)
        rows = result.get("rows", [])
        # Either ZOMATO.NS works OR ETERNAL.NS fallback kicked in
        assert len(rows) > 0, "ZOMATO OHLCV should return rows via alt ticker"

    @pytest.mark.asyncio
    async def test_raises_for_bogus_symbol(self):
        from backend.fetchers import yfinance_client

        with pytest.raises(ValueError):
            await yfinance_client.fetch_ohlcv("FAKESYMBOL999XYZ", FROM_DATE, TODAY)


# ── news_client.py ────────────────────────────────────────────────────────────

class TestNewsClient:
    """Integration tests for news_client.py — requires RSS feed access."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", ["RELIANCE", "TCS"])
    async def test_fetch_news_returns_items(self, symbol: str):
        from backend.fetchers import news_client

        result = await news_client.fetch_news(
            symbol=symbol,
            company_name="Reliance Industries" if symbol == "RELIANCE" else "Tata Consultancy",
            max_age_days=30,
            max_items=10,
        )

        assert isinstance(result, dict)
        assert result.get("symbol") == symbol
        assert "items" in result
        assert result.get("feeds_tried", 0) > 0

        # Each item must have required keys
        for item in result["items"]:
            assert "title" in item
            assert "source_id" in item
            assert "published_iso" in item

    @pytest.mark.asyncio
    async def test_fetch_news_no_html_in_items(self):
        """News items must not contain raw HTML tags."""
        from backend.fetchers import news_client
        import re

        result = await news_client.fetch_news("INFY", max_items=5)
        for item in result["items"]:
            assert not re.search(r"<[^>]+>", item.get("title", "")), \
                f"HTML found in title: {item['title']}"
            assert not re.search(r"<[^>]+>", item.get("summary", "")), \
                f"HTML found in summary: {item['summary']}"

    @pytest.mark.asyncio
    async def test_fetch_news_returns_empty_for_unknown(self):
        """Unknown symbols should return empty items, not raise."""
        from backend.fetchers import news_client

        result = await news_client.fetch_news("FAKESYMBOL999XYZ", max_items=5)

        assert result.get("items") == []
