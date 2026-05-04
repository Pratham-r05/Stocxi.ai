"""
test_m7.py — Milestone 7 (Ship) test suite.

Covers:
  - agent_report._build_report_payload(): verdict, confidence, thesis, risk, title
  - agent_report.build_report(): returns bytes; fallback on exception
  - v2_analysis routes: JSON analysis, PDF report, 422, 503, param parsing

Run:
    cd /Users/prathamraj/Documents/Placement-Prep/10.Projects/stocxi
    /Users/prathamraj/miniforge3/envs/stocxi/bin/python -m pytest backend/tests/golden/test_m7.py -v
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── sys.path setup ────────────────────────────────────────────────────────────
# Both backend/ and project root must be on path so bare imports resolve.
_BACKEND = Path(__file__).parents[3] / "backend"
_ROOT    = Path(__file__).parents[3]
for _p in (_BACKEND, _ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# ── Imports after path is set ─────────────────────────────────────────────────
from schemas.messages import AnalysisResult, UserProfile, Horizon, Risk
from agents.agent_report import (
    _build_report_payload,
    _build_minimal_snapshot,
    build_report,
    _map_verdict,
    _map_confidence,
)

# ── FastAPI TestClient setup ──────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.v2_analysis import router

test_app = FastAPI()
test_app.include_router(router)
client = TestClient(test_app)


# ─────────────────────────── helper ──────────────────────────────────────────

def _mock_result(
    overall_signal: str = "bullish",
    calibrated_confidence: float | None = 0.72,
    signals_in_favor: list[str] | None = None,
    signals_against: list[str] | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        stock="RELIANCE",
        nse_symbol="RELIANCE.NS",
        bse_code="500325",
        current_price=1284.5,
        analysis_date=date(2026, 4, 22),
        profile=UserProfile(horizon=Horizon.short, risk=Risk.moderate),
        overall_signal=overall_signal,
        calibrated_confidence=calibrated_confidence,
        data_completeness={"technical": 17, "fundamental": 10, "news": 5, "announcement": 4},
        what_data_suggests="Momentum is strong and volume is supporting the move.",
        signals_in_favor=signals_in_favor or ["RSI < 70", "MACD crossover", "EMA bullish", "ADX > 25"],
        signals_against=signals_against or ["High debt", "Sector headwind"],
        data_disclosure="17 indicators, 10 ratios",
        disclaimer="Not investment advice.",
        analysis_id="test-123",
    )


# ═════════════════════════════════════════════════════════════════════════════
# agent_report._build_report_payload — verdict mapping
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildReportPayloadVerdicts:
    def test_bullish_maps_to_buy(self):
        result = _mock_result(overall_signal="bullish")
        payload = _build_report_payload(result, tier="stellar")
        assert payload["verdict"] == "BUY"

    def test_bearish_maps_to_avoid(self):
        # SEBI Rule 12: "SELL" is banned in user-facing output — must be "AVOID"
        result = _mock_result(overall_signal="bearish")
        payload = _build_report_payload(result, tier="stellar")
        assert payload["verdict"] == "AVOID"

    def test_neutral_maps_to_hold(self):
        result = _mock_result(overall_signal="neutral")
        payload = _build_report_payload(result, tier="stellar")
        assert payload["verdict"] == "HOLD"

    def test_mixed_maps_to_hold(self):
        result = _mock_result(overall_signal="mixed")
        payload = _build_report_payload(result, tier="stellar")
        assert payload["verdict"] == "HOLD"


# ═════════════════════════════════════════════════════════════════════════════
# agent_report._build_report_payload — confidence mapping
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildReportPayloadConfidence:
    def test_above_0_7_is_high(self):
        result = _mock_result(calibrated_confidence=0.80)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["confidence"] == "High"

    def test_exactly_0_71_is_high(self):
        result = _mock_result(calibrated_confidence=0.71)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["confidence"] == "High"

    def test_above_0_5_is_medium(self):
        result = _mock_result(calibrated_confidence=0.60)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["confidence"] == "Medium"

    def test_at_or_below_0_5_is_low(self):
        result = _mock_result(calibrated_confidence=0.40)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["confidence"] == "Low"

    def test_none_confidence_is_medium(self):
        result = _mock_result(calibrated_confidence=None)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["confidence"] == "Medium"


# ═════════════════════════════════════════════════════════════════════════════
# agent_report._build_report_payload — thesis_points / risk_flags
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildReportPayloadBullets:
    def test_thesis_points_come_from_signals_in_favor(self):
        favors = ["Signal A", "Signal B", "Signal C"]
        result = _mock_result(signals_in_favor=favors)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["thesis_points"] == favors

    def test_thesis_points_capped_at_4(self):
        favors = ["A", "B", "C", "D", "E", "F"]
        result = _mock_result(signals_in_favor=favors)
        payload = _build_report_payload(result, tier="stellar")
        assert len(payload["thesis_points"]) == 4
        assert payload["thesis_points"] == favors[:4]

    def test_risk_flags_come_from_signals_against(self):
        against = ["Risk X", "Risk Y"]
        result = _mock_result(signals_against=against)
        payload = _build_report_payload(result, tier="stellar")
        assert payload["risk_flags"] == against

    def test_risk_flags_capped_at_4(self):
        against = ["R1", "R2", "R3", "R4", "R5"]
        result = _mock_result(signals_against=against)
        payload = _build_report_payload(result, tier="stellar")
        assert len(payload["risk_flags"]) == 4

    def test_executive_summary_max_400_chars(self):
        long_text = "X" * 600
        result = _mock_result()
        result.__dict__["what_data_suggests"] = long_text
        # rebuild through the function directly
        result2 = _mock_result()
        object.__setattr__(result2, "what_data_suggests", long_text)
        payload = _build_report_payload(result2, tier="stellar")
        assert len(payload["executive_summary"]) <= 400


class TestBuildReportPayloadTitle:
    def test_report_title_contains_stock_and_date(self):
        result = _mock_result()
        payload = _build_report_payload(result, tier="stellar")
        assert "RELIANCE" in payload["report_title"]
        assert "2026-04-22" in payload["report_title"]

    def test_report_title_format(self):
        result = _mock_result()
        payload = _build_report_payload(result, tier="stellar")
        # Should contain the stock name and analysis date
        assert payload["report_title"].startswith("RELIANCE")


# ═════════════════════════════════════════════════════════════════════════════
# agent_report.build_report — returns bytes
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildReport:
    def test_build_report_returns_bytes(self):
        result = _mock_result()
        pdf = build_report(result, tier="stellar", risk_level="medium")
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_build_report_pdf_magic_bytes(self):
        result = _mock_result()
        pdf = build_report(result, tier="stellar", risk_level="medium")
        # PDF files start with %PDF
        assert pdf[:4] == b"%PDF"

    def test_build_report_orbiter_tier(self):
        result = _mock_result()
        pdf = build_report(result, tier="orbiter", risk_level="low")
        assert isinstance(pdf, bytes) and len(pdf) > 0

    def test_build_report_apex_tier(self):
        result = _mock_result()
        pdf = build_report(result, tier="apex", risk_level="high")
        assert isinstance(pdf, bytes) and len(pdf) > 0

    def test_build_report_fallback_on_exception(self):
        """If build_stock_report_pdf raises, build_report returns a fallback PDF (non-empty bytes)."""
        result = _mock_result()
        with patch(
            "backend.agents.agent_report.build_stock_report_pdf",
            side_effect=RuntimeError("PDF engine exploded"),
        ):
            pdf = build_report(result, tier="stellar", risk_level="medium")
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_build_report_never_raises(self):
        """build_report must never propagate an exception."""
        result = _mock_result()
        with patch(
            "backend.agents.agent_report.build_stock_report_pdf",
            side_effect=Exception("fatal"),
        ):
            try:
                pdf = build_report(result)
            except Exception as exc:
                pytest.fail(f"build_report raised: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# v2_analysis route — GET /api/v2/analysis/{symbol}
# ═════════════════════════════════════════════════════════════════════════════

def _make_orch_mock(result: AnalysisResult | None = None, exc: Exception | None = None):
    """Return an async mock for agents.orchestrator.run."""
    mock = AsyncMock()
    if exc is not None:
        mock.side_effect = exc
    else:
        mock.return_value = (result or _mock_result(), {"admin": "view"})
    return mock


class TestV2AnalysisEndpoint:
    def test_200_returns_overall_signal(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_signal" in data
        assert data["overall_signal"] == "bullish"

    def test_200_returns_stock_field(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE")
        assert resp.status_code == 200
        assert resp.json()["stock"] == "RELIANCE"

    def test_insufficient_data_returns_422(self):
        from agents.orchestrator import InsufficientDataError
        exc = InsufficientDataError({"technical": 2}, {"technical": 5})
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(exc=exc)):
            resp = client.get("/api/v2/analysis/RELIANCE")
        assert resp.status_code == 422

    def test_runtime_error_returns_503(self):
        exc = RuntimeError("LLM failed")
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(exc=exc)):
            resp = client.get("/api/v2/analysis/RELIANCE")
        assert resp.status_code == 503

    def test_horizon_param_short_accepted(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)) as mock:
            resp = client.get("/api/v2/analysis/RELIANCE?horizon=short&risk=moderate")
        assert resp.status_code == 200

    def test_horizon_param_long_accepted(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE?horizon=long")
        assert resp.status_code == 200

    def test_invalid_horizon_returns_422(self):
        resp = client.get("/api/v2/analysis/RELIANCE?horizon=weekly")
        assert resp.status_code == 422

    def test_risk_param_conservative_accepted(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE?risk=conservative")
        assert resp.status_code == 200

    def test_risk_param_aggressive_accepted(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE?risk=aggressive")
        assert resp.status_code == 200

    def test_invalid_risk_returns_422(self):
        resp = client.get("/api/v2/analysis/RELIANCE?risk=daredevil")
        assert resp.status_code == 422

    def test_orchestrator_receives_correct_profile(self):
        """Verify horizon and risk are parsed into UserProfile correctly."""
        result = _mock_result()
        captured = {}

        async def capturing_run(request):
            captured["horizon"] = request.profile.horizon.value
            captured["risk"] = request.profile.risk.value
            return result, {}

        with patch("routers.v2_analysis.orch_run", new=capturing_run):
            resp = client.get("/api/v2/analysis/RELIANCE?horizon=long&risk=aggressive")

        assert resp.status_code == 200
        assert captured["horizon"] == "long"
        assert captured["risk"] == "aggressive"


# ═════════════════════════════════════════════════════════════════════════════
# v2_analysis route — GET /api/v2/analysis/{symbol}/report
# ═════════════════════════════════════════════════════════════════════════════

class TestV2ReportEndpoint:
    def test_200_returns_pdf_content_type(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE/report")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    def test_200_pdf_magic_bytes(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE/report")
        assert resp.content[:4] == b"%PDF"

    def test_content_disposition_includes_symbol(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE/report?tier=apex")
        assert "RELIANCE" in resp.headers.get("content-disposition", "")

    def test_content_disposition_includes_tier(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE/report?tier=apex")
        assert "apex" in resp.headers.get("content-disposition", "")

    def test_report_insufficient_data_returns_422(self):
        from agents.orchestrator import InsufficientDataError
        exc = InsufficientDataError({"technical": 1}, {"technical": 5})
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(exc=exc)):
            resp = client.get("/api/v2/analysis/RELIANCE/report")
        assert resp.status_code == 422

    def test_report_runtime_error_returns_503(self):
        exc = RuntimeError("pipeline down")
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(exc=exc)):
            resp = client.get("/api/v2/analysis/RELIANCE/report")
        assert resp.status_code == 503

    def test_tier_stellar_accepted(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE/report?tier=stellar")
        assert resp.status_code == 200

    def test_tier_orbiter_accepted(self):
        result = _mock_result()
        with patch("routers.v2_analysis.orch_run", new=_make_orch_mock(result)):
            resp = client.get("/api/v2/analysis/RELIANCE/report?tier=orbiter")
        assert resp.status_code == 200

    def test_invalid_tier_returns_422(self):
        resp = client.get("/api/v2/analysis/RELIANCE/report?tier=platinum")
        assert resp.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# _map_verdict / _map_confidence direct unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestHelpers:
    def test_map_verdict_unknown_signal_defaults_to_hold(self):
        assert _map_verdict("unknown") == "HOLD"

    def test_map_confidence_boundary_at_0_7(self):
        # exactly 0.7 is NOT above 0.7, so it should be "Medium"
        assert _map_confidence(0.7) == "Medium"

    def test_map_confidence_boundary_at_0_5(self):
        # exactly 0.5 is NOT above 0.5, so it should be "Low"
        assert _map_confidence(0.5) == "Low"
