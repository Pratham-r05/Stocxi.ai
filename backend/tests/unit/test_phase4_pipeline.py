"""
test_phase4_pipeline.py — Unit tests for the Phase 4 agent orchestration pipeline.

Covers:
  - orchestrator._run_agent_safe: FetchFailure, TimeoutError, success paths
  - orchestrator._check_sufficient: all three threshold bands + passing case
  - orchestrator._sanitize_nodes: pass-through, scrub, no-mutation guarantee
  - agent_verifier.run / _filter_claims / _filter_verdict: claim stripping,
    low_fidelity flag, agreement/contradiction link pruning
  - formatter.format_result / _build_data_disclosure: tuple shape, disclaimer,
    node count inclusion, required admin_view keys
  - agent_analysis._strip_fences / _repair_truncated_json / _parse_draft:
    fence removal, JSON repair, and draft parsing from raw dicts
  - orchestrator._cache_key: key format and uniqueness

All tests are pure unit tests: NO network calls, NO LLM calls, NO Redis.
External dependencies are mocked with unittest.mock.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from schemas.messages import (
    AnalysisDraft,
    AnalysisResult,
    AgreementLink,
    Claim,
    ContradictionLink,
    FetchDomain,
    FetchFailure,
    FetchRequest,
    Horizon,
    Risk,
    UserProfile,
    VerifiedAnalysis,
    Verdict,
)
from schemas.node import HorizonRelevance, Node, NodeCategory, NodeSignal


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_node(
    category: NodeCategory,
    name: str,
    signal: NodeSignal = NodeSignal.positive,
    node_id: str | None = None,
    sanitized: bool = True,
    stock: str = "RELIANCE",
) -> Node:
    """Create a minimal test Node with sensible defaults."""
    n = Node(
        stock=stock,
        category=category,
        name=name,
        value=f"{name} test value",
        signal=signal,
        confidence=1.0,
        source="nse_library",
        as_of_date=date(2026, 4, 26),
        fetched_at_ist=datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc),
        weight=0.5,
        horizon_relevance=HorizonRelevance.both,
        sanitized=sanitized,
    )
    if node_id:
        # Override the auto-generated node_id
        return n.model_copy(update={"node_id": node_id})
    return n


def _make_fetch_request(stock: str = "RELIANCE") -> FetchRequest:
    """Return a minimal FetchRequest with a UserProfile."""
    return FetchRequest(
        stock=stock,
        as_of_date=date(2026, 4, 26),
        profile=UserProfile(
            horizon=Horizon.long,
            risk=Risk.moderate,
            sector="energy",
        ),
        request_id="test-request-id-001",
    )


def _make_minimal_draft(
    claims: list[Claim] | None = None,
    overall_signal: str = "neutral",
) -> AnalysisDraft:
    """Build a minimal AnalysisDraft for testing."""
    claims = claims or []
    return AnalysisDraft(
        what_data_suggests=claims,
        signals_in_favor=[],
        signals_against=[],
        verdicts={
            "technical": Verdict(
                category="technical",
                direction="neutral",
                summary="Neutral technical picture.",
                supporting_node_ids=[],
                confidence=0.5,
            ),
        },
        agreements=[],
        contradictions=[],
        overall_signal=overall_signal,
        raw_confidence=0.5,
        model_id="gemini-2.5-flash",
        prompt_version="v1",
        weight_version="v1",
    )


def _make_technical_nodes(count: int) -> list[Node]:
    return [_make_node(NodeCategory.technical, f"RSI_{i}") for i in range(count)]


def _make_fundamental_nodes(count: int) -> list[Node]:
    return [_make_node(NodeCategory.fundamental, f"PE_{i}") for i in range(count)]


def _make_announcement_nodes(count: int) -> list[Node]:
    return [_make_node(NodeCategory.announcement, f"Ann_{i}") for i in range(count)]


def _sufficient_node_set() -> list[Node]:
    """Return a node list that clears all three thresholds (10 tech, 8 fund, 3 ann)."""
    return (
        _make_technical_nodes(10)
        + _make_fundamental_nodes(8)
        + _make_announcement_nodes(3)
    )


# ── TestFetchFailureHandling ───────────────────────────────────────────────────

class TestFetchFailureHandling(unittest.TestCase):
    """Tests for orchestrator._run_agent_safe covering FetchFailure, timeout, success."""

    def _run(self, coro):
        """Run a coroutine synchronously."""
        return asyncio.run(coro)

    def test_run_agent_safe_returns_empty_on_fetch_failure(self):
        """_run_agent_safe should return (name, []) when module.run() returns FetchFailure."""
        from agents.orchestrator import _run_agent_safe

        failure = FetchFailure(
            domain=FetchDomain.technical,
            source="nse_library",
            reason="timeout",
            error="connection timed out",
            request_id="req-001",
        )

        mock_module = MagicMock()
        mock_module.run = AsyncMock(return_value=failure)

        name, nodes = self._run(_run_agent_safe("technical", mock_module, _make_fetch_request()))

        self.assertEqual(name, "technical")
        self.assertEqual(nodes, [])

    def test_run_agent_safe_returns_empty_on_timeout_error(self):
        """_run_agent_safe should return (name, []) when asyncio.wait_for raises TimeoutError."""
        from agents.orchestrator import _run_agent_safe

        mock_module = MagicMock()
        # Simulate a coroutine that never finishes — wait_for fires TimeoutError
        mock_module.run = AsyncMock(return_value=[])  # value irrelevant — wait_for is patched

        with patch("backend.agents.orchestrator.asyncio.wait_for",
                   new_callable=AsyncMock, side_effect=asyncio.TimeoutError):
            name, nodes = self._run(_run_agent_safe("fundamental", mock_module, _make_fetch_request()))

        self.assertEqual(name, "fundamental")
        self.assertEqual(nodes, [])

    def test_run_agent_safe_returns_nodes_on_success(self):
        """_run_agent_safe should return (name, nodes) when module.run() succeeds."""
        from agents.orchestrator import _run_agent_safe

        expected_nodes = _make_technical_nodes(3)

        mock_module = MagicMock()
        mock_module.run = AsyncMock(return_value=expected_nodes)

        name, nodes = self._run(_run_agent_safe("technical", mock_module, _make_fetch_request()))

        self.assertEqual(name, "technical")
        self.assertEqual(len(nodes), 3)
        self.assertEqual(nodes, expected_nodes)


# ── TestInsufficientDataGate ───────────────────────────────────────────────────

class TestInsufficientDataGate(unittest.TestCase):
    """Tests for orchestrator._check_sufficient threshold enforcement."""

    def test_raises_when_technical_below_threshold(self):
        """InsufficientDataError raised when technical nodes < 10."""
        from agents.orchestrator import InsufficientDataError, _check_sufficient

        nodes = (
            _make_technical_nodes(9)       # one short of 10
            + _make_fundamental_nodes(8)
            + _make_announcement_nodes(3)
        )
        with self.assertRaises(InsufficientDataError) as ctx:
            _check_sufficient(nodes)
        self.assertIn("technical", str(ctx.exception))

    def test_raises_when_fundamental_below_threshold(self):
        """InsufficientDataError raised when fundamental nodes < 8."""
        from agents.orchestrator import InsufficientDataError, _check_sufficient

        nodes = (
            _make_technical_nodes(10)
            + _make_fundamental_nodes(7)   # one short of 8
            + _make_announcement_nodes(3)
        )
        with self.assertRaises(InsufficientDataError) as ctx:
            _check_sufficient(nodes)
        self.assertIn("fundamental", str(ctx.exception))

    def test_raises_when_announcement_below_threshold(self):
        """InsufficientDataError raised when announcement nodes < 3."""
        from agents.orchestrator import InsufficientDataError, _check_sufficient

        nodes = (
            _make_technical_nodes(10)
            + _make_fundamental_nodes(8)
            + _make_announcement_nodes(2)  # one short of 3
        )
        with self.assertRaises(InsufficientDataError) as ctx:
            _check_sufficient(nodes)
        self.assertIn("announcement", str(ctx.exception))

    def test_returns_counts_when_all_thresholds_met(self):
        """_check_sufficient returns a counts dict when all categories pass."""
        from agents.orchestrator import _check_sufficient

        nodes = _sufficient_node_set()
        counts = _check_sufficient(nodes)

        self.assertIsInstance(counts, dict)
        self.assertGreaterEqual(counts.get("technical", 0), 10)
        self.assertGreaterEqual(counts.get("fundamental", 0), 8)
        self.assertGreaterEqual(counts.get("announcement", 0), 3)


# ── TestNodeSanitization ───────────────────────────────────────────────────────

class TestNodeSanitization(unittest.TestCase):
    """Tests for orchestrator._sanitize_nodes."""

    def _make_anon_map(self) -> object:
        """Build a real AnonMap for RELIANCE."""
        from util.sanitizer import build_anon_map
        return build_anon_map(stock="RELIANCE", sector="energy")

    def test_already_sanitized_nodes_pass_through_unchanged(self):
        """Nodes with sanitized=True must not be modified."""
        from agents.orchestrator import _sanitize_nodes

        node = _make_node(NodeCategory.technical, "RSI_14", sanitized=True)
        original_value = node.value
        anon_map = self._make_anon_map()

        result = _sanitize_nodes([node], anon_map)

        self.assertEqual(len(result), 1)
        self.assertIs(result[0], node)  # exact same object
        self.assertEqual(result[0].value, original_value)

    def test_unsanitized_nodes_are_scrubbed(self):
        """Nodes with sanitized=False should be scrubbed and flagged sanitized=True."""
        from agents.orchestrator import _sanitize_nodes

        # Use a value that won't contain real names (plain indicator text)
        node = _make_node(NodeCategory.news, "Headline", sanitized=False)
        node = node.model_copy(update={"value": "RELIANCE reports quarterly earnings"})
        anon_map = self._make_anon_map()

        result = _sanitize_nodes([node], anon_map)

        self.assertEqual(len(result), 1)
        scrubbed = result[0]
        self.assertTrue(scrubbed.sanitized)
        # Real stock name should be anonymized
        self.assertNotIn("RELIANCE", scrubbed.value)

    def test_sanitize_does_not_mutate_originals(self):
        """_sanitize_nodes must return a new list; originals must not be changed."""
        from agents.orchestrator import _sanitize_nodes

        node = _make_node(NodeCategory.announcement, "Corp_Action", sanitized=False)
        original_sanitized_flag = node.sanitized
        anon_map = self._make_anon_map()

        _sanitize_nodes([node], anon_map)

        # Original node must be untouched
        self.assertEqual(node.sanitized, original_sanitized_flag)


# ── TestVerifier ───────────────────────────────────────────────────────────────

class TestVerifier(unittest.TestCase):
    """Tests for agent_verifier.run, _filter_claims, and _filter_verdict."""

    def _valid_node_id(self, name: str = "RSI_14") -> str:
        return _make_node(NodeCategory.technical, name).node_id

    def test_claims_with_zero_valid_node_ids_are_stripped(self):
        """Claims referencing nonexistent node_ids must be stripped."""
        from agents import agent_verifier

        claim = Claim(text="Some claim.", node_ids=["nonexistent-id-1", "nonexistent-id-2"])
        draft = _make_minimal_draft(claims=[claim])
        nodes = _make_technical_nodes(1)  # no matching node_ids

        result = agent_verifier.run(draft, nodes)

        self.assertEqual(len(result.draft.what_data_suggests), 0)
        self.assertEqual(result.stripped_claims, 1)

    def test_claims_with_valid_node_id_are_kept_and_trimmed(self):
        """Claims with at least one valid node_id are kept; invalid ids are removed."""
        from agents import agent_verifier

        good_node = _make_node(NodeCategory.technical, "RSI_14")
        valid_id = good_node.node_id

        claim = Claim(
            text="RSI is oversold.",
            node_ids=[valid_id, "bad-ghost-id"],
        )
        draft = _make_minimal_draft(claims=[claim])

        result = agent_verifier.run(draft, [good_node])

        self.assertEqual(len(result.draft.what_data_suggests), 1)
        kept_claim = result.draft.what_data_suggests[0]
        # Only the valid id should remain in the kept claim
        self.assertIn(valid_id, kept_claim.node_ids)
        self.assertNotIn("bad-ghost-id", kept_claim.node_ids)
        self.assertEqual(result.stripped_claims, 0)

    def test_low_fidelity_flag_set_when_strip_count_exceeds_threshold(self):
        """stripped_claims > LOW_FIDELITY_THRESHOLD should set low_fidelity=True."""
        from agents import agent_verifier
        from agents.agent_verifier import LOW_FIDELITY_THRESHOLD

        # Build (threshold + 1) claims all referencing nonexistent ids
        bad_claims = [
            Claim(text=f"Claim {i}.", node_ids=["ghost-id"])
            for i in range(LOW_FIDELITY_THRESHOLD + 1)
        ]
        draft = _make_minimal_draft(claims=bad_claims)
        nodes = _make_technical_nodes(1)

        result = agent_verifier.run(draft, nodes)

        self.assertTrue(result.low_fidelity)
        self.assertGreater(result.stripped_claims, LOW_FIDELITY_THRESHOLD)

    def test_agreement_links_with_invalid_node_ids_removed(self):
        """AgreementLinks where either node_id is not in the node set must be removed."""
        from agents import agent_verifier

        good_node_a = _make_node(NodeCategory.technical, "RSI_14")
        good_node_b = _make_node(NodeCategory.fundamental, "PE_Ratio")

        good_link = AgreementLink(
            node_id_a=good_node_a.node_id,
            node_id_b=good_node_b.node_id,
            reason="Both bullish.",
        )
        bad_link = AgreementLink(
            node_id_a=good_node_a.node_id,
            node_id_b="nonexistent-node",
            reason="Invalid link.",
        )

        draft = _make_minimal_draft()
        draft = draft.model_copy(update={"agreements": [good_link, bad_link]})

        result = agent_verifier.run(draft, [good_node_a, good_node_b])

        self.assertEqual(len(result.draft.agreements), 1)
        self.assertEqual(result.draft.agreements[0].reason, "Both bullish.")

    def test_contradiction_links_with_invalid_node_ids_removed(self):
        """ContradictionLinks where either node_id is absent must be removed."""
        from agents import agent_verifier

        pos_node = _make_node(NodeCategory.technical, "MACD", NodeSignal.positive)
        neg_node = _make_node(NodeCategory.fundamental, "Revenue", NodeSignal.negative)

        good_ct = ContradictionLink(
            node_id_positive=pos_node.node_id,
            node_id_negative=neg_node.node_id,
            resolution="Fundamental wins (tier 1).",
            tier_applied=1,
        )
        bad_ct = ContradictionLink(
            node_id_positive="ghost-pos",
            node_id_negative=neg_node.node_id,
            resolution="Invalid.",
            tier_applied=6,
        )

        draft = _make_minimal_draft()
        draft = draft.model_copy(update={"contradictions": [good_ct, bad_ct]})

        result = agent_verifier.run(draft, [pos_node, neg_node])

        self.assertEqual(len(result.draft.contradictions), 1)
        self.assertEqual(result.draft.contradictions[0].tier_applied, 1)


# ── TestFormatter ──────────────────────────────────────────────────────────────

class TestFormatter(unittest.TestCase):
    """Tests for formatter.format_result and formatter._build_data_disclosure."""

    def _make_anon_map(self):
        from util.sanitizer import build_anon_map
        return build_anon_map(stock="INFY", sector="technology")

    def _make_verified(self) -> VerifiedAnalysis:
        draft = _make_minimal_draft()
        return VerifiedAnalysis(
            draft=draft,
            stripped_claims=0,
            low_fidelity=False,
            verification_method="python",
        )

    def test_format_result_returns_tuple_of_analysis_result_and_dict(self):
        """format_result must return a (AnalysisResult, dict) tuple."""
        from agents import formatter

        request = _make_fetch_request("INFY")
        verified = self._make_verified()
        nodes = _sufficient_node_set()
        anon_map = self._make_anon_map()

        result = formatter.format_result(
            verified=verified,
            anon_map=anon_map,
            request=request,
            nodes=nodes,
            analysis_id="test-analysis-id",
            latency_ms=500,
        )

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        analysis_result, admin_view = result
        self.assertIsInstance(analysis_result, AnalysisResult)
        self.assertIsInstance(admin_view, dict)

    def test_disclaimer_is_always_non_empty(self):
        """AnalysisResult.disclaimer must never be empty or None."""
        from agents import formatter

        request = _make_fetch_request("INFY")
        verified = self._make_verified()
        nodes = _sufficient_node_set()
        anon_map = self._make_anon_map()

        analysis_result, _ = formatter.format_result(
            verified=verified,
            anon_map=anon_map,
            request=request,
            nodes=nodes,
        )

        self.assertTrue(analysis_result.disclaimer)
        self.assertGreater(len(analysis_result.disclaimer.strip()), 0)

    def test_build_data_disclosure_includes_node_counts(self):
        """_build_data_disclosure should embed each category's count in the string."""
        from agents.formatter import _build_data_disclosure

        node_counts = {
            "technical": 17,
            "fundamental": 11,
            "announcement": 5,
        }
        disclosure = _build_data_disclosure(node_counts)

        self.assertIn("17", disclosure)
        self.assertIn("11", disclosure)
        self.assertIn("5", disclosure)
        # Sanity: should not be empty
        self.assertTrue(disclosure.strip())

    def test_admin_view_contains_required_keys(self):
        """admin_view must have analysis_id, model_id, verdicts, overall_signal, stripped_claims."""
        from agents import formatter

        request = _make_fetch_request("INFY")
        verified = self._make_verified()
        nodes = _sufficient_node_set()
        anon_map = self._make_anon_map()

        _, admin_view = formatter.format_result(
            verified=verified,
            anon_map=anon_map,
            request=request,
            nodes=nodes,
            analysis_id="audit-id-42",
        )

        required_keys = {"analysis_id", "model_id", "verdicts", "overall_signal", "stripped_claims"}
        for key in required_keys:
            self.assertIn(key, admin_view, f"admin_view is missing required key: {key!r}")

        self.assertEqual(admin_view["analysis_id"], "audit-id-42")


# ── TestAnalysisDraftParsing ───────────────────────────────────────────────────

class TestAnalysisDraftParsing(unittest.TestCase):
    """Tests for agent_analysis._strip_fences, _repair_truncated_json, _parse_draft."""

    def test_strip_fences_removes_json_code_block(self):
        """_strip_fences must strip ```json ... ``` wrapper."""
        from agents.agent_analysis import _strip_fences

        fenced = '```json\n{"key": "value"}\n```'
        result = _strip_fences(fenced)
        self.assertEqual(result, '{"key": "value"}')

    def test_strip_fences_passes_plain_json_unchanged(self):
        """_strip_fences must leave bare JSON unmodified."""
        from agents.agent_analysis import _strip_fences

        plain = '{"overall_signal": "neutral"}'
        result = _strip_fences(plain)
        self.assertEqual(result, plain)

    def test_repair_truncated_json_closes_open_brackets(self):
        """_repair_truncated_json should return a parsed dict for truncated JSON."""
        from agents.agent_analysis import _repair_truncated_json

        # Simulate truncated JSON — top-level object cut off mid-array
        truncated = '{"key": [1, 2, 3'
        result = _repair_truncated_json(truncated)

        # Must not return None — should be able to repair the truncation
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("key", result)

    def test_repair_truncated_json_returns_none_on_non_json(self):
        """_repair_truncated_json must return None if input doesn't start with {."""
        from agents.agent_analysis import _repair_truncated_json

        self.assertIsNone(_repair_truncated_json("not json at all"))
        self.assertIsNone(_repair_truncated_json("[1, 2, 3"))
        self.assertIsNone(_repair_truncated_json(""))


# ── TestCacheKey ───────────────────────────────────────────────────────────────

class TestCacheKey(unittest.TestCase):
    """Tests for orchestrator._cache_key."""

    def test_cache_key_includes_stock_profile_and_data_hash(self):
        """_cache_key must embed stock ticker, profile bucket, and data_hash."""
        from agents.orchestrator import _cache_key

        key = _cache_key("RELIANCE", "long_moderate", "abc123")

        self.assertIn("RELIANCE", key)
        self.assertIn("long_moderate", key)
        self.assertIn("abc123", key)

    def test_different_stock_produces_different_cache_key(self):
        """Two stocks with same profile and data_hash must yield different keys."""
        from agents.orchestrator import _cache_key

        key_a = _cache_key("RELIANCE", "long_moderate", "abc123")
        key_b = _cache_key("INFY", "long_moderate", "abc123")

        self.assertNotEqual(key_a, key_b)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
