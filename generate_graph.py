"""
generate_graph.py — Quick standalone NYKAA graph generator.

Runs: data agents → build_graph → render_3d_html → open in browser.
Usage: python generate_graph.py [SYMBOL]
"""
import sys
import asyncio
import subprocess
from datetime import date, datetime
from pathlib import Path

# ── make sure backend/ is on the path ─────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))

import logging
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "NYKAA"
print(f"\n=== Stocxi Knowledge Graph — {SYMBOL} ===\n")


async def main():
    from schemas.messages import FetchRequest, UserProfile, Horizon, Risk
    from schemas.node import Node, NodeCategory, NodeSignal
    import agents.agent_technical as agent_technical
    import agents.agent_fundamental as agent_fundamental
    import agents.agent_news as agent_news
    from graph.knowledge_graph import build_graph, render_3d_html
    import uuid

    today = date.today()
    profile = UserProfile(horizon=Horizon.long, risk=Risk.moderate, sector="")
    req = FetchRequest(
        stock=SYMBOL,
        profile=profile,
        as_of_date=today,
        request_id=str(uuid.uuid4()),
    )

    all_nodes: list[Node] = []
    admin_view: dict = {"agreements": [], "contradictions": [], "verdicts": []}

    # ── Technical agent ────────────────────────────────────────────────────────
    print(f"[1/3] Running technical agent for {SYMBOL}...")
    t0 = datetime.now()
    try:
        tech_nodes = await agent_technical.run(req)
        all_nodes.extend(tech_nodes)
        print(f"      OK — {len(tech_nodes)} nodes ({(datetime.now()-t0).seconds}s)")

        # Build intra-technical agreements: same bullish / same bearish nodes pair up
        bull = [n.node_id for n in tech_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bullish","positive")]
        bear = [n.node_id for n in tech_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bearish","negative")]
        for i in range(len(bull)):
            for j in range(i+1, min(i+4, len(bull))):
                admin_view["agreements"].append({"node_a": bull[i], "node_b": bull[j]})
        for i in range(len(bear)):
            for j in range(i+1, min(i+4, len(bear))):
                admin_view["agreements"].append({"node_a": bear[i], "node_b": bear[j]})
        # Bull-bear cross-contradictions (first 5 of each)
        for b in bull[:5]:
            for r in bear[:5]:
                admin_view["contradictions"].append({"node_a": b, "node_b": r})

        # Verdict node support: nodes with weight >= 1.2 support a technical verdict
        hi_wt = [n.node_id for n in tech_nodes if n.weight >= 1.2]
        bull_count = len([n for n in tech_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bullish","positive")])
        bear_count = len([n for n in tech_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bearish","negative")])
        tech_signal = "bullish" if bull_count > bear_count else ("bearish" if bear_count > bull_count else "neutral")
        admin_view["verdicts"].append({
            "category": "technical",
            "signal": tech_signal,
            "supporting_node_ids": hi_wt[:8],
        })

    except Exception as e:
        print(f"      FAIL — {e}")

    # ── Fundamental agent ──────────────────────────────────────────────────────
    print(f"[2/3] Running fundamental agent for {SYMBOL}...")
    t0 = datetime.now()
    try:
        fund_nodes = await agent_fundamental.run(req)
        all_nodes.extend(fund_nodes)
        print(f"      OK — {len(fund_nodes)} nodes ({(datetime.now()-t0).seconds}s)")

        # Cross-category agreement: bullish tech ↔ bullish fundamental
        fund_bull = [n.node_id for n in fund_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bullish","positive")]
        fund_bear = [n.node_id for n in fund_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bearish","negative")]
        tech_bull_ids = admin_view["agreements"][:5] if admin_view["agreements"] else []

        for fb in fund_bull[:4]:
            for tb in bull[:4]:
                admin_view["agreements"].append({"node_a": fb, "node_b": tb})
        for fr in fund_bear[:4]:
            for tb in bull[:3]:
                admin_view["contradictions"].append({"node_a": fr, "node_b": tb})

        fund_signal = "bullish" if len(fund_bull) > len(fund_bear) else ("bearish" if len(fund_bear) > len(fund_bull) else "neutral")
        admin_view["verdicts"].append({
            "category": "fundamental",
            "signal": fund_signal,
            "supporting_node_ids": (fund_bull + fund_bear)[:6],
        })

    except Exception as e:
        print(f"      FAIL — {e}")

    # ── News agent ─────────────────────────────────────────────────────────────
    print(f"[3/3] Running news agent for {SYMBOL}...")
    t0 = datetime.now()
    try:
        news_nodes = await agent_news.run(req)
        all_nodes.extend(news_nodes)
        print(f"      OK — {len(news_nodes)} nodes ({(datetime.now()-t0).seconds}s)")

        news_bull = [n.node_id for n in news_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bullish","positive")]
        news_bear = [n.node_id for n in news_nodes if str(getattr(n.signal, 'value', n.signal)) in ("bearish","negative")]
        news_signal = "bullish" if len(news_bull) > len(news_bear) else ("bearish" if len(news_bear) > len(news_bull) else "neutral")
        admin_view["verdicts"].append({
            "category": "news",
            "signal": news_signal,
            "supporting_node_ids": news_bull[:4] + news_bear[:2],
        })

    except Exception as e:
        print(f"      FAIL — {e}")

    if not all_nodes:
        print("\nERROR: No nodes collected. Check agent errors above.")
        return

    print(f"\n[Build] {len(all_nodes)} total nodes → building graph...")
    graph_data = build_graph(all_nodes, admin_view)
    print(f"        {graph_data['meta']['node_count']} nodes, {graph_data['meta']['edge_count']} edges")

    # ── Save ───────────────────────────────────────────────────────────────────
    out_dir = ROOT / "graphify-out" / "stocks" / SYMBOL
    out_path = out_dir / f"{today}.html"
    render_3d_html(graph_data, title=f"Stocxi — {SYMBOL} Knowledge Graph | {today}", output_path=out_path)
    print(f"\n[Saved] {out_path}")

    # Open in browser
    subprocess.run(["open", str(out_path)])
    print(f"[Open]  Launched in browser.\n")


asyncio.run(main())
