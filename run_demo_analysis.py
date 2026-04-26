"""
run_demo_analysis.py — End-to-end analysis demo runner with full timing + status report.

Usage:
    python run_demo_analysis.py [SYMBOL] [--horizon short|long] [--risk conservative|moderate|aggressive]

Examples:
    python run_demo_analysis.py RELIANCE
    python run_demo_analysis.py HDFCBANK --horizon long --risk aggressive
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
import webbrowser
from datetime import date
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent
_BACKEND   = _REPO_ROOT / "backend"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

# ── Imports ───────────────────────────────────────────────────────────────────
from schemas.messages import FetchRequest, UserProfile        # type: ignore[import]
from schemas.node import Node                                 # type: ignore[import]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(seconds: float) -> str:
    return f"{seconds:.1f}s"

def _box(title: str, width: int = 62) -> str:
    return f"\n{'═'*width}\n  {title}\n{'═'*width}"

def _row(label: str, value: str, width: int = 22) -> str:
    return f"  {label:<{width}} {value}"


# ── Per-agent runner with timing ──────────────────────────────────────────────

async def _run_agent_timed(
    name: str,
    coro,
) -> tuple[str, list[Node] | None, float, str]:
    """Run one agent coroutine, measure wall-clock time, catch errors.

    Returns: (name, nodes_or_None, elapsed_seconds, status_str)
    """
    t0 = time.monotonic()
    try:
        nodes = await asyncio.wait_for(coro, timeout=30)
        elapsed = time.monotonic() - t0
        count = len(nodes) if nodes else 0
        return name, nodes, elapsed, f"OK — {count} nodes"
    except asyncio.TimeoutError:
        return name, None, time.monotonic() - t0, "TIMEOUT (>30s)"
    except Exception as exc:
        return name, None, time.monotonic() - t0, f"ERROR — {exc}"


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    symbol  = args.symbol.upper().removesuffix(".NS")
    profile = UserProfile(
        horizon=args.horizon,
        risk=args.risk,
        sector=args.sector or "",
    )
    request = FetchRequest(
        stock=symbol,
        profile=profile,
        as_of_date=date.today(),
        request_id=str(uuid.uuid4()),
    )

    print(_box(f"STOCXI ANALYSIS — {symbol}"))
    print(_row("Horizon:", args.horizon))
    print(_row("Risk:", args.risk))
    print(_row("Date:", str(date.today())))
    print(_row("Request ID:", request.request_id[:16] + "..."))

    # ── Stage 1: Data agents in parallel ─────────────────────────────────────
    print(_box("STAGE 1 — Data Collection (parallel)"))

    from agents import (                                      # type: ignore[import]
        agent_technical, agent_fundamental,
        agent_news, agent_announcement, agent_context,
    )
    from util.sanitizer import build_anon_map                # type: ignore[import]

    t_data_start = time.monotonic()
    results = await asyncio.gather(
        _run_agent_timed("Technical",    agent_technical.run(request)),
        _run_agent_timed("Fundamental",  agent_fundamental.run(request)),
        _run_agent_timed("News",         agent_news.run(request)),
        _run_agent_timed("Announcement", agent_announcement.run(request)),
        _run_agent_timed("Context",      agent_context.run(request)),
    )
    t_data_total = time.monotonic() - t_data_start

    all_nodes: list[Node] = []
    for name, nodes, elapsed, status in results:
        icon = "✓" if nodes else "✗"
        print(_row(f"  {icon} {name}:", f"{status}  [{_fmt(elapsed)}]"))
        if nodes:
            all_nodes.extend(nodes)

    print(_row("\n  Total nodes collected:", str(len(all_nodes))))
    print(_row("  Data collection wall-time:", _fmt(t_data_total)))

    # Node breakdown by category
    cat_counts: dict[str, int] = {}
    for n in all_nodes:
        cat = str(n.category.value if hasattr(n.category, "value") else n.category)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    print("\n  Node breakdown:")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"    {cat:<16} {cnt} nodes")

    if len(all_nodes) == 0:
        print("\n[ABORT] Zero nodes collected — cannot proceed with analysis.")
        return

    # ── Stage 2: Anonymization ────────────────────────────────────────────────
    print(_box("STAGE 2 — Anonymization"))
    t2 = time.monotonic()
    from util.sanitizer import build_anon_map, scrub_text    # type: ignore[import]
    from agents.orchestrator import _sanitize_nodes          # type: ignore[import]
    anon_map = build_anon_map(stock=symbol, sector=profile.sector)
    all_nodes = _sanitize_nodes(all_nodes, anon_map)
    print(_row("  Status:", f"OK — identity scrubbed [{_fmt(time.monotonic()-t2)}]"))
    print(_row("  Tokens replaced:", str(len(anon_map.all_pairs()))))

    # ── Stage 3: Insufficient-data gate ──────────────────────────────────────
    print(_box("STAGE 3 — Sufficiency Gate"))
    from agents.orchestrator import _check_sufficient, InsufficientDataError  # type: ignore[import]
    try:
        _check_sufficient(all_nodes)
        print(_row("  Status:", "PASSED — sufficient nodes"))
    except InsufficientDataError as e:
        print(_row("  Status:", f"FAILED — {e}"))
        print("\n[ABORT] Insufficient data. Cannot produce a reliable analysis.")
        print("  This stock may be too thinly traded or data providers lack coverage.")
        return

    # ── Stage 4: LLM Analysis ─────────────────────────────────────────────────
    print(_box("STAGE 4 — LLM Analysis (Gemini 3.1 Pro)"))
    from agents import agent_analysis as _aa                 # type: ignore[import]
    t4 = time.monotonic()
    try:
        draft, full_prompt, full_raw = await _aa.run(all_nodes, request)
        t4_elapsed = time.monotonic() - t4
        print(_row("  Status:", f"OK — draft produced [{_fmt(t4_elapsed)}]"))
        print(_row("  Prompt length:", f"{len(full_prompt):,} chars"))
        print(_row("  Response length:", f"{len(full_raw):,} chars"))
        all_claims = draft.what_data_suggests + draft.signals_in_favor + draft.signals_against
        print(_row("  Claims in draft:", str(len(all_claims))))
        print(_row("  Verdicts:", str(len(draft.verdicts))))
    except Exception as exc:
        print(_row("  Status:", f"FAILED — {exc}"))
        raise

    # ── Stage 5: Verifier ────────────────────────────────────────────────────
    print(_box("STAGE 5 — Verifier (citation check)"))
    from agents import agent_verifier as _av                 # type: ignore[import]
    t5 = time.monotonic()
    verified = _av.run(draft, all_nodes)
    t5_elapsed = time.monotonic() - t5
    print(_row("  Status:", f"OK [{_fmt(t5_elapsed)}]"))
    kept = (len(verified.draft.what_data_suggests)
            + len(verified.draft.signals_in_favor)
            + len(verified.draft.signals_against))
    print(_row("  Claims kept:", str(kept)))
    print(_row("  Claims stripped:", str(verified.stripped_claims)))
    print(_row("  Low fidelity:", str(verified.low_fidelity)))

    # ── Stage 6: Formatter ────────────────────────────────────────────────────
    print(_box("STAGE 6 — Formatter (de-anonymize + structure)"))
    from agents import formatter as _fmt_mod                 # type: ignore[import]
    t6 = time.monotonic()
    analysis_id = str(uuid.uuid4())
    result, admin_view = _fmt_mod.format_result(
        verified=verified, anon_map=anon_map, request=request,
        nodes=all_nodes, failed_fetches=None,
        analysis_id=analysis_id,
        latency_ms=int((time.monotonic() - t_data_start) * 1000),
        cache_hit=False,
    )
    t6_elapsed = time.monotonic() - t6
    print(_row("  Status:", f"OK [{_fmt(t6_elapsed)}]"))

    # ── Stage 7: Calibration ─────────────────────────────────────────────────
    print(_box("STAGE 7 — Confidence Calibration"))
    from calibration.refit_weights import apply_calibration  # type: ignore[import]
    import yaml as _yaml
    _calib_map = {}
    try:
        _calib_map = _yaml.safe_load(
            (Path("..") / "config" / "calibration.yaml").read_text()
        )
    except Exception:
        pass
    raw_conf   = verified.draft.raw_confidence
    calib_conf = apply_calibration(raw_conf, _calib_map)
    result     = result.model_copy(update={"calibrated_confidence": calib_conf})
    print(_row("  Raw confidence:", f"{raw_conf:.2%}"))
    print(_row("  Calibrated conf:", f"{calib_conf:.2%}"))
    print(_row("  Method:", _calib_map.get("method", "identity")))

    # ── Stage 8: Knowledge Graph ──────────────────────────────────────────────
    print(_box("STAGE 8 — 3D Knowledge Graph"))
    from graph.knowledge_graph import build_graph, render_3d_html  # type: ignore[import]
    t8 = time.monotonic()
    G = build_graph(all_nodes, admin_view)
    graph_dir  = _REPO_ROOT / "graphify-out" / "stocks" / symbol
    graph_path = graph_dir / f"{date.today()}.html"
    render_3d_html(G, title=f"Stocxi — {symbol} | {date.today()}", output_path=graph_path)
    t8_elapsed = time.monotonic() - t8
    print(_row("  Nodes in graph:", str(G.number_of_nodes())))
    print(_row("  Edges in graph:", str(G.number_of_edges())))
    print(_row("  Build time:", _fmt(t8_elapsed)))
    print(_row("  Saved to:", str(graph_path)))

    # ── Stage 9: PDF Report ───────────────────────────────────────────────────
    print(_box("STAGE 9 — PDF Report"))
    from agents.agent_report import build_report             # type: ignore[import]
    t9 = time.monotonic()
    pdf_dir  = _REPO_ROOT / "graphify-out" / "stocks" / symbol
    pdf_path = pdf_dir / f"{date.today()}.pdf"
    try:
        pdf_bytes = build_report(result)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        t9_elapsed = time.monotonic() - t9
        print(_row("  Status:", f"OK — {len(pdf_bytes):,} bytes [{_fmt(t9_elapsed)}]"))
        print(_row("  Saved to:", str(pdf_path)))
    except Exception as exc:
        print(_row("  Status:", f"ERROR — {exc}"))
        pdf_path = None

    # ── Stage 10: Audit log ───────────────────────────────────────────────────
    print(_box("STAGE 10 — Audit Log"))
    from audit.audit_log import log_analysis                 # type: ignore[import]
    try:
        log_analysis(
            analysis_id=analysis_id, stock=symbol,
            profile_bucket=profile.bucket,
            as_of_date=str(date.today()),
            node_ids=[n.node_id for n in all_nodes],
            prompt_version=draft.prompt_version,
            weight_version=draft.weight_version,
            model_id=draft.model_id,
            input_nodes_json=json.dumps([n.node_id for n in all_nodes]),
            full_prompt=full_prompt, full_raw_output=full_raw,
            final_output=result.model_dump(mode="json"),
            admin_view=admin_view,
        )
        print(_row("  Status:", "OK — audit row written"))
    except Exception as exc:
        print(_row("  Status:", f"ERROR — {exc}"))

    # ── Final Summary ─────────────────────────────────────────────────────────
    total_time = time.monotonic() - t_data_start
    print(_box(f"ANALYSIS COMPLETE — {symbol}"))
    print(_row("  Overall signal:", result.overall_signal.upper()))
    print(_row("  Calibrated conf:", f"{calib_conf:.2%}"))
    print(_row("  Total wall-time:", _fmt(total_time)))
    print(_row("  Analysis ID:", analysis_id[:16] + "..."))
    print(f"\nSUMMARY:\n  {result.summary}\n")

    if result.claims:
        print(f"TOP CLAIMS:")
        for i, claim in enumerate(result.claims[:6], 1):
            print(f"  {i}. [{claim.signal}] {claim.text}")

    print(f"\n{'─'*62}")
    print(f"  PDF  → {pdf_path}")
    print(f"  HTML → {graph_path}")
    print(f"{'─'*62}\n")

    if not args.no_browser and graph_path and graph_path.exists():
        webbrowser.open(f"file://{graph_path}")
        print("Opened knowledge graph in browser.")
    if not args.no_browser and pdf_path and pdf_path.exists():
        import subprocess
        subprocess.Popen(["open", str(pdf_path)])
        print("Opened PDF.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stocxi end-to-end demo analysis")
    p.add_argument("symbol",    nargs="?", default="RELIANCE")
    p.add_argument("--horizon", default="short", choices=["short", "long"])
    p.add_argument("--risk",    default="moderate", choices=["conservative", "moderate", "aggressive"])
    p.add_argument("--sector",  default="")
    p.add_argument("--no-browser", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
