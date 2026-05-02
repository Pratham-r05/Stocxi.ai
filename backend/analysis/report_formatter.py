"""
report_formatter.py — Save Gemini analysis reports to disk.

Writes the Markdown report to analysis-out/{SYMBOL}/{horizon}_{level}_{date}.md
and optionally an HTML-wrapped version for browser viewing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[2]
_OUT_DIR      = _PROJECT_ROOT / "analysis-out"

_HTML_CSS = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 900px; margin: 40px auto; padding: 0 24px;
         background: #0f1117; color: #e0e0e0; line-height: 1.7; }
  h1 { color: #fff; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }
  h2 { color: #93c5fd; margin-top: 2em; }
  h3 { color: #bfdbfe; }
  h4 { color: #dbeafe; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  th { background: #1e293b; color: #93c5fd; padding: 8px 12px; text-align: left; }
  td { padding: 7px 12px; border-bottom: 1px solid #1e293b; }
  tr:hover td { background: #1e293b55; }
  code { background: #1e293b; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
  pre  { background: #1e293b; padding: 16px; border-radius: 8px; overflow-x: auto; }
  blockquote { border-left: 3px solid #2563eb; padding-left: 16px; color: #94a3b8; }
  a { color: #60a5fa; }
  strong { color: #fff; }
</style>
"""


def _md_to_html(md: str, title: str) -> str:
    """
    Wrap raw Markdown in a minimal HTML shell for browser viewing.
    Uses marked.js CDN for rendering — no Python markdown dependency needed.
    """
    escaped = md.replace("`", "&#96;").replace("\\", "\\\\").replace("${", "\\${")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  {_HTML_CSS}
</head>
<body>
  <div id="content"></div>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script>
    const raw = `{escaped}`;
    document.getElementById('content').innerHTML = marked.parse(raw);
  </script>
</body>
</html>"""


def save_report(
    symbol: str,
    horizon: str,
    user_level: str,
    report_md: str,
    kg_link: str = "",
    open_browser: bool = False,
) -> dict[str, Path]:
    """
    Save Gemini analysis report to disk.

    Args:
        symbol:       NSE stock symbol (e.g. "RELIANCE")
        horizon:      "short" | "medium" | "long"
        user_level:   "beginner" | "medium" | "pro"
        report_md:    Markdown string from gemini_analysis.run_analysis()
        kg_link:      Path to the knowledge graph HTML (optional, for display)
        open_browser: If True, open the HTML file in the default browser.

    Returns:
        {"md": Path, "html": Path} — paths to saved files.
    """
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    out_dir  = _OUT_DIR / symbol.upper()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem     = f"{horizon}_{user_level}_{date_str}"
    md_path  = out_dir / f"{stem}.md"
    html_path = out_dir / f"{stem}.html"

    # Inject KG link if placeholder still present and kg_link provided
    if kg_link and "[KG_LINK_PLACEHOLDER]" in report_md:
        report_md = report_md.replace("[KG_LINK_PLACEHOLDER]", kg_link)

    md_path.write_text(report_md, encoding="utf-8")
    logger.info("[report_formatter] Saved Markdown → %s", md_path)

    title    = f"{symbol.upper()} — {horizon.title()}-Term Analysis ({user_level.title()})"
    html_str = _md_to_html(report_md, title)
    html_path.write_text(html_str, encoding="utf-8")
    logger.info("[report_formatter] Saved HTML     → %s", html_path)

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{html_path.resolve()}")

    return {"md": md_path, "html": html_path}
