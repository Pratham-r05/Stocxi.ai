"""
v2_analysis.py — New analysis endpoint using the full agent pipeline (M0–M5).

Endpoints:
  GET /api/v2/analysis/{symbol}?horizon=short&risk=moderate&sector=
  GET /api/v2/analysis/{symbol}/report?horizon=short&risk=moderate&tier=stellar

The v1 endpoint (/api/v1/analysis) remains untouched — v2 is additive.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from agents.orchestrator import run as orch_run, InsufficientDataError
from agents.agent_report import build_report
from schemas.messages import FetchRequest, UserProfile, Horizon, Risk
from services.simple_analysis_service import generate as simple_generate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/analysis", tags=["AI Analysis v2"])

_GRAPH_DIR = Path(__file__).parents[2] / "graphify-out" / "stocks"
_ROOT = Path(__file__).parents[2]
_DATA_DIR = _ROOT / "data"
_GRAPH_BUILD_TIMEOUT_S = 90

# Risk param → PDF risk_level string
_RISK_TO_LEVEL = {
    "conservative": "low",
    "moderate":     "medium",
    "aggressive":   "high",
}


def _html_to_text(html_text: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n")
    except Exception:
        stripped = re.sub(r"<(script|style).*?</\1>", "", html_text, flags=re.I | re.S)
        stripped = re.sub(r"<[^>]+>", "\n", stripped)
        return html.unescape(stripped)


def _text_pdf(title: str, lines: list[str], filename_note: str = "") -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 42
    y = height - margin

    def new_page() -> None:
        nonlocal y
        pdf.showPage()
        y = height - margin

    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin, y, title[:74])
    y -= 26
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin, y, filename_note[:110])
    y -= 24
    pdf.line(margin, y, width - margin, y)
    y -= 20

    pdf.setFont("Helvetica", 10)
    for raw in lines:
        text = " ".join(raw.replace("₹", "INR ").split())
        if not text:
            y -= 8
            continue
        for chunk in [text[i:i + 105] for i in range(0, len(text), 105)]:
            if y < margin:
                new_page()
                pdf.setFont("Helvetica", 10)
            pdf.drawString(margin, y, chunk)
            y -= 14

    pdf.save()
    return buffer.getvalue()


def _latest_graph_path(symbol: str) -> Path | None:
    symbol_dir = _GRAPH_DIR / symbol.upper()
    if not symbol_dir.exists():
        return None
    html_files = [p for p in symbol_dir.glob("*.html") if p.is_file()]
    if not html_files:
        return None
    return max(html_files, key=lambda p: p.stat().st_mtime)


async def _run_graph_builder(symbol: str) -> Path:
    safe_symbol = symbol.upper().strip()
    data_path = _DATA_DIR / f"{safe_symbol}_data.md"
    if not data_path.exists():
        raise FileNotFoundError(
            f"Knowledge data not found for {safe_symbol}. Run analysis first."
        )

    proc = await asyncio.create_subprocess_exec(
        "python3",
        str(_ROOT / "build_knowledge_graph.py"),
        safe_symbol,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_ROOT),
    )
    try:
        _stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_GRAPH_BUILD_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError("Knowledge graph generation timed out")

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")[-1000:]
        raise RuntimeError(f"Knowledge graph generation failed: {msg}")

    latest = _latest_graph_path(safe_symbol)
    if not latest:
        raise FileNotFoundError("Knowledge graph builder finished without HTML output")
    return latest


async def _resolve_graph_path(symbol: str, as_of_date: str = "") -> Path:
    safe_symbol = symbol.upper().strip()
    if as_of_date:
        dated_path = _GRAPH_DIR / safe_symbol / f"{as_of_date}.html"
        if dated_path.exists():
            return dated_path

    latest = _latest_graph_path(safe_symbol)
    if latest:
        return latest

    return await _run_graph_builder(safe_symbol)


@router.get("/{symbol}")
async def get_analysis_v2(
    symbol: str,
    horizon: str = Query(
        default="short",
        pattern="^(short|medium|long)$",
        description="Investment horizon: short | medium | long",
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
        pattern="^(short|medium|long)$",
        description="Investment horizon: short | medium | long",
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


@router.get("/{symbol}/generate")
async def generate_simple_analysis(
    symbol: str,
    horizon: str = Query(
        default="short",
        pattern="^(short|medium|long)$",
        description="Investment horizon",
    ),
    risk: str = Query(
        default="moderate",
        pattern="^(conservative|moderate|aggressive)$",
        description="Risk appetite",
    ),
):
    """
    Run the simplified analysis pipeline: fetch data → build KG → Gemini → HTML.

    Returns JSON with analysis_html and kg_html strings ready to embed.
    Caches output for 23 hours per (symbol, horizon, risk) combination.

    Raises:
        503 — pipeline failure (data fetch or Gemini error).
    """
    try:
        result = await simple_generate(symbol.upper(), horizon, risk)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("simple analysis pipeline error for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Analysis pipeline failed: {exc}")
    return result


@router.get("/{symbol}/generate/report")
async def download_simple_analysis_report(
    symbol: str,
    horizon: str = Query(
        default="short",
        pattern="^(short|medium|long)$",
        description="Investment horizon",
    ),
    risk: str = Query(
        default="moderate",
        pattern="^(conservative|moderate|aggressive)$",
        description="Risk appetite",
    ),
):
    """Download the visible AI analysis as a PDF."""
    try:
        result = await simple_generate(symbol.upper(), horizon, risk)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("simple analysis PDF error for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Analysis PDF failed: {exc}")

    safe_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-", "_"}) or "STOCK"
    text = _html_to_text(result.get("analysis_html") or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pdf_bytes = _text_pdf(
        title=f"{safe_symbol} AI Analysis",
        lines=lines,
        filename_note=f"Horizon: {horizon} | Risk: {risk}",
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_symbol}_{horizon}_{risk}_analysis.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{symbol}/graph/report")
async def download_knowledge_graph_report(symbol: str):
    """Download the current knowledge graph as a PDF."""
    try:
        graph_path = await _resolve_graph_path(symbol)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("knowledge graph PDF error for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Knowledge graph PDF failed: {exc}")

    safe_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in {"-", "_"}) or "STOCK"
    text = _html_to_text(graph_path.read_text(encoding="utf-8"))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pdf_bytes = _text_pdf(
        title=f"{safe_symbol} Knowledge Graph",
        lines=lines[:260],
        filename_note=f"Source graph: {graph_path.name}",
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_symbol}_knowledge_graph.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{symbol}/graph")
async def get_knowledge_graph(
    symbol: str,
    as_of_date: str = Query(
        default="",
        description="ISO date string (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Serve or generate the standalone knowledge graph HTML."""
    try:
        graph_path = await _resolve_graph_path(symbol, as_of_date)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("knowledge graph generation error for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=503, detail=str(exc))

    return HTMLResponse(
        content=graph_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )
