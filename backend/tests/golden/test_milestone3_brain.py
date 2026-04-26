"""
test_milestone3_brain.py — Deterministic CI tests for Milestone 3 (The Brain).

Covers agent_verifier, formatter, agent_analysis (LLM mocked), and audit_log.
No network I/O. No LLM calls. All assertions are deterministic.

Modules under test:
  - backend/agents/agent_verifier.py
  - backend/agents/formatter.py
  - backend/agents/agent_analysis.py  (LLM call patched via unittest.mock)
  - backend/audit/audit_log.py
"""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.agents import agent_verifier, formatter
from backend.audit import audit_log
from backend.schemas.messages import (
    AnalysisDraft,
    AgreementLink,
    Claim,
    ContradictionLink,
    FetchRequest,
    Horizon,
    Risk,
    UserProfile,
    VerifiedAnalysis,
    Verdict,
)
from backend.schemas.node import HorizonRelevance, Node, NodeCategory, NodeSignal
from backend.util.sanitizer import build_anon_map

# ── Shared fixtures ────────────────────────────────────────────────────────────

_TODAY = date.today()
_NOW   = datetime.now(timezone.utc)
_STOCK = "TESTCO"  # fake ticker — never a real NSE name


def _node(name: str, value: str, category: NodeCategory = NodeCategory.technical) -> Node:
    return Node(
        stock=_STOCK,
        category=category,
        name=name,
        value=value,
        signal=NodeSignal.positive,
        confidence=0.75,
        source="test",
        source_id="test",
        as_of_date=_TODAY,
        fetched_at_ist=_NOW,
        weight=0.5,
        weight_version="2026.04",
        sanitized=True,
    )


def _make_nodes() -> list[Node]:
    return [
        _node("RSI",             "RSI(14)=62 — Bullish"),
        _node("MACD",            "MACD=0.8 — Bullish"),
        _node("Revenue_Growth",  "Revenue Growth YoY=18%", NodeCategory.fundamental),
        _node("ROE",             "ROE=22.3%",              NodeCategory.fundamental),
        _node("Market_Regime",   "Regime=Bullish",         NodeCategory.context),
    ]


def _make_draft(nodes: list[Node], *, strip_one: bool = False) -> AnalysisDraft:
    """Build a mock AnalysisDraft. If strip_one=True, one claim has an invalid node_id."""
    valid_ids = [n.node_id for n in nodes]
    bad_id    = "FAKE|technical|Nonexistent|2020-01-01"

    claims = [
        Claim(text="RSI indicates bullish momentum.",    node_ids=[valid_ids[0]]),
        Claim(text="MACD confirms upward crossover.",    node_ids=[valid_ids[1]]),
    ]
    if strip_one:
        claims.append(Claim(text="Ghost signal observed.", node_ids=[bad_id]))

    return AnalysisDraft(
        what_data_suggests=claims,
        signals_in_favor=[Claim(text="Revenue growth is strong.", node_ids=[valid_ids[2]])],
        signals_against=[],
        verdicts={
            "technical": Verdict(
                category="technical",
                direction="bullish",
                summary="Technical indicators are bullish.",
                supporting_node_ids=[valid_ids[0], valid_ids[1]],
                confidence=0.72,
            ),
            "fundamental": Verdict(
                category="fundamental",
                direction="bullish",
                summary="Fundamentals look strong.",
                supporting_node_ids=[valid_ids[2]],
                confidence=0.80,
            ),
            "news":         Verdict(category="news",         direction="neutral", summary="No news.", supporting_node_ids=[], confidence=0.5),
            "announcement": Verdict(category="announcement", direction="neutral", summary="No filings.", supporting_node_ids=[], confidence=0.5),
        },
        agreements=[
            AgreementLink(node_id_a=valid_ids[0], node_id_b=valid_ids[1], reason="Both confirm uptrend."),
        ],
        contradictions=[],
        overall_signal="bullish",
        raw_confidence=0.74,
        model_id="test-model",
        prompt_version="2026.04.a",
        weight_version="2026.04",
    )


def _make_request() -> FetchRequest:
    return FetchRequest(
        stock=_STOCK,
        as_of_date=_TODAY,
        profile=UserProfile(horizon=Horizon.short, risk=Risk.moderate),
        request_id=str(uuid.uuid4()),
    )


# ── agent_verifier tests ───────────────────────────────────────────────────────

class TestAgentVerifier:

    def test_all_valid_claims_kept(self):
        nodes = _make_nodes()
        draft = _make_draft(nodes, strip_one=False)
        result = agent_verifier.run(draft, nodes)

        assert isinstance(result, VerifiedAnalysis)
        assert result.stripped_claims == 0
        assert result.low_fidelity is False
        assert result.verification_method == "python"
        assert len(result.draft.what_data_suggests) == 2
        assert len(result.draft.signals_in_favor) == 1

    def test_invalid_claim_stripped(self):
        nodes = _make_nodes()
        draft = _make_draft(nodes, strip_one=True)
        result = agent_verifier.run(draft, nodes)

        assert result.stripped_claims == 1
        assert result.low_fidelity is False          # threshold is 2; 1 stripped is OK
        assert len(result.draft.what_data_suggests) == 2   # ghost claim removed

    def test_low_fidelity_flag_triggers_above_threshold(self):
        nodes  = _make_nodes()
        bad_id = "FAKE|technical|X|2020-01-01"
        draft  = AnalysisDraft(
            what_data_suggests=[
                Claim(text="Ghost 1.", node_ids=[bad_id]),
                Claim(text="Ghost 2.", node_ids=[bad_id]),
                Claim(text="Ghost 3.", node_ids=[bad_id]),
            ],
            signals_in_favor=[],
            signals_against=[],
            verdicts={
                cat: Verdict(category=cat, direction="neutral", summary="", supporting_node_ids=[], confidence=0.5)
                for cat in ("technical", "fundamental", "news", "announcement")
            },
            agreements=[],
            contradictions=[],
            overall_signal="neutral",
            raw_confidence=0.5,
            model_id="test", prompt_version="test", weight_version="test",
        )
        result = agent_verifier.run(draft, nodes)

        assert result.stripped_claims == 3
        assert result.low_fidelity is True    # 3 > LOW_FIDELITY_THRESHOLD(2)

    def test_invalid_agreement_removed(self):
        nodes   = _make_nodes()
        draft   = _make_draft(nodes)
        bad_id  = "FAKE|technical|X|2020-01-01"
        # inject a bad agreement
        draft.agreements.append(
            AgreementLink(node_id_a=bad_id, node_id_b=nodes[0].node_id, reason="Bad link.")
        )
        result = agent_verifier.run(draft, nodes)

        # Only the valid agreement should survive
        assert len(result.draft.agreements) == 1
        assert result.draft.agreements[0].node_id_a == nodes[0].node_id

    def test_verdict_bad_node_ids_pruned(self):
        nodes  = _make_nodes()
        draft  = _make_draft(nodes)
        bad_id = "FAKE|technical|X|2020-01-01"
        draft.verdicts["technical"].supporting_node_ids.append(bad_id)

        result = agent_verifier.run(draft, nodes)
        tech_verdict = result.draft.verdicts["technical"]

        assert bad_id not in tech_verdict.supporting_node_ids
        assert nodes[0].node_id in tech_verdict.supporting_node_ids


# ── formatter tests ────────────────────────────────────────────────────────────

class TestFormatter:

    def test_result_structure(self):
        nodes    = _make_nodes()
        draft    = _make_draft(nodes)
        verified = agent_verifier.run(draft, nodes)
        request  = _make_request()
        anon_map = build_anon_map(stock=_STOCK)

        result, admin_view = formatter.format_result(
            verified=verified,
            anon_map=anon_map,
            request=request,
            nodes=nodes,
            analysis_id="test-aid-001",
        )

        assert result.stock == _STOCK
        assert result.overall_signal == "bullish"
        assert result.disclaimer != ""
        assert result.analysis_id == "test-aid-001"
        assert result.cache_hit is False
        assert isinstance(result.signals_in_favor, list)
        assert isinstance(result.signals_against, list)

    def test_data_disclosure_counts(self):
        nodes    = _make_nodes()   # 2 technical, 2 fundamental, 1 context
        draft    = _make_draft(nodes)
        verified = agent_verifier.run(draft, nodes)
        request  = _make_request()
        anon_map = build_anon_map(stock=_STOCK)

        result, _ = formatter.format_result(
            verified=verified, anon_map=anon_map, request=request, nodes=nodes,
        )

        assert result.data_completeness.get("technical") == 2
        assert result.data_completeness.get("fundamental") == 2
        assert result.data_completeness.get("context") == 1

    def test_disclaimer_always_present(self):
        nodes    = _make_nodes()
        verified = agent_verifier.run(_make_draft(nodes), nodes)
        result, _ = formatter.format_result(
            verified=verified,
            anon_map=build_anon_map(stock=_STOCK),
            request=_make_request(),
            nodes=nodes,
        )
        assert "SEBI" in result.disclaimer or "advisor" in result.disclaimer.lower()

    def test_admin_view_has_full_trace(self):
        nodes    = _make_nodes()
        verified = agent_verifier.run(_make_draft(nodes), nodes)
        _, admin_view = formatter.format_result(
            verified=verified,
            anon_map=build_anon_map(stock=_STOCK),
            request=_make_request(),
            nodes=nodes,
        )
        for key in ("verdicts", "agreements", "what_data_suggests_annotated",
                    "signals_in_favor_annotated", "node_counts", "anon_map"):
            assert key in admin_view, f"admin_view missing key: {key}"

    def test_failed_fetches_appear_in_disclosure(self):
        nodes    = _make_nodes()
        verified = agent_verifier.run(_make_draft(nodes), nodes)
        result, _ = formatter.format_result(
            verified=verified,
            anon_map=build_anon_map(stock=_STOCK),
            request=_make_request(),
            nodes=nodes,
            failed_fetches=["news data unavailable today"],
        )
        assert "news data unavailable today" in result.data_disclosure


# ── agent_analysis tests (LLM mocked) ─────────────────────────────────────────

class TestAgentAnalysis:

    _MOCK_LLM_RESPONSE = {
        "what_data_suggests": [
            {"text": "STOCK_A shows strong momentum.", "node_ids": [], "is_positive": True},
        ],
        "signals_in_favor": [
            {"text": "RSI is in bullish territory.", "node_ids": [], "is_positive": True},
        ],
        "signals_against": [],
        "verdicts": {
            "technical":    {"direction": "bullish", "summary": "Bullish.",  "supporting_node_ids": [], "confidence": 0.72},
            "fundamental":  {"direction": "neutral",  "summary": "Neutral.", "supporting_node_ids": [], "confidence": 0.55},
            "news":         {"direction": "neutral",  "summary": "No news.", "supporting_node_ids": [], "confidence": 0.50},
            "announcement": {"direction": "neutral",  "summary": "None.",    "supporting_node_ids": [], "confidence": 0.50},
        },
        "agreements": [],
        "contradictions": [],
        "overall_signal": "bullish",
        "raw_confidence": 0.70,
    }

    @pytest.mark.asyncio
    async def test_parses_llm_output_into_draft(self):
        from backend.agents import agent_analysis

        nodes   = _make_nodes()
        request = _make_request()

        with patch("backend.agents.agent_analysis._call_llm", return_value=(self._MOCK_LLM_RESPONSE, "{}")):
            draft, _, _ = await agent_analysis.run(nodes, request)

        assert isinstance(draft, AnalysisDraft)
        assert draft.overall_signal == "bullish"
        assert draft.raw_confidence == pytest.approx(0.70)
        assert draft.prompt_version != ""
        assert draft.weight_version != ""
        assert draft.model_id != ""

    @pytest.mark.asyncio
    async def test_rejects_unsanitized_nodes(self):
        from backend.agents import agent_analysis

        dirty_node = Node(
            stock=_STOCK, category=NodeCategory.news, name="headline",
            value="TESTCO stock rises", signal=NodeSignal.positive,
            confidence=0.6, source="test", source_id="test",
            as_of_date=_TODAY, fetched_at_ist=_NOW,
            weight=0.5, weight_version="2026.04", sanitized=False,
        )
        request = _make_request()

        with pytest.raises(ValueError, match="unsanitized"):
            await agent_analysis.run([dirty_node], request)

    @pytest.mark.asyncio
    async def test_invalid_overall_signal_defaults_to_neutral(self):
        from backend.agents import agent_analysis

        bad_response = dict(self._MOCK_LLM_RESPONSE)
        bad_response["overall_signal"] = "VERY_BULLISH"   # not a valid enum value

        nodes   = _make_nodes()
        request = _make_request()

        with patch("backend.agents.agent_analysis._call_llm", return_value=(bad_response, "{}")):
            draft, _, _ = await agent_analysis.run(nodes, request)

        assert draft.overall_signal == "neutral"

    @pytest.mark.asyncio
    async def test_json_fence_stripped(self):
        """_call_llm returning a valid dict (after fence stripping) should parse correctly."""
        from backend.agents import agent_analysis

        nodes   = _make_nodes()
        request = _make_request()

        with patch("backend.agents.agent_analysis._call_llm", return_value=(self._MOCK_LLM_RESPONSE, "{}")):
            draft, _, _ = await agent_analysis.run(nodes, request)

        assert draft.overall_signal == "bullish"


# ── audit_log tests ────────────────────────────────────────────────────────────

class TestAuditLog:

    def test_write_and_read_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(audit_log, "_AUDIT_DIR", tmp_path)

        aid = str(uuid.uuid4())
        node_ids = ["TESTCO|technical|RSI|2026-04-21", "TESTCO|fundamental|ROE|2026-04-21"]

        data_hash = audit_log.log_analysis(
            analysis_id=aid,
            stock="TESTCO",
            profile_bucket="short_moderate",
            as_of_date="2026-04-21",
            node_ids=node_ids,
            prompt_version="2026.04.a",
            weight_version="2026.04",
            model_id="test-model",
            input_nodes_json="[]",
            full_prompt="test prompt",
            full_raw_output="{}",
            final_output={"overall_signal": "bullish"},
            admin_view={"test": True},
        )

        assert data_hash != ""
        row = audit_log.read_row(aid)
        assert row is not None
        assert row["analysis_id"] == aid
        assert row["stock"] == "TESTCO"
        assert row["data_hash"] == data_hash

    def test_data_hash_is_deterministic(self):
        ids = ["B|technical|RSI|2026-01-01", "A|fundamental|ROE|2026-01-01"]
        h1  = audit_log.compute_data_hash(ids)
        h2  = audit_log.compute_data_hash(list(reversed(ids)))   # order shouldn't matter
        assert h1 == h2

    def test_profile_hash_is_stable(self):
        h = audit_log.compute_profile_hash("short_moderate")
        assert len(h) == 8
        assert audit_log.compute_profile_hash("short_moderate") == h   # deterministic

    def test_write_failure_does_not_raise(self, monkeypatch):
        """Audit failures must never crash the pipeline."""
        monkeypatch.setattr(audit_log, "_AUDIT_DIR", Path("/nonexistent/path/that/cannot/exist"))

        try:
            audit_log.log_analysis(
                analysis_id="x", stock="X", profile_bucket="short_moderate",
                as_of_date="2026-01-01", node_ids=[], prompt_version="v",
                weight_version="v", model_id="m", input_nodes_json="[]",
                full_prompt="", full_raw_output="", final_output={}, admin_view={},
            )
        except Exception as exc:
            pytest.fail(f"audit_log.log_analysis raised unexpectedly: {exc}")
