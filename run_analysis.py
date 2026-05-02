"""
run_analysis.py — CLI entrypoint for Stocxi end-to-end analysis.

Usage:
    conda run -n stocxi python run_analysis.py RELIANCE --horizon short --level beginner
    conda run -n stocxi python run_analysis.py NYKAA   --horizon medium --level pro
    conda run -n stocxi python run_analysis.py INFY    --horizon long   --level medium

Steps performed:
    1. Verify data/{SYMBOL}_data.md exists (run fetch_phase1_data.py if not)
    2. Build knowledge graph HTML (graphify-out/stocks/{SYMBOL}/)
    3. Call Gemini with horizon instructions + user level
    4. Save report to analysis-out/{SYMBOL}/{horizon}_{level}_{date}.md + .html
    5. Open report in browser
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Project root on path ──────────────────────────────────────────────────────

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))


def _banner(text: str) -> None:
    width = 60
    print("\n" + "─" * width)
    print(f"  {text}")
    print("─" * width)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Stocxi — AI stock analysis via knowledge graph + Gemini",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_analysis.py RELIANCE --horizon short  --level beginner
  python run_analysis.py NYKAA   --horizon medium --level medium
  python run_analysis.py INFY    --horizon long   --level pro
        """,
    )
    ap.add_argument("symbol",
                    help="NSE stock symbol (e.g. RELIANCE, INFY, NYKAA)")
    ap.add_argument("--horizon", "-H",
                    choices=["short", "medium", "long"],
                    default="medium",
                    help="Investment horizon: short (1-3m) | medium (3-12m) | long (1-5y)  [default: medium]")
    ap.add_argument("--level", "-L",
                    choices=["beginner", "medium", "pro"],
                    default="beginner",
                    help="Report depth: beginner | medium | pro  [default: beginner]")
    ap.add_argument("--no-browser",
                    action="store_true",
                    help="Do not open the report in the browser after generation")
    ap.add_argument("--skip-kg",
                    action="store_true",
                    help="Skip knowledge graph HTML generation (use if already built)")
    args = ap.parse_args()

    symbol     = args.symbol.upper()
    horizon    = args.horizon
    user_level = args.level

    horizon_label = {"short": "Short-Term (1–3 months)",
                     "medium": "Medium-Term (3–12 months)",
                     "long": "Long-Term (1–5 years)"}[horizon]

    print(f"\n  Stocxi Analysis Pipeline")
    print(f"  Symbol   : {symbol}")
    print(f"  Horizon  : {horizon_label}")
    print(f"  Report   : {user_level.title()} level")

    # ── Step 1: Verify data file ──────────────────────────────────────────────

    _banner("Step 1/4  Checking data file")
    data_path = _ROOT / "data" / f"{symbol}_data.md"
    if not data_path.exists():
        print(f"\n  [ERROR] Data file not found: {data_path}")
        print(f"  Run first:  conda run -n stocxi python fetch_phase1_data.py {symbol}\n")
        sys.exit(1)
    print(f"  Found: {data_path.name}")

    # ── Step 2: Build knowledge graph ─────────────────────────────────────────

    _banner("Step 2/4  Building knowledge graph")

    kg_link = ""
    if args.skip_kg:
        print("  Skipped (--skip-kg flag set)")
        # Try to find existing KG file
        kg_dir = _ROOT / "graphify-out" / "stocks" / symbol
        if kg_dir.exists():
            existing = sorted(kg_dir.glob("*.html"), reverse=True)
            if existing:
                kg_link = f"file://{existing[0].resolve()}"
                print(f"  Using existing: {existing[0].name}")
    else:
        from build_knowledge_graph import parse_md, build_graph_data, render_html

        meta, nodes = parse_md(data_path)
        graph_data  = build_graph_data(symbol, meta, nodes)
        date_str    = meta.get("captured_at", "unknown")

        out_dir  = _ROOT / "graphify-out" / "stocks" / symbol
        out_dir.mkdir(parents=True, exist_ok=True)
        kg_path  = out_dir / f"{date_str}.html"
        kg_path.write_text(render_html(symbol, meta, graph_data), encoding="utf-8")
        kg_link  = f"file://{kg_path.resolve()}"

        n_nodes = len(graph_data["nodes"])
        n_links = len(graph_data["links"])
        print(f"  Built: {n_nodes} nodes, {n_links} links → {kg_path.name}")

    # ── Step 3: Gemini analysis ───────────────────────────────────────────────

    _banner("Step 3/4  Running Gemini analysis")
    t0 = time.time()

    from backend.analysis.gemini_analysis import run_analysis

    try:
        report_md = run_analysis(
            symbol=symbol,
            horizon=horizon,
            user_level=user_level,
            kg_link=kg_link,
        )
    except FileNotFoundError as exc:
        print(f"\n  [ERROR] {exc}\n")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  [ERROR] Gemini API call failed: {exc}\n")
        logger.exception("Gemini call failed")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s — {len(report_md):,} chars")

    # ── Step 4: Save report ───────────────────────────────────────────────────

    _banner("Step 4/4  Saving report")

    from backend.analysis.report_formatter import save_report

    paths = save_report(
        symbol=symbol,
        horizon=horizon,
        user_level=user_level,
        report_md=report_md,
        kg_link=kg_link,
        open_browser=not args.no_browser,
    )

    print(f"  Markdown : {paths['md']}")
    print(f"  HTML     : {paths['html']}")
    if kg_link:
        print(f"  KG graph : {kg_link}")

    print(f"\n  Analysis complete.\n")


if __name__ == "__main__":
    main()
