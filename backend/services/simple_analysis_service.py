"""
simple_analysis_service.py — Simplified AI analysis pipeline for the frontend.

Pipeline per request:
  1. Run fetch_phase1_data.py as subprocess → creates/refreshes data/{SYMBOL}_data.md
     (skipped if file is < DATA_FRESHNESS_H hours old)
  2. Build 3D knowledge graph HTML using build_knowledge_graph functions
  3. Call Gemini to generate Markdown analysis report
  4. Wrap Markdown in HTML template; save both files to analysis-out/{SYMBOL}/
  5. Return (analysis_html: str, kg_html: str, cached: bool)

Risk → user_level mapping:
  conservative → beginner
  moderate     → medium
  aggressive   → pro
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_ROOT       = Path(__file__).parents[2]          # stocxi/
_DATA_DIR   = _ROOT / "data"
_OUT_DIR    = _ROOT / "analysis-out"
_GRAPHIFY_DIR = _ROOT / "graphify-out" / "stocks"

DATA_FRESHNESS_H = 12   # re-fetch if data file is older than this
ANALYSIS_TEMPLATE_VERSION = "v4"

UserLevel = Literal["beginner", "medium", "pro"]
Horizon   = Literal["short", "medium", "long"]

RISK_TO_LEVEL: dict[str, UserLevel] = {
    "conservative": "beginner",
    "moderate":     "medium",
    "aggressive":   "pro",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _data_path(symbol: str) -> Path:
    return _DATA_DIR / f"{symbol.upper()}_data.md"


def _out_paths(symbol: str, horizon: Horizon, level: UserLevel, today: str) -> tuple[Path, Path]:
    """Return (analysis_html_path, kg_html_path)."""
    sym_dir = _OUT_DIR / symbol.upper()
    sym_dir.mkdir(parents=True, exist_ok=True)
    analysis = sym_dir / f"{horizon}_{level}_{ANALYSIS_TEMPLATE_VERSION}_{today}.html"
    kg        = sym_dir / f"kg_{horizon}_{today}.html"
    return analysis, kg


def _is_fresh(path: Path, max_age_h: float) -> bool:
    if not path.exists():
        return False
    age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
    return age_h < max_age_h


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def _render_markdown(md_text: str) -> str:
    """Render the fixed Gemini Markdown subset without runtime JS."""
    parts: list[str] = []
    paragraph: list[str] = []
    list_tag: str | None = None
    in_code = False
    code_lines: list[str] = []
    table_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body = " ".join(line.strip() for line in paragraph).strip()
            if body:
                parts.append(f"<p>{_inline_markdown(body)}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            parts.append(f"</{list_tag}>")
            list_tag = None

    def is_table_row(value: str) -> bool:
        return value.startswith("|") and value.endswith("|") and value.count("|") >= 2

    def is_separator_row(value: str) -> bool:
        cells = [cell.strip() for cell in value.strip("|").split("|")]
        return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)

    def flush_table() -> None:
        nonlocal table_lines
        if len(table_lines) < 2:
            for row in table_lines:
                parts.append(f"<p>{_inline_markdown(row)}</p>")
            table_lines = []
            return

        rows = [[cell.strip() for cell in row.strip("|").split("|")] for row in table_lines]
        header = rows[0]
        body_rows = rows[2:] if len(rows) > 1 and is_separator_row(table_lines[1]) else rows[1:]
        parts.append("<div class=\"table-wrap\"><table>")
        parts.append("<thead><tr>" + "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in header) + "</tr></thead>")
        parts.append("<tbody>")
        for row in body_rows:
            padded = row + [""] * max(0, len(header) - len(row))
            parts.append("<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in padded[:len(header)]) + "</tr>")
        parts.append("</tbody></table></div>")
        table_lines = []

    for raw in md_text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            close_list()
            flush_table()
            continue

        if is_table_row(stripped):
            flush_paragraph()
            close_list()
            table_lines.append(stripped)
            continue

        flush_table()

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            parts.append(f"<h{level}>{_inline_markdown(heading.group(2).strip())}</h{level}>")
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if bullet or ordered:
            flush_paragraph()
            next_tag = "ul" if bullet else "ol"
            if list_tag != next_tag:
                close_list()
                list_tag = next_tag
                parts.append(f"<{list_tag}>")
            item = (bullet or ordered).group(1)
            parts.append(f"<li>{_inline_markdown(item)}</li>")
            continue

        close_list()
        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    flush_table()
    if in_code:
        parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(parts)


def _analysis_html_template(md_text: str, symbol: str, horizon: Horizon, level: UserLevel) -> str:
    """Wrap Gemini Markdown in a styled, self-contained HTML page."""
    label_h = {"short": "Short-Term (1–3M)", "medium": "Medium-Term (3M–1Y)", "long": "Long-Term (1–5Y)"}
    report_html = _render_markdown(md_text)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{symbol.upper()} — {label_h[horizon]} Analysis ({level.capitalize()})</title>
  <style>
    :root {{ color-scheme: dark; background: #000; }}
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; min-height: 100%; margin: 0; background: #000; }}
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: #d4d4d8;
      line-height: 1.75;
      font-size: 16px;
      overflow: hidden;
    }}
    #content {{ width: 100%; max-width: 100%; padding: 2px 0 48px; }}
    h1 {{
      color: #fff;
      border-bottom: 1px solid #27272a;
      padding-bottom: 18px;
      margin: 0 0 34px;
      font-size: 2.1rem;
      font-weight: 800;
      letter-spacing: 0;
      line-height: 1.15;
    }}
    h2 {{
      color: #f4f4f5;
      margin: 48px 0 14px;
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: 0;
      line-height: 1.25;
    }}
    h3 {{ color: #e4e4e7; font-size: 1.1rem; font-weight: 650; margin: 28px 0 10px; }}
    h4 {{ color: #e4e4e7; font-weight: 650; margin: 22px 0 8px; }}
    p {{ margin: 0 0 18px; }}
    .table-wrap {{
      width: 100%;
      max-width: 100%;
      margin: 24px 0;
      overflow-x: auto;
      border: 1px solid #27272a;
      border-radius: 8px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 0.95em;
    }}
    th {{ background: #18181b; color: #f4f4f5; padding: 12px; text-align: left; border: 1px solid #27272a; }}
    td {{ padding: 12px; border: 1px solid #27272a; color: #d4d4d8; }}
    tr:hover td {{ background: #18181b; }}
    code {{ background: #18181b; padding: 3px 6px; border-radius: 6px; font-size: 0.88em; color: #c4b5fd; border: 1px solid #27272a; }}
    pre {{ background: #09090b; padding: 20px; border-radius: 8px; overflow-x: auto; border: 1px solid #27272a; }}
    blockquote {{ border-left: 3px solid #71717a; padding-left: 18px; color: #a1a1aa; margin: 22px 0; font-style: italic; }}
    a {{ color: #a5b4fc; text-decoration: none; overflow-wrap: anywhere; }}
    a:hover {{ text-decoration: underline; }}
    strong {{ color: #fff; font-weight: 650; }}
    ul, ol {{ padding-left: 1.35em; margin: 14px 0 20px; }}
    li {{ margin: 8px 0; }}
    hr {{ border: none; border-top: 1px solid #27272a; margin: 40px 0; }}
    @media (max-width: 640px) {{
      body {{ font-size: 15px; }}
      h1 {{ font-size: 1.65rem; }}
      h2 {{ font-size: 1.18rem; }}
      th, td {{ padding: 10px; }}
    }}
  </style>
</head>
<body>
  <article id="content">{report_html}</article>
</body>
</html>"""


def _clean_markdown(md_text: str) -> str:
    """Normalize Gemini markdown so it renders cleanly in HTML."""
    from analysis.gemini_analysis import standardize_report_markdown
    return standardize_report_markdown(md_text)


# ── Subprocess: fetch_phase1_data.py ─────────────────────────────────────────

async def _run_fetch_phase1(symbol: str, horizon: Horizon) -> None:
    """Run fetch_phase1_data.py as a subprocess. Raises RuntimeError on failure."""
    logger.info("simple_analysis: running fetch_phase1_data for %s (%s)", symbol, horizon)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_ROOT / "fetch_phase1_data.py"),
        symbol.upper(), horizon,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_ROOT),
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=360)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("fetch_phase1_data timed out after 6 minutes")
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")[-800:]
        raise RuntimeError(f"fetch_phase1_data failed (exit {proc.returncode}): {msg}")
    logger.info("simple_analysis: fetch_phase1_data complete for %s", symbol)


# ── Knowledge graph builder ───────────────────────────────────────────────────

def _build_kg_html_sync(symbol: str) -> str:
    """Build KG HTML synchronously using build_knowledge_graph module."""
    # Add project root to path so build_knowledge_graph is importable
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    import importlib
    bkg = importlib.import_module("build_knowledge_graph")

    data_path = _data_path(symbol)
    meta, nodes = bkg.parse_md(data_path)
    graph_data  = bkg.build_graph_data(symbol.upper(), meta, nodes)
    return bkg.render_html(symbol.upper(), meta, graph_data)


async def _build_kg_html(symbol: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _build_kg_html_sync, symbol)


# ── Gemini analysis ───────────────────────────────────────────────────────────

def _run_gemini_sync(symbol: str, horizon: Horizon, level: UserLevel, kg_link: str) -> str:
    """Call gemini_analysis.run_analysis in a thread-safe way."""
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    if str(_ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(_ROOT / "backend"))

    from analysis.gemini_analysis import run_analysis  # type: ignore
    return run_analysis(symbol.upper(), horizon, level, kg_link=kg_link)


async def _run_gemini(symbol: str, horizon: Horizon, level: UserLevel, kg_link: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_gemini_sync, symbol, horizon, level, kg_link)


# ── Public entry point ────────────────────────────────────────────────────────

async def generate(
    symbol:  str,
    horizon: str,
    risk:    str,
) -> dict:
    """
    Run the simplified analysis pipeline for one stock.

    Args:
        symbol:  NSE ticker (e.g. "ADANIPOWER")
        horizon: "short" | "medium" | "long"
        risk:    "conservative" | "moderate" | "aggressive"

    Returns:
        dict with keys: analysis_html (str), kg_html (str), cached (bool),
        symbol (str), horizon (str), level (str), generated_on (str)

    Raises:
        ValueError:   invalid horizon/risk.
        FileNotFoundError: if data file can't be created.
        RuntimeError: if fetch_phase1 or Gemini fails.
    """
    symbol  = symbol.upper().strip()
    horizon = horizon.lower()
    risk    = risk.lower()

    if horizon not in ("short", "medium", "long"):
        raise ValueError(f"Invalid horizon: {horizon}")
    level: UserLevel = RISK_TO_LEVEL.get(risk, "medium")

    today   = str(date.today())
    data_p  = _data_path(symbol)
    ana_p, kg_p = _out_paths(symbol, horizon, level, today)

    # ── Serve from cache if both HTML files exist and were made today ──────────
    if _is_fresh(ana_p, 23) and _is_fresh(kg_p, 23):
        logger.info("simple_analysis: cache HIT for %s/%s/%s", symbol, horizon, level)
        return {
            "symbol": symbol, "horizon": horizon, "level": level,
            "generated_on": today, "cached": True,
            "analysis_html": ana_p.read_text(encoding="utf-8"),
            "kg_html":       kg_p.read_text(encoding="utf-8"),
        }

    # ── Step 1: ensure data file is fresh ─────────────────────────────────────
    if not _is_fresh(data_p, DATA_FRESHNESS_H):
        await _run_fetch_phase1(symbol, horizon)

    if not data_p.exists():
        raise FileNotFoundError(
            f"Data file not found after fetch: {data_p}. "
            f"Run: python fetch_phase1_data.py {symbol} {horizon}"
        )

    # ── Step 2: build knowledge graph ─────────────────────────────────────────
    kg_link = f"/stock/{symbol}/knowledge"
    try:
        kg_html = await _build_kg_html(symbol)
        kg_p.write_text(kg_html, encoding="utf-8")
        graph_dir = _GRAPHIFY_DIR / symbol.upper()
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / f"{today}.html").write_text(kg_html, encoding="utf-8")
        logger.info("simple_analysis: KG HTML saved → %s", kg_p)
    except Exception as kg_exc:
        logger.warning("simple_analysis: KG build failed (non-fatal) — %s", kg_exc)
        kg_html = "<p style='color:#94a3b8'>Knowledge graph unavailable.</p>"

    # ── Step 3: Gemini analysis ───────────────────────────────────────────────
    report_md = await _run_gemini(symbol, horizon, level, kg_link)
    cleaned_md = _clean_markdown(report_md)
    analysis_html = _analysis_html_template(cleaned_md, symbol, horizon, level)
    ana_p.write_text(analysis_html, encoding="utf-8")
    logger.info("simple_analysis: analysis HTML saved → %s", ana_p)

    return {
        "symbol": symbol, "horizon": horizon, "level": level,
        "generated_on": today, "cached": False,
        "analysis_html": analysis_html,
        "kg_html":       kg_html,
    }
