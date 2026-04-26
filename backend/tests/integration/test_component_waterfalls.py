"""
test_component_waterfalls.py — Phase 2.8 integration tests for component services.

Verifies:
  1. Every service returns nodes with correct schema (source_id, confidence, node_type).
  2. Waterfall fallback triggers: L1 patched to raise → L2/L3 provides result.
  3. Coverage across large-cap (RELIANCE), mid-cap (IRCTC), and small-cap (QUESTCAP).

Stock selection rationale:
  RELIANCE  — large cap, NSE+BSE, all data always available
  IRCTC     — mid cap, NSE+BSE, government sector, strong shareholding data
  QUESTCAP  — small cap / NBFC, known Screener standalone/consolidated edge case

Run:
  cd stocxi
  STOCXI_INTEGRATION=1 python -m pytest backend/tests/integration/test_component_waterfalls.py -v --asyncio-mode=auto

Skipped by default (requires live network + STOCXI_INTEGRATION=1).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# ── Skip guard ────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    os.getenv("STOCXI_INTEGRATION") != "1",
    reason="Integration tests require STOCXI_INTEGRATION=1 and live network",
)

# ── Constants ─────────────────────────────────────────────────────────────────

LARGE_CAP   = "RELIANCE"
MID_CAP     = "IRCTC"
SMALL_CAP   = "QUESTCAP"
TEST_STOCKS = [LARGE_CAP, MID_CAP, SMALL_CAP]
AS_OF       = date.today()

from backend.schemas.messages import UserProfile, Horizon, Risk

PROFILE = UserProfile(horizon=Horizon.short, risk=Risk.moderate)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_node_list(nodes: list, label: str = "") -> None:
    """Assert every element is a Node with required fields populated."""
    from backend.schemas.node import Node
    tag = f" for {label}" if label else ""
    assert isinstance(nodes, list), f"Expected list[Node], got {type(nodes)}"
    assert len(nodes) > 0, f"Node list is empty{tag}"
    for node in nodes:
        assert isinstance(node, Node), f"Item is not a Node: {node!r}"
        assert node.source, f"Node missing source{tag}: {node!r}"
        assert node.name, f"Node missing name{tag}: {node!r}"
        assert 0.0 < node.confidence <= 1.0, f"Bad confidence {node.confidence!r}{tag}: {node!r}"
        assert node.signal is not None, f"Node missing signal{tag}: {node!r}"
        assert node.weight >= 0.0, f"Node weight negative{tag}: {node!r}"
        assert node.as_of_date is not None, f"Node missing as_of_date{tag}: {node!r}"


# ═════════════════════════════════════════════════════════════════════════════
# 2.1  Price Service
# ═════════════════════════════════════════════════════════════════════════════

class TestPriceService:
    """Tests for backend/services/price_service.py — NSE → BSE → yfinance."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", TEST_STOCKS)
    async def test_get_price_returns_nodes(self, symbol: str) -> None:
        """get_price returns non-empty list[Node] with valid schema."""
        from backend.services.price_service import get_price
        nodes = await get_price(symbol, AS_OF, PROFILE, request_id=f"test:{symbol}")
        _assert_node_list(nodes, symbol)

    @pytest.mark.asyncio
    async def test_get_price_nodes_contain_price_node(self) -> None:
        """At least one node with name='Price' must be present."""
        from backend.services.price_service import get_price
        nodes = await get_price(LARGE_CAP, AS_OF, PROFILE)
        names = {n.name for n in nodes}
        assert "Price" in names, f"Price node missing. Got names: {names}"

    @pytest.mark.asyncio
    async def test_price_waterfall_fallback_to_bse(self) -> None:
        """When NSE equityQuote raises, BSE quote supplies the result."""
        from backend.services.price_service import get_price
        from backend.fetchers import nse_client

        with patch.object(nse_client, "fetch_quote", new=AsyncMock(side_effect=Exception("NSE down"))):
            nodes = await get_price(LARGE_CAP, AS_OF, PROFILE, request_id="test:fallback:price")

        assert len(nodes) > 0, "No nodes returned after NSE fallback"
        # When NSE is down, BSE should be the source
        sources = {n.source for n in nodes}
        assert "nse_library" not in sources, "NSE should not be source when mocked to fail"

    @pytest.mark.asyncio
    async def test_price_waterfall_fallback_to_yfinance(self) -> None:
        """When both NSE and BSE raise, yfinance supplies the result."""
        from backend.services.price_service import get_price
        from backend.fetchers import nse_client, bse_client

        with (
            patch.object(nse_client, "fetch_quote", new=AsyncMock(side_effect=Exception("NSE down"))),
            patch.object(bse_client, "fetch_quote", new=AsyncMock(side_effect=Exception("BSE down"))),
        ):
            nodes = await get_price(LARGE_CAP, AS_OF, PROFILE, request_id="test:fallback:price:yf")

        assert len(nodes) > 0, "No nodes returned after NSE+BSE fallback"
        sources = {n.source for n in nodes}
        assert "yfinance" in sources, f"Expected yfinance source, got {sources}"


# ═════════════════════════════════════════════════════════════════════════════
# 2.2  OHLCV Service
# ═════════════════════════════════════════════════════════════════════════════

class TestOhlcvService:
    """Tests for backend/services/ohlcv_service.py — NSE → yfinance."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", TEST_STOCKS)
    async def test_get_ohlcv_returns_dataframe(self, symbol: str) -> None:
        """get_ohlcv returns a non-empty DataFrame with standard OHLCV columns."""
        import pandas as pd
        from backend.services.ohlcv_service import get_ohlcv
        df = await get_ohlcv(symbol, AS_OF)
        assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
        assert not df.empty, f"OHLCV DataFrame empty for {symbol}"
        for col in ("Open", "High", "Low", "Close", "Volume"):
            assert col in df.columns, f"Missing column '{col}' for {symbol}: {list(df.columns)}"

    @pytest.mark.asyncio
    async def test_ohlcv_index_is_datetime(self) -> None:
        """DataFrame must have DatetimeIndex ascending."""
        import pandas as pd
        from backend.services.ohlcv_service import get_ohlcv
        df = await get_ohlcv(LARGE_CAP, AS_OF)
        assert isinstance(df.index, pd.DatetimeIndex), "Index must be DatetimeIndex"
        assert df.index.is_monotonic_increasing, "Index must be ascending"

    @pytest.mark.asyncio
    async def test_ohlcv_waterfall_fallback_to_yfinance(self) -> None:
        """When NSE historical fetch raises, yfinance supplies OHLCV."""
        import pandas as pd
        from backend.services.ohlcv_service import get_ohlcv
        from backend.fetchers import nse_client

        with patch.object(nse_client, "fetch_ohlcv", new=AsyncMock(side_effect=Exception("NSE OHLCV down"))):
            df = await get_ohlcv(LARGE_CAP, AS_OF)

        assert isinstance(df, pd.DataFrame)
        assert not df.empty, "OHLCV fallback to yfinance returned empty DataFrame"

    @pytest.mark.asyncio
    async def test_ohlcv_total_failure_returns_empty_dataframe(self) -> None:
        """When all sources fail, returns empty DataFrame without raising."""
        import pandas as pd
        from backend.services.ohlcv_service import get_ohlcv
        from backend.fetchers import nse_client, yfinance_client

        with (
            patch.object(nse_client, "fetch_ohlcv", new=AsyncMock(side_effect=Exception("NSE down"))),
            patch.object(yfinance_client, "fetch_ohlcv", new=AsyncMock(side_effect=Exception("yfinance down"))),
        ):
            df = await get_ohlcv(LARGE_CAP, AS_OF)

        assert isinstance(df, pd.DataFrame)
        assert df.empty, "Expected empty DataFrame on total OHLCV failure"


# ═════════════════════════════════════════════════════════════════════════════
# 2.3  Ratios Service
# ═════════════════════════════════════════════════════════════════════════════

class TestRatiosService:
    """Tests for backend/services/ratios_service.py — BSE → Screener."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", [LARGE_CAP, MID_CAP])
    async def test_get_ratios_returns_nodes(self, symbol: str) -> None:
        """get_ratios returns non-empty list[Node] with valid schema."""
        from backend.services.ratios_service import get_ratios
        nodes = await get_ratios(symbol, AS_OF, PROFILE)
        _assert_node_list(nodes, symbol)

    @pytest.mark.asyncio
    async def test_ratios_waterfall_fallback_to_screener(self) -> None:
        """When BSE equityMetaInfo raises, Screener top-ratios supplies data."""
        from backend.services.ratios_service import get_ratios
        from backend.fetchers import bse_client

        with patch.object(bse_client, "fetch_meta_info", new=AsyncMock(side_effect=Exception("BSE down"))):
            nodes = await get_ratios(LARGE_CAP, AS_OF, PROFILE, request_id="test:fallback:ratios")

        assert len(nodes) > 0, "No ratio nodes returned after BSE fallback"
        sources = {n.source for n in nodes}
        assert "screener_in" in sources, f"Expected screener_in source, got {sources}"

    @pytest.mark.asyncio
    async def test_ratios_total_failure_returns_empty_list(self) -> None:
        """When all ratio sources fail, returns [] without raising."""
        from backend.services.ratios_service import get_ratios
        from backend.fetchers import bse_client, screener_client

        with (
            patch.object(bse_client, "fetch_meta_info", new=AsyncMock(side_effect=Exception("BSE down"))),
            patch.object(screener_client, "fetch_financials", new=AsyncMock(side_effect=Exception("Screener down"))),
        ):
            nodes = await get_ratios(LARGE_CAP, AS_OF, PROFILE)

        assert nodes == [], f"Expected empty list, got {nodes}"


# ═════════════════════════════════════════════════════════════════════════════
# 2.4  Financials Service
# ═════════════════════════════════════════════════════════════════════════════

class TestFinancialsService:
    """Tests for backend/services/financials_service.py — Screener → BSE snapshot."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", TEST_STOCKS)
    async def test_get_financials_returns_nodes(self, symbol: str) -> None:
        """get_financials returns non-empty list[Node] with valid schema."""
        from backend.services.financials_service import get_financials
        nodes = await get_financials(symbol, AS_OF, PROFILE)
        _assert_node_list(nodes, symbol)

    @pytest.mark.asyncio
    async def test_financials_waterfall_fallback_to_bse(self) -> None:
        """When Screener raises, BSE resultsSnapshot provides financial data."""
        from backend.services.financials_service import get_financials
        from backend.fetchers import screener_client

        with patch.object(screener_client, "fetch_financials", new=AsyncMock(side_effect=Exception("Screener down"))):
            nodes = await get_financials(LARGE_CAP, AS_OF, PROFILE, request_id="test:fallback:financials")

        # BSE snapshot has limited periods but should still return something
        assert isinstance(nodes, list), "Expected list on screener fallback"
        sources = {n.source for n in nodes}
        if nodes:
            assert "bse_library" in sources, f"Expected bse_library source, got {sources}"

    @pytest.mark.asyncio
    async def test_financials_screener_preferred_over_bse(self) -> None:
        """Primary source for financials is Screener (higher recency coverage)."""
        from backend.services.financials_service import get_financials
        nodes = await get_financials(LARGE_CAP, AS_OF, PROFILE)
        sources = {n.source for n in nodes}
        # Screener wins for large caps — it should be in the source set
        assert "screener_in" in sources, f"Expected screener_in as primary, got {sources}"


# ═════════════════════════════════════════════════════════════════════════════
# 2.5  Shareholding Service
# ═════════════════════════════════════════════════════════════════════════════

class TestShareholdingService:
    """Tests for backend/services/shareholding_service.py — NSE → Screener."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", [LARGE_CAP, MID_CAP])
    async def test_get_shareholding_returns_nodes(self, symbol: str) -> None:
        """get_shareholding returns non-empty list[Node] with valid schema."""
        from backend.services.shareholding_service import get_shareholding
        nodes = await get_shareholding(symbol, AS_OF, PROFILE)
        _assert_node_list(nodes, symbol)

    @pytest.mark.asyncio
    async def test_shareholding_contains_promoter_node(self) -> None:
        """Promoter_Holding node must be present for large caps."""
        from backend.services.shareholding_service import get_shareholding
        nodes = await get_shareholding(LARGE_CAP, AS_OF, PROFILE)
        names = {n.name for n in nodes}
        assert "Promoter_Holding" in names, f"Promoter_Holding missing. Got names: {names}"

    @pytest.mark.asyncio
    async def test_shareholding_waterfall_fallback_to_screener(self) -> None:
        """When NSE shareholding raises, Screener provides the data."""
        from backend.services.shareholding_service import get_shareholding
        from backend.fetchers import nse_client

        with patch.object(nse_client, "fetch_shareholding", new=AsyncMock(side_effect=Exception("NSE down"))):
            nodes = await get_shareholding(LARGE_CAP, AS_OF, PROFILE, request_id="test:fallback:holding")

        assert isinstance(nodes, list)
        if nodes:
            sources = {n.source for n in nodes}
            assert "screener_in" in sources, f"Expected screener_in fallback, got {sources}"


# ═════════════════════════════════════════════════════════════════════════════
# 2.6  Technicals Service
# ═════════════════════════════════════════════════════════════════════════════

class TestTechnicalsService:
    """Tests for backend/services/technicals_service.py — ta library on OHLCV."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", [LARGE_CAP, MID_CAP])
    async def test_get_technicals_returns_nodes(self, symbol: str) -> None:
        """get_technicals returns list[Node] with valid schema."""
        from backend.services.technicals_service import get_technicals
        nodes = await get_technicals(symbol, as_of_date=AS_OF, profile=PROFILE)
        _assert_node_list(nodes, symbol)

    @pytest.mark.asyncio
    async def test_technicals_node_count(self) -> None:
        """Large cap with full history should produce close to 17 indicator nodes."""
        from backend.services.technicals_service import get_technicals
        nodes = await get_technicals(LARGE_CAP, as_of_date=AS_OF, profile=PROFILE)
        assert len(nodes) >= 10, f"Expected >= 10 indicator nodes, got {len(nodes)}"

    @pytest.mark.asyncio
    async def test_technicals_accepts_none_profile(self) -> None:
        """get_technicals must not raise when profile=None (uses default)."""
        from backend.services.technicals_service import get_technicals
        nodes = await get_technicals(LARGE_CAP, profile=None)
        assert isinstance(nodes, list)

    @pytest.mark.asyncio
    async def test_technicals_ohlcv_failure_returns_empty(self) -> None:
        """When OHLCV is unavailable, get_technicals returns [] without raising."""
        from backend.services.technicals_service import get_technicals
        from backend.services import ohlcv_service
        import pandas as pd

        with patch.object(ohlcv_service, "get_ohlcv", new=AsyncMock(return_value=pd.DataFrame())):
            nodes = await get_technicals(LARGE_CAP, profile=PROFILE)

        assert nodes == [], f"Expected [] on OHLCV failure, got {nodes}"

    @pytest.mark.asyncio
    async def test_technicals_all_nodes_have_category_technical(self) -> None:
        """Every node returned by technicals service must be category=technical."""
        from backend.services.technicals_service import get_technicals
        from backend.schemas.node import NodeCategory
        nodes = await get_technicals(LARGE_CAP, as_of_date=AS_OF, profile=PROFILE)
        for node in nodes:
            assert node.category == NodeCategory.technical, (
                f"Node '{node.name}' has wrong category {node.category}"
            )


# ═════════════════════════════════════════════════════════════════════════════
# 2.7  Announcements Service
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementsService:
    """Tests for backend/services/announcements_service.py — NSE parallel BSE."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symbol", [LARGE_CAP, MID_CAP])
    async def test_get_announcements_returns_nodes(self, symbol: str) -> None:
        """get_announcements returns non-empty list[Node] with valid schema."""
        from backend.services.announcements_service import get_announcements
        nodes = await get_announcements(symbol, AS_OF, PROFILE)
        _assert_node_list(nodes, symbol)

    @pytest.mark.asyncio
    async def test_announcements_nse_failure_bse_fills(self) -> None:
        """When NSE announcements fail, BSE actions still populate nodes."""
        from backend.services.announcements_service import get_announcements
        from backend.services.announcements_service import _fetch_nse  # noqa: F401

        # Patch _fetch_nse to simulate NSE failure (returns exception)
        with patch(
            "backend.services.announcements_service._fetch_nse",
            new=AsyncMock(side_effect=Exception("NSE announcements down")),
        ):
            nodes = await get_announcements(LARGE_CAP, AS_OF, PROFILE)

        # BSE alone should still yield some announcements for RELIANCE
        assert isinstance(nodes, list)
        assert len(nodes) > 0, "BSE should fill announcements when NSE fails"

    @pytest.mark.asyncio
    async def test_announcements_bse_failure_nse_fills(self) -> None:
        """When BSE actions fail, NSE board meetings + actions still populate nodes."""
        from backend.services.announcements_service import get_announcements

        with patch(
            "backend.services.announcements_service._fetch_bse",
            new=AsyncMock(side_effect=Exception("BSE announcements down")),
        ):
            nodes = await get_announcements(LARGE_CAP, AS_OF, PROFILE)

        assert isinstance(nodes, list)
        assert len(nodes) > 0, "NSE should fill announcements when BSE fails"

    @pytest.mark.asyncio
    async def test_announcements_deduplication(self) -> None:
        """Nodes must not have duplicate node_id (same event from NSE+BSE must be collapsed)."""
        from backend.services.announcements_service import get_announcements
        nodes = await get_announcements(LARGE_CAP, AS_OF, PROFILE)
        # node_id is deterministic: {stock}|{category}|{name}|{as_of_date}
        seen: set[str] = set()
        for node in nodes:
            assert node.node_id not in seen, f"Duplicate node_id: {node.node_id}"
            seen.add(node.node_id)

    @pytest.mark.asyncio
    async def test_announcements_both_fail_returns_empty(self) -> None:
        """When both NSE and BSE fail, returns [] without raising."""
        from backend.services.announcements_service import get_announcements

        with (
            patch(
                "backend.services.announcements_service._fetch_nse",
                new=AsyncMock(side_effect=Exception("NSE down")),
            ),
            patch(
                "backend.services.announcements_service._fetch_bse",
                new=AsyncMock(side_effect=Exception("BSE down")),
            ),
        ):
            nodes = await get_announcements(LARGE_CAP, AS_OF, PROFILE)

        assert nodes == [], f"Expected [] when both sources fail, got {nodes}"


# ═════════════════════════════════════════════════════════════════════════════
# Cross-service: Node schema invariants
# ═════════════════════════════════════════════════════════════════════════════

class TestNodeSchemaInvariants:
    """Assert that all services emit nodes that satisfy the Node pydantic schema."""

    @pytest.mark.asyncio
    async def test_all_services_emit_valid_nodes_for_reliance(self) -> None:
        """
        Run all 6 node-returning services for RELIANCE and assert every node passes
        the pydantic model validation (no raw dict leakage, all required fields set).
        """
        from backend.schemas.node import Node
        from backend.services.price_service import get_price
        from backend.services.ratios_service import get_ratios
        from backend.services.financials_service import get_financials
        from backend.services.shareholding_service import get_shareholding
        from backend.services.technicals_service import get_technicals
        from backend.services.announcements_service import get_announcements

        all_nodes: list[Node] = []
        all_nodes += await get_price(LARGE_CAP, AS_OF, PROFILE)
        all_nodes += await get_ratios(LARGE_CAP, AS_OF, PROFILE)
        all_nodes += await get_financials(LARGE_CAP, AS_OF, PROFILE)
        all_nodes += await get_shareholding(LARGE_CAP, AS_OF, PROFILE)
        all_nodes += await get_technicals(LARGE_CAP, as_of_date=AS_OF, profile=PROFILE)
        all_nodes += await get_announcements(LARGE_CAP, AS_OF, PROFILE)

        assert len(all_nodes) > 0, "No nodes produced at all for RELIANCE"

        for node in all_nodes:
            assert isinstance(node, Node), f"Non-Node in output: {node!r}"
            assert node.source, f"source empty: {node!r}"
            assert 0.0 < node.confidence <= 1.0, f"Bad confidence: {node!r}"
            assert node.stock == LARGE_CAP, f"Wrong stock on node: {node!r}"
