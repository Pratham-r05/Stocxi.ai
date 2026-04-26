"""
agent_context.py — Market Context Agent for the Stocxi analysis pipeline.

Emits exactly 4 nodes per request: Market_Regime (Nifty 50 SMA-based regime
classification), Sector_Trend (20-day momentum on the relevant NSE sector index),
Peer_Snapshot (MVP placeholder, no peer fetch yet), and Data_Completeness
(placeholder replaced by the orchestrator after all agents report in).  The agent
never raises — degraded nodes with low confidence are returned instead of a
FetchFailure so that the orchestrator always receives a complete context envelope.

All node values are computed labels or percentages (sanitized=True); no raw
company names or brand strings enter any node value field.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Literal

from backend.config import yaml_cfg
from backend.schemas.messages import FetchDomain, FetchFailure, FetchRequest
from backend.schemas.node import HorizonRelevance, Node, NodeCategory, NodeSignal
from backend.services.ohlcv_service import get_ohlcv
from backend.util.ist_calendar import now_ist

logger = logging.getLogger(__name__)

_AGENT_TIMEOUT: float = 20.0
_DOMAIN = FetchDomain.context

# NSE sector index tickers keyed by lowercase sector label fragment
_SECTOR_INDEX_MAP: dict[str, str] = {
    "bank":    "^NSEBANK",
    "it":      "^CNXIT",
    "pharma":  "^CNXPHARMA",
    "fmcg":    "^CNXFMCG",
    "auto":    "^CNXAUTO",
    "metal":   "^CNXMETAL",
    "energy":  "^CNXENERGY",
    "realty":  "^CNXREALTY",
    "infra":   "^CNXINFRA",
    "media":   "^CNXMEDIA",
}


# ── Config helpers ────────────────────────────────────────────────────────────

def _context_weight() -> float:
    """Return the context node weight from weights.yaml, falling back to 0.1."""
    return float(yaml_cfg.weights.get("context", {}).get("weight", 0.1))


def _weight_ver() -> str:
    """Return the pinned weight version string from versions.yaml."""
    return yaml_cfg.versions.get("weight_version", "")


# ── Node factory ──────────────────────────────────────────────────────────────

def _make_node(
    *,
    stock: str,
    as_of_date: date,
    fetched_at: datetime,
    name: str,
    value: str,
    value_raw: dict,
    signal: NodeSignal,
    source: str,
    confidence: float,
) -> Node:
    """
    Build a context Node with all required fields pre-filled.

    Args:
        stock:       NSE ticker the analysis belongs to.
        as_of_date:  Point-in-time date for the analysis.
        fetched_at:  IST datetime stamp from now_ist().
        name:        Node name (e.g. "Market_Regime").
        value:       Human-readable label (sanitized).
        value_raw:   Raw numeric/dict payload for audit.
        signal:      NodeSignal enum value.
        source:      Source identifier string.
        confidence:  Float [0, 1] confidence in this node.

    Returns:
        A fully populated Node instance with sanitized=True.
    """
    return Node(
        node_id="",
        stock=stock.upper(),
        category=NodeCategory.context,
        name=name,
        value=value,
        value_raw=value_raw,
        signal=signal,
        confidence=confidence,
        source=source,
        source_url="",
        as_of_date=as_of_date,
        fetched_at_ist=fetched_at,
        horizon_relevance=HorizonRelevance.both,
        weight=_context_weight(),
        weight_version=_weight_ver(),
        schema_version=1,
        sanitized=True,
    )


# ── Individual node builders ──────────────────────────────────────────────────

def _classify_regime(
    close: "pd.Series",  # type: ignore[name-defined]  # pandas imported inside ohlcv_service
    price: float,
    sma50: float,
    sma200: float,
) -> tuple[str, NodeSignal]:
    """
    Classify market regime from price and SMAs.

    Returns (label, signal).  Checks for recent SMA50/SMA200 crossover first
    (≤10 bars back) → Transition; then applies Bull/Bear/Sideways thresholds.
    """
    if len(close) >= 210:
        curr_above = sma50 > sma200
        for i in range(2, 12):
            prev_sma50 = float(close.iloc[-50 - i: -i].mean())
            prev_sma200 = float(close.iloc[-200 - i: -i].mean())
            if (prev_sma50 > prev_sma200) != curr_above:
                return "Transition (recent SMA crossover)", NodeSignal.neutral
    if price > sma50 > sma200:
        return "Bull Market", NodeSignal.positive
    if price < sma50 < sma200:
        return "Bear Market", NodeSignal.negative
    return "Sideways", NodeSignal.neutral


async def _market_regime_node(request: FetchRequest, fetched_at: datetime) -> Node:
    """
    Compute Market_Regime from Nifty 50 SMA50/SMA200.  Returns a degraded node
    (confidence=0.1, value="Unknown") if OHLCV fetch fails or rows < 200.
    """
    try:
        df = await get_ohlcv("^NSEI", request.as_of_date)
        if df.empty or "Close" not in df.columns or len(df) < 200:
            raise ValueError("Insufficient NSEI OHLCV rows")
        close = df["Close"].dropna()
        price = float(close.iloc[-1])
        sma50 = float(close.iloc[-50:].mean())
        sma200 = float(close.iloc[-200:].mean())
        value, signal = _classify_regime(close, price, sma50, sma200)
        return _make_node(
            stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
            name="Market_Regime", value=value,
            value_raw={"price": price, "sma50": round(sma50, 2), "sma200": round(sma200, 2)},
            signal=signal, source="nse_library", confidence=0.9,
        )
    except Exception as exc:
        logger.warning("agent_context: Market_Regime degraded — %s", exc)
        return _make_node(
            stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
            name="Market_Regime", value="Unknown",
            value_raw={}, signal=NodeSignal.neutral, source="nse_library", confidence=0.1,
        )


def _momentum_label(momentum_pct: float) -> tuple[str, NodeSignal]:
    """Classify 20-day momentum into a label/signal pair (thresholds: ±3%)."""
    if momentum_pct > 3.0:
        return f"Positive momentum ({momentum_pct:+.2f}% 20d)", NodeSignal.positive
    if momentum_pct < -3.0:
        return f"Negative momentum ({momentum_pct:+.2f}% 20d)", NodeSignal.negative
    return f"Neutral momentum ({momentum_pct:+.2f}% 20d)", NodeSignal.neutral


async def _sector_trend_node(request: FetchRequest, fetched_at: datetime) -> Node:
    """
    Compute Sector_Trend from the NSE sector index matched to request.profile.sector.
    Emits a degraded node (confidence=0.3) if no sector match or OHLCV fails.
    """
    sector_label = (request.profile.sector or "").lower()
    index_ticker: str | None = None
    for key, ticker in _SECTOR_INDEX_MAP.items():
        if key in sector_label:
            index_ticker = ticker
            break

    if not index_ticker:
        return _make_node(
            stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
            name="Sector_Trend", value="Data unavailable",
            value_raw={"reason": "no_sector_match", "sector": sector_label},
            signal=NodeSignal.neutral, source="nse_library", confidence=0.3,
        )

    try:
        df = await get_ohlcv(index_ticker, request.as_of_date)
        if df.empty or "Close" not in df.columns or len(df) < 22:
            raise ValueError(f"Insufficient rows for {index_ticker}")

        close = df["Close"].dropna()
        momentum_pct = round((float(close.iloc[-1]) / float(close.iloc[-21]) - 1.0) * 100, 2)
        value, signal = _momentum_label(momentum_pct)
        return _make_node(
            stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
            name="Sector_Trend", value=value,
            value_raw={"index": index_ticker, "momentum_20d_pct": momentum_pct},
            signal=signal, source="nse_library", confidence=0.7,
        )
    except Exception as exc:
        logger.warning("agent_context: Sector_Trend degraded — %s", exc)
        return _make_node(
            stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
            name="Sector_Trend", value="Data unavailable",
            value_raw={"reason": str(exc), "index": index_ticker},
            signal=NodeSignal.neutral, source="nse_library", confidence=0.3,
        )


def _peer_snapshot_node(request: FetchRequest, fetched_at: datetime) -> Node:
    """
    Emit a placeholder Peer_Snapshot node.

    MVP: no peer fetch implemented yet.  The orchestrator and analysis agent are
    aware that this node carries no signal.  Future: fetch ratio nodes for top-3
    peers from screener.in and compute relative z-scores.

    Returns:
        A neutral, low-confidence placeholder node.
    """
    return _make_node(
        stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
        name="Peer_Snapshot", value="Peer data not yet implemented",
        value_raw={"status": "not_implemented"},
        signal=NodeSignal.neutral, source="internal", confidence=0.3,
    )


def _data_completeness_node(request: FetchRequest, fetched_at: datetime) -> Node:
    """
    Emit a placeholder Data_Completeness node to be overwritten by the orchestrator.

    The orchestrator collects results from all agents and computes the true
    completeness score.  This placeholder ensures the node slot always exists in
    the context envelope even before orchestrator post-processing.

    Returns:
        A neutral placeholder node with confidence=1.0.
    """
    return _make_node(
        stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
        name="Data_Completeness", value="Computed by orchestrator",
        value_raw={"status": "placeholder"},
        signal=NodeSignal.neutral, source="internal", confidence=1.0,
    )


# ── Agent class ───────────────────────────────────────────────────────────────

class ContextAgent:
    """
    Market context agent — emits Market_Regime, Sector_Trend, Peer_Snapshot,
    and Data_Completeness nodes for every analysis request.
    """

    domain: FetchDomain = FetchDomain.context

    def _coerce_node(
        self,
        result: Node | BaseException,
        request: FetchRequest,
        fetched_at: datetime,
        name: str,
        fallback_value: str,
        fallback_confidence: float,
        fallback_source: str,
    ) -> Node:
        """
        Return result as-is if it is a Node; otherwise log the error and return a
        degraded node.  Used to coerce gather(return_exceptions=True) outputs.
        """
        if isinstance(result, BaseException):
            logger.error("agent_context: %s raised — %s", name, result)
            return _make_node(
                stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
                name=name, value=fallback_value, value_raw={},
                signal=NodeSignal.neutral, source=fallback_source,
                confidence=fallback_confidence,
            )
        return result

    async def fetch(self, request: FetchRequest) -> list[Node] | FetchFailure:
        """
        Fetch 4 context nodes concurrently under a 20s timeout.  Returns degraded
        nodes on timeout; FetchFailure only on catastrophic non-recoverable error.
        """
        try:
            fetched_at = now_ist()
            raw = await asyncio.wait_for(
                asyncio.gather(
                    _market_regime_node(request, fetched_at),
                    _sector_trend_node(request, fetched_at),
                    return_exceptions=True,
                ),
                timeout=_AGENT_TIMEOUT,
            )
            regime_node = self._coerce_node(
                raw[0], request, fetched_at, "Market_Regime", "Unknown", 0.1, "nse_library",
            )
            sector_node = self._coerce_node(
                raw[1], request, fetched_at, "Sector_Trend", "Data unavailable", 0.3, "nse_library",
            )
            nodes: list[Node] = [
                regime_node, sector_node,
                _peer_snapshot_node(request, fetched_at),
                _data_completeness_node(request, fetched_at),
            ]
            logger.info(
                "agent_context: %s — 4 context nodes built (regime=%s sector=%s)",
                request.stock, regime_node.value, sector_node.value,
            )
            return nodes

        except asyncio.TimeoutError:
            logger.warning("agent_context: timeout after %.0fs for %s", _AGENT_TIMEOUT, request.stock)
            return self._degraded_envelope(request, now_ist())

        except Exception as exc:
            logger.error("agent_context: catastrophic failure for %s — %s", request.stock, exc)
            return FetchFailure(
                domain=self.domain, source="nse_library", reason="parse_error",
                error=str(exc), request_id=request.request_id,
            )

    async def validate(self, nodes: list[Node]) -> list[Node]:
        """
        Validate context nodes.

        Context nodes are informational and always returned even when degraded,
        so validation is a pass-through.  This hook exists to satisfy the agent
        contract defined in AGENTS.md.

        Args:
            nodes: Node list as returned by fetch().

        Returns:
            The same node list, unchanged.
        """
        return nodes

    def _degraded_envelope(self, request: FetchRequest, fetched_at: datetime) -> list[Node]:
        """
        Return a 4-node degraded envelope used when the fetch times out.

        Args:
            request:    Original FetchRequest.
            fetched_at: IST timestamp to stamp on each node.

        Returns:
            List of 4 degraded/placeholder nodes.
        """
        return [
            _make_node(
                stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
                name="Market_Regime", value="Unknown", value_raw={"reason": "timeout"},
                signal=NodeSignal.neutral, source="nse_library", confidence=0.1,
            ),
            _make_node(
                stock=request.stock, as_of_date=request.as_of_date, fetched_at=fetched_at,
                name="Sector_Trend", value="Data unavailable", value_raw={"reason": "timeout"},
                signal=NodeSignal.neutral, source="nse_library", confidence=0.3,
            ),
            _peer_snapshot_node(request, fetched_at),
            _data_completeness_node(request, fetched_at),
        ]


context_agent = ContextAgent()


async def run(request: FetchRequest) -> list[Node] | FetchFailure:
    """Module-level entry point — delegates to context_agent singleton."""
    return await context_agent.fetch(request)
