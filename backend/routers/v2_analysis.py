"""
v2_analysis.py — New analysis endpoint using the full agent pipeline (M0–M5).

Endpoints:
  GET /api/v2/analysis/{symbol}?horizon=short&risk=moderate&sector=
  GET /api/v2/analysis/{symbol}/report?horizon=short&risk=moderate&tier=stellar

The v1 endpoint (/api/v1/analysis) remains untouched — v2 is additive.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from agents.orchestrator import run as orch_run, InsufficientDataError
from agents.agent_report import build_report
from schemas.messages import FetchRequest, UserProfile, Horizon, Risk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/analysis", tags=["AI Analysis v2"])

# Risk param → PDF risk_level string
_RISK_TO_LEVEL = {
    "conservative": "low",
    "moderate":     "medium",
    "aggressive":   "high",
}


@router.get("/{symbol}")
async def get_analysis_v2(
    symbol: str,
    horizon: str = Query(
        default="short",
        pattern="^(short|long)$",
        description="Investment horizon: short | long",
    ),
    risk: str = Query(
        default="moderate",
        pattern="^(conservative|moderate|aggressive)$",
        description="Risk appetite: conservative | moderate | aggressive",
    ),
    sector: str = Query(
        default="",
        description="Optional sector filter for peer selection",
    ),
):
    """
    Run the full agent pipeline (M0-M5) for the given stock symbol and user profile.

    Returns an AnalysisResult JSON object.

    Raises:
        422 — InsufficientDataError (not enough market data to produce a valid analysis).
        503 — Pipeline unavailable (transient LLM/data error).
    """
    request = FetchRequest(
        stock=symbol.upper(),
        as_of_date=date.today(),
        profile=UserProfile(
            horizon=Horizon(horizon),
            risk=Risk(risk),
            sector=sector,
        ),
        request_id=str(uuid4()),
    )

    try:
        result, _admin_view = await orch_run(request)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("v2 analysis pipeline error for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail="Analysis pipeline unavailable")

    return result.model_dump(mode="json")


@router.get("/{symbol}/report")
async def download_analysis_report_v2(
    symbol: str,
    horizon: str = Query(
        default="short",
        pattern="^(short|long)$",
        description="Investment horizon: short | long",
    ),
    risk: str = Query(
        default="moderate",
        pattern="^(conservative|moderate|aggressive)$",
        description="Risk appetite: conservative | moderate | aggressive",
    ),
    sector: str = Query(
        default="",
        description="Optional sector filter for peer selection",
    ),
    tier: str = Query(
        default="stellar",
        pattern="^(orbiter|stellar|apex)$",
        description="Report tier: orbiter | stellar | apex",
    ),
):
    """
    Run the full agent pipeline and return a PDF report.

    Returns a PDF file download.

    Raises:
        422 — InsufficientDataError (not enough market data).
        503 — Pipeline unavailable.
    """
    request = FetchRequest(
        stock=symbol.upper(),
        as_of_date=date.today(),
        profile=UserProfile(
            horizon=Horizon(horizon),
            risk=Risk(risk),
            sector=sector,
        ),
        request_id=str(uuid4()),
    )

    try:
        result, _admin_view = await orch_run(request)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("v2 report pipeline error for %s: %s", symbol, exc)
        raise HTTPException(status_code=503, detail="Analysis pipeline unavailable")

    risk_level = _RISK_TO_LEVEL.get(risk, "medium")
    pdf_bytes = build_report(result, tier=tier, risk_level=risk_level)

    safe_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-", "_"}) or "STOCK"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_symbol}_{tier}_v2.pdf"',
        },
    )
