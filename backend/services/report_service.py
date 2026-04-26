"""report_service.py - Build professional tiered stock report PDFs with charts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from textwrap import wrap
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


def _ascii_clean(value: Any) -> str:
    """Normalize unicode-heavy strings to PDF-safe ASCII text."""
    text = str(value or "")
    replacements = {
        "₹": "INR ",
        "—": "-",
        "–": "-",
        "−": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "•": "-",
        "…": "...",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    out_chars: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch in {"\n", "\t"} or 32 <= code <= 126:
            out_chars.append(ch)
        else:
            out_chars.append(" ")
    cleaned = "".join(out_chars)
    return " ".join(cleaned.split())


def _to_text(value: Any, fallback: str = "N/A") -> str:
    """Convert arbitrary values to readable text for PDF rendering."""
    if value is None:
        return fallback
    text = _ascii_clean(value).strip()
    return text if text else fallback


def _to_float(value: Any) -> float | None:
    """Convert arbitrary values to float while safely handling malformed input."""
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _fmt_money(value: Any) -> str:
    """Format numeric values as INR-friendly compact strings."""
    number = _to_float(value)
    if number is None:
        return "N/A"
    return f"INR {number:,.2f}"


def _fmt_pct(value: Any) -> str:
    """Format numeric values as percentages."""
    number = _to_float(value)
    if number is None:
        return "N/A"
    return f"{number:.2f}%"


def _limit_text(text: str, max_chars: int) -> str:
    """Clamp text length so report content fits on a single PDF page."""
    clean = _ascii_clean(text)
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "..."


def _safe_list(value: Any, limit: int = 4) -> list[str]:
    """Normalize mixed input into a bounded string list for bullet rendering."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _limit_text(_to_text(item, ""), 180)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _metric_line(label: str, value: Any) -> str:
    """Format one metric as a short readable key-value string."""
    return f"{label}: {_to_text(value)}"


def _draw_wrapped_block(
    c: canvas.Canvas,
    *,
    text: str,
    x: float,
    y: float,
    width: float,
    font_name: str = "Helvetica",
    font_size: int = 9,
    color: str = "#111827",
    leading: float = 1.35,
    max_chars: int = 1200,
) -> float:
    """Draw wrapped text and return the updated y position."""
    safe_text = _limit_text(text, max_chars)
    if not safe_text:
        return y

    wrap_width = max(30, int(width / (font_size * 0.52)))
    lines = wrap(safe_text, wrap_width)
    if not lines:
        return y

    line_height = font_size * leading
    c.setFont(font_name, font_size)
    c.setFillColor(HexColor(color))
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
    return y


def _draw_section_header(c: canvas.Canvas, *, title: str, x: float, y: float, page_width: float, margin: float) -> float:
    """Draw section divider line and heading, then return updated y."""
    c.setStrokeColor(HexColor("#d1d5db"))
    c.setLineWidth(0.8)
    c.line(margin, y, page_width - margin, y)
    y -= 14
    return _draw_wrapped_block(
        c,
        text=title,
        x=x,
        y=y,
        width=page_width - (margin * 2),
        font_name="Helvetica-Bold",
        font_size=10,
        color="#111827",
        leading=1.15,
        max_chars=120,
    ) - 4


def _draw_bullets(
    c: canvas.Canvas,
    *,
    items: list[str],
    x: float,
    y: float,
    width: float,
    font_size: int = 9,
    color: str = "#111827",
    max_chars_per_item: int = 200,
) -> float:
    """Draw a bullet list and return updated y."""
    for item in items:
        y = _draw_wrapped_block(
            c,
            text=f"- {_limit_text(item, max_chars_per_item)}",
            x=x,
            y=y,
            width=width,
            font_name="Helvetica",
            font_size=font_size,
            color=color,
            leading=1.35,
            max_chars=max_chars_per_item + 10,
        )
        y -= 1
    return y


def _draw_footer(c: canvas.Canvas, *, page_no: int, total_pages: int, margin: float, width: float) -> None:
    """Draw a consistent footer with disclaimer and page number."""
    footer_y = 26
    c.setStrokeColor(HexColor("#e5e7eb"))
    c.setLineWidth(0.6)
    c.line(margin, footer_y + 14, width - margin, footer_y + 14)

    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#6b7280"))
    c.drawString(
        margin,
        footer_y,
        "AI-generated report for informational purposes only. Not investment advice. Consult a SEBI-registered advisor.",
    )
    c.drawRightString(width - margin, footer_y, f"Page {page_no}/{total_pages}")


def _draw_price_momentum_chart(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    price_movement: dict[str, Any],
) -> None:
    """Draw line chart for 1W/1M/6M/1Y percentage move."""
    periods = ["1w", "1mo", "6mo", "1y"]
    labels = ["1W", "1M", "6M", "1Y"]
    values = []
    for p in periods:
        v = _to_float((price_movement.get(p) or {}).get("change_pct"))
        values.append(v if v is not None else 0.0)

    drawing = Drawing(w, h)
    chart = HorizontalLineChart()
    chart.x = 42
    chart.y = 28
    chart.width = max(120, w - 62)
    chart.height = max(60, h - 50)
    chart.data = [values]
    chart.lines[0].strokeColor = HexColor("#1d4ed8")
    chart.lines[0].strokeWidth = 1.8
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fillColor = HexColor("#374151")
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = HexColor("#374151")
    chart.valueAxis.labels.fontSize = 7
    min_v = min(values) if values else -5
    max_v = max(values) if values else 5
    chart.valueAxis.valueMin = min(-5.0, min_v - 1.0)
    chart.valueAxis.valueMax = max(5.0, max_v + 1.0)
    drawing.add(chart)

    renderPDF.draw(drawing, c, x, y)


def _draw_financial_change_chart(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    q: dict[str, Any],
    a: dict[str, Any],
) -> None:
    """Draw bar chart for revenue/profit growth trends from financial snapshot."""
    labels = ["Q Rev", "Q Profit", "A Rev", "A Profit"]
    values = [
        _to_float(q.get("revenue_change_pct")) or 0.0,
        _to_float(q.get("net_profit_change_pct")) or 0.0,
        _to_float(a.get("revenue_change_pct")) or 0.0,
        _to_float(a.get("net_profit_change_pct")) or 0.0,
    ]

    drawing = Drawing(w, h)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 26
    chart.width = max(120, w - 60)
    chart.height = max(60, h - 46)
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fillColor = HexColor("#374151")
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = HexColor("#374151")
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = HexColor("#0ea5e9")
    chart.valueAxis.valueMin = min(-25.0, min(values) - 1.0)
    chart.valueAxis.valueMax = max(25.0, max(values) + 1.0)
    drawing.add(chart)

    renderPDF.draw(drawing, c, x, y)


def _draw_shareholding_chart(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    shareholding: dict[str, Any],
) -> None:
    """Draw bar chart for promoter/FII/DII/public holding mix."""
    labels = ["Promoter", "FII", "DII", "Public"]
    values = [
        _to_float(shareholding.get("promoter_pct")) or 0.0,
        _to_float(shareholding.get("fii_pct")) or 0.0,
        _to_float(shareholding.get("dii_pct")) or 0.0,
        _to_float(shareholding.get("public_pct")) or 0.0,
    ]

    drawing = Drawing(w, h)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 26
    chart.width = max(120, w - 60)
    chart.height = max(60, h - 46)
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fillColor = HexColor("#374151")
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = HexColor("#374151")
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = HexColor("#16a34a")
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(100.0, max(values) + 5.0)
    drawing.add(chart)

    renderPDF.draw(drawing, c, x, y)


def _beginner_action_lines(
    verdict: str,
    confidence: str,
    risk_level: str,
    volume_ratio: float | None,
    trend_signal: str,
) -> list[str]:
    """Build simple beginner-friendly guidance lines for Orbiter page."""
    vol_text = "normal" if volume_ratio is None else ("strong" if volume_ratio >= 1.5 else "weak" if volume_ratio < 0.7 else "normal")
    return [
        f"Current stance is {verdict} with {confidence.lower()} confidence for {risk_level.lower()} risk investors.",
        f"Price trend currently appears {trend_signal.lower()} and volume participation looks {vol_text}.",
        "Start with small position sizing and always define stop-loss before entry.",
    ]


def _build_minimal_pdf(symbol: str, company_name: str, tier: str, reason: str) -> bytes:
    """Build a fallback PDF when detailed rendering fails."""
    buff = BytesIO()
    c = canvas.Canvas(buff, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, _ascii_clean(f"{symbol} - Quick Report"))
    y -= 24

    c.setFont("Helvetica", 10)
    c.drawString(margin, y, _ascii_clean(f"Company: {company_name}"))
    y -= 16
    c.drawString(margin, y, _ascii_clean(f"Tier: {tier.title()}"))
    y -= 16
    c.drawString(margin, y, _ascii_clean(f"Generated (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"))
    y -= 22

    c.setFont("Helvetica", 9)
    lines = wrap(
        _ascii_clean(
            "Detailed report rendering is temporarily unavailable. Please use on-screen sections for full analysis. "
            f"Technical note: {reason}"
        ),
        width=95,
    )
    for line in lines[:7]:
        c.drawString(margin, y, line)
        y -= 13

    y -= 8
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        margin,
        y,
        "This report is AI-assisted and for informational purposes only. Not financial advice.",
    )

    c.showPage()
    c.save()
    return buff.getvalue()


def build_stock_report_pdf(
    *,
    symbol: str,
    company_name: str,
    tier: str,
    risk_level: str,
    report_payload: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    ai_analysis: dict[str, Any],
) -> bytes:
    """Build tier-specific professional PDF report with 1/2/3 page templates and charts."""
    try:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        margin = 34
        max_width = width - (margin * 2)
        y = height - margin

        tier_labels = {
            "orbiter": "Orbiter (Beginner)",
            "stellar": "Stellar (Mediocre)",
            "apex": "Apex (Pro)",
        }
        tier = (tier or "stellar").lower().strip()
        tier_label = tier_labels.get(tier, tier.title())
        total_pages = {"orbiter": 1, "stellar": 2, "apex": 3}.get(tier, 2)

        verdict = _to_text(report_payload.get("verdict"), _to_text(ai_analysis.get("final_verdict"), "HOLD")).upper()
        # SEBI compliance (CLAUDE.md Rule 12): never write "SELL" in user-facing output.
        # Normalize: SELL→AVOID, keep BUY/HOLD/AVOID.
        if verdict == "SELL":
            verdict = "AVOID"

        confidence = _to_text(report_payload.get("confidence"), "Medium")
        investor_fit = _limit_text(_to_text(report_payload.get("investor_fit"), "Balanced for this risk profile."), 140)
        summary = _limit_text(
            _to_text(report_payload.get("executive_summary"), _to_text(ai_analysis.get("plain_english"), "Summary unavailable.")),
            760 if tier == "apex" else 560 if tier == "stellar" else 420,
        )

        key = analysis_snapshot.get("key_indicators") or {}
        tech = analysis_snapshot.get("technical_indicators") or {}
        volume_ctx = (analysis_snapshot.get("volume_exchange_price_context") or {}).get("volume") or {}
        price_move = (analysis_snapshot.get("volume_exchange_price_context") or {}).get("price_movement") or {}
        financial = analysis_snapshot.get("financial_statement_snapshot") or {}
        q = financial.get("quarterly") or {}
        a = financial.get("annual") or {}
        bs = financial.get("balance_sheet") or {}
        cf = financial.get("cash_flow") or {}
        sh = financial.get("shareholding") or {}
        news_items = analysis_snapshot.get("important_news") or []
        ann_items = analysis_snapshot.get("important_announcements") or []

        thesis_points = _safe_list(report_payload.get("thesis_points"), limit=4)
        risk_flags = _safe_list(report_payload.get("risk_flags"), limit=4)
        action_plan = _safe_list(report_payload.get("action_plan"), limit=3)

        if not thesis_points:
            thesis_points = [
                _limit_text(_to_text(ai_analysis.get("fundamentals", {}).get("summary"), "Fundamental view is mixed."), 170),
                _limit_text(_to_text(ai_analysis.get("technicals", {}).get("summary"), "Technical setup is mixed."), 170),
                _limit_text(_to_text(ai_analysis.get("news", {}).get("summary"), "News flow is neutral."), 170),
            ]

        if not risk_flags:
            risk_flags = [
                "Validate position size and stop-loss before entry.",
                "Track next quarterly results and management commentary.",
                "Monitor news and announcements for sudden sentiment shifts.",
            ]

        if not action_plan:
            action_plan = [
                "Review this report with your own risk and time horizon.",
                "Cross-check charts and latest filings before action.",
                "Avoid concentrated exposure in a single stock.",
            ]

        trend_signal = _to_text(price_move.get("trend_signal"), "Sideways")
        volume_ratio = _to_float(volume_ctx.get("volume_ratio_vs_20d"))
        beginner_lines = _beginner_action_lines(
            verdict=verdict,
            confidence=confidence,
            risk_level=risk_level,
            volume_ratio=volume_ratio,
            trend_signal=trend_signal,
        )

        # ----------------------------- Page 1 ---------------------------------
        header_title = _limit_text(report_payload.get("report_title") or f"{symbol} Investment Report", 90)
        y = _draw_wrapped_block(
            c,
            text=header_title,
            x=margin,
            y=y,
            width=max_width,
            font_name="Helvetica-Bold",
            font_size=16,
            color="#111827",
            leading=1.2,
            max_chars=120,
        )
        y = _draw_wrapped_block(
            c,
            text=(
                f"{_to_text(company_name, symbol)} | Tier: {tier_label} | Risk: {risk_level.upper()} | "
                f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
            ),
            x=margin,
            y=y,
            width=max_width,
            font_name="Helvetica",
            font_size=8,
            color="#4b5563",
            leading=1.3,
            max_chars=220,
        )

        y -= 6
        c.setFillColor(HexColor("#eff6ff"))
        c.setStrokeColor(HexColor("#93c5fd"))
        c.roundRect(margin, y - 34, max_width, 30, 6, fill=1, stroke=1)
        c.setFillColor(HexColor("#1e3a8a"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin + 8, y - 18, _ascii_clean(f"FINAL CALL: {verdict} | Confidence: {confidence}"))
        c.setFont("Helvetica", 8)
        c.drawString(margin + 8, y - 30, _ascii_clean(f"Investor Fit: {investor_fit}"))
        y -= 44

        y = _draw_section_header(c, title="Executive Summary", x=margin, y=y, page_width=width, margin=margin)
        y = _draw_wrapped_block(
            c,
            text=summary,
            x=margin,
            y=y,
            width=max_width,
            font_name="Helvetica",
            font_size=9,
            color="#1f2937",
            leading=1.34,
            max_chars=520 if tier == "orbiter" else 700,
        )
        y -= 4

        y = _draw_section_header(c, title="What This Means Now", x=margin, y=y, page_width=width, margin=margin)
        y = _draw_bullets(
            c,
            items=beginner_lines if tier == "orbiter" else thesis_points,
            x=margin,
            y=y,
            width=max_width,
            font_size=9,
            color="#111827",
            max_chars_per_item=180,
        )

        y -= 2
        y = _draw_section_header(c, title="Quick Data Snapshot", x=margin, y=y, page_width=width, margin=margin)
        left_x = margin
        right_x = margin + (max_width / 2) + 6
        row_y = y
        left_lines = [
            _metric_line("Price", _fmt_money(key.get("price"))),
            _metric_line("PE", key.get("pe_ratio")),
            _metric_line("PB", key.get("pb_ratio")),
            _metric_line("EPS", key.get("eps")),
            _metric_line("MCap", _fmt_money(key.get("market_cap"))),
        ]
        right_lines = [
            _metric_line("RSI", tech.get("rsi")),
            _metric_line("MACD", tech.get("macd")),
            _metric_line("ADX", tech.get("adx")),
            _metric_line("Overall", tech.get("overall_signal")),
            _metric_line("Volume Ratio", volume_ctx.get("volume_ratio_vs_20d")),
        ]
        for line in left_lines:
            row_y = _draw_wrapped_block(
                c,
                text=line,
                x=left_x,
                y=row_y,
                width=(max_width / 2) - 12,
                font_name="Helvetica",
                font_size=8,
                color="#111827",
                leading=1.35,
                max_chars=90,
            )
        row_y2 = y
        for line in right_lines:
            row_y2 = _draw_wrapped_block(
                c,
                text=line,
                x=right_x,
                y=row_y2,
                width=(max_width / 2) - 12,
                font_name="Helvetica",
                font_size=8,
                color="#111827",
                leading=1.35,
                max_chars=90,
            )
        y = min(row_y, row_y2) - 8

        # Keep chart compact for 1-page Orbiter output.
        chart_h = 110 if tier == "orbiter" else 120
        c.setFillColor(HexColor("#f8fafc"))
        c.setStrokeColor(HexColor("#dbeafe"))
        c.roundRect(margin, y - chart_h, max_width, chart_h, 6, fill=1, stroke=1)
        _draw_price_momentum_chart(
            c,
            x=margin + 4,
            y=y - chart_h + 6,
            w=max_width - 8,
            h=chart_h - 10,
            price_movement=price_move,
        )
        c.setFillColor(HexColor("#1f2937"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin + 8, y - 12, "Price Momentum Chart (1W / 1M / 6M / 1Y Change%)")
        y -= chart_h + 4

        if tier == "orbiter":
            y = _draw_section_header(c, title="Risk Flags", x=margin, y=y, page_width=width, margin=margin)
            y = _draw_bullets(
                c,
                items=risk_flags[:3],
                x=margin,
                y=y,
                width=max_width,
                font_size=8,
                color="#111827",
                max_chars_per_item=170,
            )
            y = _draw_section_header(c, title="Action Plan", x=margin, y=y, page_width=width, margin=margin)
            _draw_bullets(
                c,
                items=action_plan,
                x=margin,
                y=y,
                width=max_width,
                font_size=8,
                color="#111827",
                max_chars_per_item=160,
            )

        _draw_footer(c, page_no=1, total_pages=total_pages, margin=margin, width=width)

        # ----------------------------- Page 2 ---------------------------------
        if tier in {"stellar", "apex"}:
            c.showPage()
            y = height - margin
            y = _draw_wrapped_block(
                c,
                text=f"{symbol} Detailed Review",
                x=margin,
                y=y,
                width=max_width,
                font_name="Helvetica-Bold",
                font_size=15,
                color="#111827",
                leading=1.2,
                max_chars=100,
            )
            y = _draw_wrapped_block(
                c,
                text=f"{_to_text(company_name)} | Tier: {tier_label} | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
                x=margin,
                y=y,
                width=max_width,
                font_name="Helvetica",
                font_size=8,
                color="#4b5563",
                leading=1.3,
                max_chars=220,
            )

            y -= 6
            y = _draw_section_header(c, title="Fundamental, Technical and News View", x=margin, y=y, page_width=width, margin=margin)
            deep_lines = [
                _to_text(report_payload.get("fundamental_view"), _to_text(ai_analysis.get("fundamentals", {}).get("summary"), "Fundamental view unavailable.")),
                _to_text(report_payload.get("technical_view"), _to_text(ai_analysis.get("technicals", {}).get("summary"), "Technical view unavailable.")),
                _to_text(report_payload.get("news_announcements_view"), _to_text(ai_analysis.get("news", {}).get("summary"), "News view unavailable.")),
                _to_text(report_payload.get("financial_health_view"), "Financial health details are limited."),
            ]
            for line in deep_lines:
                y = _draw_wrapped_block(
                    c,
                    text=line,
                    x=margin,
                    y=y,
                    width=max_width,
                    font_name="Helvetica",
                    font_size=9,
                    color="#111827",
                    leading=1.35,
                    max_chars=280,
                )
                y -= 2

            y -= 2
            y = _draw_section_header(c, title="Financial Trend Chart", x=margin, y=y, page_width=width, margin=margin)
            c.setFillColor(HexColor("#f8fafc"))
            c.setStrokeColor(HexColor("#dbeafe"))
            c.roundRect(margin, y - 150, max_width, 146, 6, fill=1, stroke=1)
            _draw_financial_change_chart(
                c,
                x=margin + 4,
                y=y - 146,
                w=max_width - 8,
                h=138,
                q=q,
                a=a,
            )
            c.setFillColor(HexColor("#1f2937"))
            c.setFont("Helvetica-Bold", 8)
            c.drawString(margin + 8, y - 12, "Revenue and Profit Growth (%) by Quarterly and Annual Snapshot")
            y -= 158

            y = _draw_section_header(c, title="Risk Flags and Action Plan", x=margin, y=y, page_width=width, margin=margin)
            y = _draw_bullets(
                c,
                items=risk_flags,
                x=margin,
                y=y,
                width=max_width,
                font_size=8,
                color="#111827",
                max_chars_per_item=180,
            )
            y = _draw_bullets(
                c,
                items=action_plan,
                x=margin,
                y=y,
                width=max_width,
                font_size=8,
                color="#111827",
                max_chars_per_item=180,
            )

            y -= 2
            y = _draw_section_header(c, title="Coverage Matrix", x=margin, y=y, page_width=width, margin=margin)
            coverage_lines = [
                f"Key indicators: Price {_fmt_money(key.get('price'))}, PE {_to_text(key.get('pe_ratio'))}, PB {_to_text(key.get('pb_ratio'))}, EPS {_to_text(key.get('eps'))}",
                f"Price movement: 1W {_fmt_pct((price_move.get('1w') or {}).get('change_pct'))}, 1M {_fmt_pct((price_move.get('1mo') or {}).get('change_pct'))}, 6M {_fmt_pct((price_move.get('6mo') or {}).get('change_pct'))}, trend {_to_text(price_move.get('trend_signal'))}",
                f"Balance and cash: Borrowings {_fmt_money(bs.get('borrowings_latest'))}, Operating cash flow {_fmt_money(cf.get('operating_cash_flow_latest'))}",
                f"Shareholding: Promoter {_fmt_pct(sh.get('promoter_pct'))}, FII {_fmt_pct(sh.get('fii_pct'))}, DII {_fmt_pct(sh.get('dii_pct'))}, Public {_fmt_pct(sh.get('public_pct'))}",
                f"Top news: {_limit_text(_to_text((news_items[0] or {}).get('title') if news_items else 'No major headline'), 120)}",
                f"Top announcement: {_limit_text(_to_text((ann_items[0] or {}).get('subject') if ann_items else 'No major filing'), 120)}",
            ]
            for line in coverage_lines:
                y = _draw_wrapped_block(
                    c,
                    text=line,
                    x=margin,
                    y=y,
                    width=max_width,
                    font_name="Helvetica",
                    font_size=8,
                    color="#111827",
                    leading=1.3,
                    max_chars=240,
                )

            _draw_footer(c, page_no=2, total_pages=total_pages, margin=margin, width=width)

        # ----------------------------- Page 3 ---------------------------------
        if tier == "apex":
            c.showPage()
            y = height - margin
            y = _draw_wrapped_block(
                c,
                text=f"{symbol} Pro Technical Appendix",
                x=margin,
                y=y,
                width=max_width,
                font_name="Helvetica-Bold",
                font_size=15,
                color="#111827",
                leading=1.2,
                max_chars=110,
            )
            y = _draw_wrapped_block(
                c,
                text=(
                    f"{_to_text(company_name)} | Advanced tier structure with ownership mix and scenario framework | "
                    f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
                ),
                x=margin,
                y=y,
                width=max_width,
                font_name="Helvetica",
                font_size=8,
                color="#4b5563",
                leading=1.3,
                max_chars=260,
            )

            y -= 6
            y = _draw_section_header(c, title="Advanced Technical Matrix", x=margin, y=y, page_width=width, margin=margin)
            matrix_lines = [
                f"Signal stack: Overall {_to_text(tech.get('overall_signal'))}, EMA {_to_text(tech.get('ema_signal'))}, BB {_to_text(tech.get('bb_signal'))}, MACD {_to_text(tech.get('macd_signal'))}",
                f"Momentum profile: RSI {_to_text(tech.get('rsi'))}, ADX {_to_text(tech.get('adx'))}, ATR {_to_text(tech.get('atr'))}, volume ratio {_to_text(volume_ctx.get('volume_ratio_vs_20d'))}",
                f"Trend profile: 1W {_fmt_pct((price_move.get('1w') or {}).get('change_pct'))}, 1M {_fmt_pct((price_move.get('1mo') or {}).get('change_pct'))}, 6M {_fmt_pct((price_move.get('6mo') or {}).get('change_pct'))}, 1Y {_fmt_pct((price_move.get('1y') or {}).get('change_pct'))}, trend {_to_text(price_move.get('trend_signal'))}",
            ]
            for line in matrix_lines:
                y = _draw_wrapped_block(
                    c,
                    text=line,
                    x=margin,
                    y=y,
                    width=max_width,
                    font_name="Helvetica",
                    font_size=8,
                    color="#111827",
                    leading=1.33,
                    max_chars=260,
                )
                y -= 2

            y = _draw_section_header(c, title="Ownership Concentration Chart", x=margin, y=y, page_width=width, margin=margin)
            c.setFillColor(HexColor("#f8fafc"))
            c.setStrokeColor(HexColor("#dcfce7"))
            c.roundRect(margin, y - 150, max_width, 146, 6, fill=1, stroke=1)
            _draw_shareholding_chart(
                c,
                x=margin + 4,
                y=y - 146,
                w=max_width - 8,
                h=138,
                shareholding=sh,
            )
            c.setFillColor(HexColor("#1f2937"))
            c.setFont("Helvetica-Bold", 8)
            c.drawString(margin + 8, y - 12, "Shareholding Mix (%) - Promoter / FII / DII / Public")
            y -= 156

            y = _draw_section_header(c, title="Scenario Framework", x=margin, y=y, page_width=width, margin=margin)
            bull_case = (
                f"Bull case: Trend shifts from {_to_text(price_move.get('trend_signal'))} to sustained uptrend with "
                f"volume ratio above 1.5x and improving quarterly growth profile."
            )
            base_case = (
                f"Base case: Mixed signal regime persists with range-bound behavior and selective rotational flows around earnings updates."
            )
            bear_case = (
                f"Bear case: Weak momentum continuation with low participation, negative earnings surprise, and downside trend extension."
            )
            y = _draw_bullets(
                c,
                items=[bull_case, base_case, bear_case],
                x=margin,
                y=y,
                width=max_width,
                font_size=8,
                color="#111827",
                max_chars_per_item=220,
            )

            y = _draw_section_header(c, title="Execution Checklist", x=margin, y=y, page_width=width, margin=margin)
            checklist = [
                "Confirm entry trigger with price + volume alignment, not price alone.",
                "Map invalidation level before position sizing; avoid post-entry stop drift.",
                "Track event calendar: earnings, guidance, filings, and key sector catalysts.",
                "Reassess exposure if ownership flows and trend structure diverge materially.",
            ]
            _draw_bullets(
                c,
                items=checklist,
                x=margin,
                y=y,
                width=max_width,
                font_size=8,
                color="#111827",
                max_chars_per_item=210,
            )

            _draw_footer(c, page_no=3, total_pages=total_pages, margin=margin, width=width)

        c.save()
        return buffer.getvalue()
    except Exception as e:
        logger.warning(f"PDF report build failed for {symbol}: {e}")
        return _build_minimal_pdf(symbol, company_name, tier, str(e))
