"""
run_e2e_analysis.py — Full end-to-end analysis runner with live diagnostics.

Usage: python run_e2e_analysis.py [SYMBOL]   (default: RELIANCE)

Runs every pipeline stage, prints live status, writes report to reports/<SYMBOL>_report.md
and generates a 3D knowledge graph at graphify-out/stocks/<SYMBOL>/<date>.html
"""

import asyncio
import datetime
import json
import sys
import time
import uuid
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "RELIANCE"
HORIZON = sys.argv[2].lower() if len(sys.argv) > 2 else "long"
RISK    = "moderate"

# Sector map for common stocks — used for peer comparison and anonymization
_SECTOR_MAP = {
    "POWERGRID": "utilities", "NTPC": "utilities", "TATAPOWER": "utilities",
    "RELIANCE": "energy", "ONGC": "energy", "IOC": "energy",
    "TCS": "technology", "INFY": "technology", "WIPRO": "technology", "HCLTECH": "technology",
    "HDFCBANK": "banking", "ICICIBANK": "banking", "AXISBANK": "banking", "KOTAKBANK": "banking",
    "ASIANPAINT": "paints", "BERGERPAINTS": "paints",
    "MARUTI": "automobiles", "TATAMOTORS": "automobiles", "BAJAJ-AUTO": "automobiles",
    "SUNPHARMA": "pharma", "DRREDDY": "pharma", "CIPLA": "pharma",
    "ITC": "fmcg", "HINDUNILVR": "fmcg", "NESTLEIND": "fmcg",
    "LT": "infrastructure", "ADANIPORTS": "infrastructure",
    "SBIN": "banking", "BAJFINANCE": "nbfc", "BAJAJFINSV": "nbfc",
}
SECTOR = _SECTOR_MAP.get(SYMBOL, "diversified")

print(f"\n{'='*60}")
print(f"  STOCXI — Full E2E Analysis")
print(f"  Stock: {SYMBOL} | Horizon: {HORIZON} | Risk: {RISK}")
print(f"  Date:  {datetime.date.today()}")
print(f"{'='*60}\n")

# ── 1. Config ──────────────────────────────────────────────────────────────────
print("[1/8] Loading config + credentials...")
t_start = time.monotonic()

from config import settings
import os
print(f"      model          : {settings.google_model}")
print(f"      creds path     : {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS','NOT SET')}")
print(f"      redis          : {settings.redis_url[:40]}...")

# Verify Vertex AI token refreshes
import google.auth, google.auth.transport.requests
creds, gcp_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
creds.refresh(google.auth.transport.requests.Request())
print(f"      GCP project    : {gcp_project}")
print(f"      token prefix   : {creds.token[:20]}...")
print("  [OK] Config + Vertex AI credentials\n")

# ── 2. Build FetchRequest ──────────────────────────────────────────────────────
print("[2/8] Building FetchRequest...")
from backend.schemas.messages import FetchFailure, FetchRequest, UserProfile

profile = UserProfile(horizon=HORIZON, risk=RISK, sector=SECTOR)
request = FetchRequest(
    stock=SYMBOL,
    profile=profile,
    as_of_date=datetime.date.today(),
    request_id=str(uuid.uuid4()),
)
print(f"      request_id : {request.request_id}")
print(f"      bucket     : {profile.bucket}")
print("  [OK] FetchRequest built\n")

# ── 3. Data agents — parallel fan-out ─────────────────────────────────────────
print("[3/8] Running data agents (parallel fan-out, 180s timeout each)...")
import importlib

agent_mods = [
    ("technical",    "backend.agents.agent_technical"),
    ("fundamental",  "backend.agents.agent_fundamental"),
    ("news",         "backend.agents.agent_news"),
    ("announcement", "backend.agents.agent_announcement"),
    ("context",      "backend.agents.agent_context"),
]

async def run_agent_safe(name: str, mod_path: str, req: FetchRequest):
    try:
        mod    = importlib.import_module(mod_path)
        t0     = time.monotonic()
        result = await asyncio.wait_for(mod.run(req), timeout=180.0)
        ms     = int((time.monotonic() - t0) * 1000)
        if isinstance(result, FetchFailure):
            print(f"      [{name:12s}]   0 nodes  FETCH_FAILURE: {result.reason} — {result.error}  [WARN]")
            return name, []
        print(f"      [{name:12s}] {len(result):>3} nodes  {ms:>5}ms  [OK]")
        return name, result
    except asyncio.TimeoutError:
        print(f"      [{name:12s}]   0 nodes  TIMEOUT  [WARN]")
        return name, []
    except Exception as e:
        print(f"      [{name:12s}]   0 nodes  ERROR: {e}  [WARN]")
        return name, []

async def run_data_agents():
    tasks = [run_agent_safe(n, m, request) for n, m in agent_mods]
    return await asyncio.gather(*tasks)

agent_results = asyncio.run(run_data_agents())

all_nodes     = []
failed_agents = []
node_summary  = {}
for name, nodes in agent_results:
    if nodes:
        all_nodes.extend(nodes)
        node_summary[name] = len(nodes)
    else:
        failed_agents.append(name)
        node_summary[name] = 0

print(f"\n      Total nodes: {len(all_nodes)}")
print(f"      Failed agents: {failed_agents or 'none'}")
print("  [OK] Data collection complete\n")

# ── 4. Anonymization ──────────────────────────────────────────────────────────
print("[4/8] Anonymizing nodes (AnonMap + identity scrub)...")
from backend.util.sanitizer import AnonMap, build_anon_map, scrub_text
from backend.audit.audit_log import compute_data_hash

anon_map  = build_anon_map(stock=SYMBOL, sector=SECTOR)
print(f"      anon tokens: {len(anon_map.all_pairs())} replacements registered")

# Scrub sanitized=False nodes
scrubbed = 0
sanitized_nodes = []
for n in all_nodes:
    if not n.sanitized:
        n = n.model_copy(update={
            "value": scrub_text(n.value, anon_map),
            "sanitized": True,
        })
        scrubbed += 1
    sanitized_nodes.append(n)
all_nodes = sanitized_nodes
print(f"      scrubbed {scrubbed} nodes (news/announcement → sanitized=True)")
print("  [OK] Anonymization done\n")

# ── 5. INSUFFICIENT_DATA check ────────────────────────────────────────────────
print("[5/8] Checking data sufficiency gate...")
import yaml
versions = yaml.safe_load((ROOT / "config" / "versions.yaml").read_text())
N_MIN = versions["min_nodes"]
sufficient = True
for cat, threshold in [("technical", N_MIN["technical"]), ("fundamental", N_MIN["fundamental"]), ("announcement", N_MIN["announcement"])]:
    count = node_summary.get(cat, 0)
    ok    = count >= threshold
    if not ok:
        sufficient = False
    status = "OK" if ok else "WARN (below threshold)"
    print(f"      {cat:12s}: {count:>3} / {threshold} required  [{status}]")

if not sufficient:
    print("\n  [WARN] Some categories below N_MIN — pipeline continues (orchestrator would raise InsufficientDataError in prod)")
else:
    print("  [OK] Data sufficiency gate passed\n")

# ── 6. LLM Analysis ───────────────────────────────────────────────────────────
print("[6/8] Running LLM analysis (Gemini 2.5 Pro via Vertex AI)...")
print("      (this takes 60–120s for full prompt — please wait)")

async def run_llm():
    from backend.agents import agent_analysis
    return await agent_analysis.run(all_nodes, request)

t_llm = time.monotonic()
draft, full_prompt, full_raw_output = asyncio.run(run_llm())
llm_ms = int((time.monotonic() - t_llm) * 1000)

print(f"      LLM latency      : {llm_ms/1000:.1f}s")
print(f"      overall_signal   : {draft.overall_signal}")
print(f"      raw_confidence   : {draft.raw_confidence:.2f}")
print(f"      claims           : {len(draft.what_data_suggests)}")
print(f"      signals_in_favor : {len(draft.signals_in_favor)}")
print(f"      signals_against  : {len(draft.signals_against)}")
print(f"      model_id         : {draft.model_id}")
print(f"      prompt_version   : {draft.prompt_version}")
print("  [OK] LLM analysis complete\n")

# ── 7. Verifier ───────────────────────────────────────────────────────────────
print("[7/8] Running verifier (node_id citation check)...")
from backend.agents import agent_verifier

verified = agent_verifier.run(draft, all_nodes)
print(f"      stripped_claims : {verified.stripped_claims}")
print(f"      low_fidelity    : {verified.low_fidelity}")
print(f"      valid claims    : {len(verified.draft.what_data_suggests)}")
print("  [OK] Verifier done\n")

# ── 8. Formatter → AnalysisResult ─────────────────────────────────────────────
print("[8/8] Formatting result + calibration + audit log...")
from backend.agents import formatter
import yaml as _yaml
from backend.calibration.refit_weights import apply_calibration

analysis_id = str(uuid.uuid4())
latency_ms  = int((time.monotonic() - t_start) * 1000)

result, admin_view = formatter.format_result(
    verified=verified,
    anon_map=anon_map,
    request=request,
    nodes=all_nodes,
    failed_fetches=[f"{a} data unavailable" for a in failed_agents] if failed_agents else None,
    analysis_id=analysis_id,
    latency_ms=latency_ms,
    cache_hit=False,
)

# Apply calibration (load from config/calibration.yaml — identity map until backtest runs)
_calib_path = ROOT / "config" / "calibration.yaml"
calib_map   = _yaml.safe_load(_calib_path.read_text()) if _calib_path.exists() else {}
calibrated_conf = apply_calibration(verified.draft.raw_confidence, calib_map)
result = result.model_copy(update={"calibrated_confidence": calibrated_conf})

print(f"      analysis_id          : {result.analysis_id}")
print(f"      overall_signal       : {result.overall_signal}")
print(f"      calibrated_confidence: {result.calibrated_confidence:.2f}")
print(f"      total latency        : {latency_ms/1000:.1f}s")
print("  [OK] AnalysisResult ready\n")

# ── Knowledge graph (HFBP) ────────────────────────────────────────────────────
print("[BONUS] Building 3D knowledge graph with HFBP edges...")
graph_link = "N/A"
try:
    from backend.graph import StocxiKnowledgeGraph, build_graph, render_3d_html, to_graphxr_data

    # Build graph + run HFBP forward pass
    kg = StocxiKnowledgeGraph(ticker=SYMBOL, horizon=HORIZON)
    kg.build(all_nodes, analysis_id=analysis_id)
    effective_weights = kg.forward_propagate()

    # Serialize for LLM (HFBP-aware format)
    kg_llm_text = kg.serialize_for_llm()

    # Build graph data with effective_weights for sizing
    graph_admin = {
        "agreements": [
            {"node_id_a": ag["node_id_a"], "node_id_b": ag["node_id_b"]}
            for ag in admin_view.get("agreements", [])
        ],
        "contradictions": [
            {"node_id_positive": ct["node_id_positive"], "node_id_negative": ct["node_id_negative"]}
            for ct in admin_view.get("contradictions", [])
        ],
        "verdicts": [
            {
                "category": cat,
                "direction": v["direction"],
                "supporting_node_ids": v.get("supporting_node_ids", []),
            }
            for cat, v in admin_view.get("verdicts", {}).items()
        ],
    }
    graph_data = build_graph(all_nodes, graph_admin, edges=kg._edges, effective_weights=effective_weights, horizon=HORIZON)

    # Render 3D HTML
    graph_dir  = ROOT / "graphify-out" / "stocks" / SYMBOL
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / f"{datetime.date.today()}.html"
    render_3d_html(graph_data, title=f"Stocxi — {SYMBOL}", stock_name=SYMBOL, horizon=HORIZON, output_path=str(graph_path))
    graph_link = f"file://{graph_path.resolve()}"
    print(f"      Graph saved: {graph_path}")
    print(f"      Nodes: {graph_data['meta']['node_count']} | Edges: {graph_data['meta']['edge_count']} | HFBP edges: {len(kg._edges)}")
    print(f"      Top activated node weight: {max(effective_weights.values(), default=0.0):.3f}")
    print(f"      LLM serialization: {len(kg_llm_text)} chars")

    # Export GraphXR-compatible JSON
    graphxr_data = to_graphxr_data(graph_data)
    graphxr_path = graph_dir / f"{datetime.date.today()}_graphxr.json"
    graphxr_path.write_text(json.dumps(graphxr_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"      GraphXR export: {graphxr_path}")
    print("  [OK] Knowledge graph built\n")
except Exception as e:
    import traceback
    print(f"  [WARN] Graph skipped: {e}")
    traceback.print_exc()
    print()

# ── Build 10-section report per 03_long_term_output.md ─────────────────────────
print("Writing report (10-section long-term format) to reports/ ...")

report_dir = ROOT / "reports"
report_dir.mkdir(exist_ok=True)
report_path = report_dir / f"{SYMBOL}_{datetime.date.today()}_analysis.md"

# Helper: group nodes by category
cat_nodes = {}
for n in all_nodes:
    c = n.category.value
    cat_nodes.setdefault(c, []).append(n)

# Helper: find a node by name (case-insensitive substring match)
def find_node(name_fragment, nodes):
    frag = name_fragment.lower()
    for n in nodes:
        if frag in n.name.lower():
            return n
    return None

def find_nodes(name_fragment, nodes):
    frag = name_fragment.lower()
    return [n for n in nodes if frag in n.name.lower()]

def node_val(n, default="N/A"):
    if n is None:
        return default
    v = n.value_raw if hasattr(n, 'value_raw') and n.value_raw else n.value
    if isinstance(v, dict):
        return v
    return str(v) if v is not None else default

def fmt_node_line(n, label=None):
    lbl = label or n.name
    v = n.value if n else "N/A"
    ctx = n.context if n and hasattr(n, 'context') and n.context else ""
    if ctx:
        return f"**{lbl}: {v}** — {ctx}"
    return f"**{lbl}: {v}**"

# ── Section 1: Stock Snapshot ──────────────────────────────────────────────────
fund_nodes = cat_nodes.get("fundamental", [])
tech_nodes = cat_nodes.get("technical", [])
ann_nodes  = cat_nodes.get("announcement", [])
news_nodes = cat_nodes.get("news", [])
ctx_nodes  = cat_nodes.get("context", [])

pe_node = find_node("PE", fund_nodes) or find_node("ConPE", fund_nodes)
mcap_node = find_node("Market_Cap", fund_nodes) or find_node("market_cap", fund_nodes)
sector_node = find_node("Sector", fund_nodes) or find_node("Industry", fund_nodes)
industry_val = ""
sector_val = result.profile.sector or "N/A"
if sector_node:
    raw = node_val(sector_node)
    if isinstance(raw, dict):
        industry_val = raw.get("industry", raw.get("Industry", ""))
        sector_val = raw.get("sector", raw.get("Sector", sector_val))
    else:
        industry_val = str(raw)

exchange_line = "NSE" if result.nse_symbol else "N/A"
mcap_line = "N/A"
if mcap_node:
    raw = node_val(mcap_node)
    if isinstance(raw, dict):
        mcap_line = f"₹{raw.get('full_market_cap', raw.get('free_float_market_cap', 'N/A'))} Cr"
    else:
        try:
            mcap_line = f"₹{float(raw):,.0f} Cr"
        except (ValueError, TypeError):
            mcap_line = str(raw)

price_node = find_node("Price", tech_nodes) or find_node("Close", tech_nodes)
price_line = "N/A"
if price_node:
    try:
        price_line = f"₹{float(price_node.value):,.2f}"
    except (ValueError, TypeError):
        price_line = str(price_node.value)

conf = result.calibrated_confidence or 0.0
conf_label = "High" if conf > 0.7 else "Medium" if conf > 0.5 else "Low"

# ── Section 2: Knowledge Graph Summary ─────────────────────────────────────────
verdicts = admin_view.get("verdicts", {})
agreements = admin_view.get("agreements", [])
contradictions = admin_view.get("contradictions", [])

confluence_lines = []
for ag in agreements[:5]:
    confluence_lines.append(f"- {ag['reason']}")

conflict_lines = []
for ct in contradictions[:5]:
    conflict_lines.append(f"- {ct['resolution']}")

# ── Section 3: Business Quality & Fundamentals ────────────────────────────────
fund_prose_lines = []
for n in fund_nodes:
    ctx = n.context if hasattr(n, 'context') and n.context else ""
    if ctx:
        fund_prose_lines.append(f"**{n.name}: {n.value}** — {ctx}")
    else:
        fund_prose_lines.append(f"**{n.name}: {n.value}**")

# ── Section 5: Financial Trend ────────────────────────────────────────────────
fin_nodes = find_nodes("financial", fund_nodes)
fin_lines = []
for n in fin_nodes:
    ctx = n.context if hasattr(n, 'context') and n.context else ""
    if ctx:
        fin_lines.append(f"{n.name}: {n.value} — {ctx}")
    else:
        fin_lines.append(f"{n.name}: {n.value}")

# ── Section 4: Institutional & Promoter Conviction ───────────────────────────
holding_nodes = find_nodes("holding", fund_nodes) + find_nodes("Promoter", fund_nodes) + find_nodes("FII", fund_nodes) + find_nodes("DII", fund_nodes)
holding_lines = []
for n in holding_nodes:
    ctx = n.context if hasattr(n, 'context') and n.context else ""
    holding_lines.append(f"- **{n.name}: {n.value}**" + (f" — {ctx}" if ctx else ""))

# ── Section 6: Sector Structural Thesis ───────────────────────────────────────
sector_trend_node = find_node("Sector_Trend", ctx_nodes)
market_regime_node = find_node("Market_Regime", ctx_nodes)
sector_prose = ""
if sector_trend_node:
    ctx = sector_trend_node.context if hasattr(sector_trend_node, 'context') and sector_trend_node.context else ""
    sector_prose = f"**Sector Trend: {sector_trend_node.value}**"
    if ctx:
        sector_prose += f" — {ctx}"
if market_regime_node:
    ctx = market_regime_node.context if hasattr(market_regime_node, 'context') and market_regime_node.context else ""
    if sector_prose:
        sector_prose += f"\n\n**Market Regime: {market_regime_node.value}**"
        if ctx:
            sector_prose += f" — {ctx}"

# ── Section 7: Competitive Positioning ────────────────────────────────────────
peer_node = find_node("Peer_Snapshot", ctx_nodes)
peer_prose = ""
if peer_node:
    ctx = peer_node.context if hasattr(peer_node, 'context') and peer_node.context else ""
    peer_prose = f"**Peer Comparison: {peer_node.value}**"
    if ctx:
        peer_prose += f" — {ctx}"

# ── Section 8: Structural Announcements ────────────────────────────────────────
ann_lines = []
for n in ann_nodes:
    ctx = n.context if hasattr(n, 'context') and n.context else ""
    ann_lines.append(f"- **{n.name}:** {n.value}" + (f" — {ctx}" if ctx else ""))

# ── Section 9: Technical Entry Context ────────────────────────────────────────
ema200_node = find_node("EMA_200", tech_nodes) or find_node("SMA_200", tech_nodes)
price_tech = find_node("Price", tech_nodes)
tech_verdict = verdicts.get("technical", {})
tech_dir = tech_verdict.get("direction", "N/A") if isinstance(tech_verdict, dict) else "N/A"
tech_summary = tech_verdict.get("summary", "") if isinstance(tech_verdict, dict) else ""

tech_prose = ""
if ema200_node:
    tech_prose = f"**EMA-200: {ema200_node.value}** — The 200-day exponential moving average is the institutional dividing line between bull and bear phases. "
    if price_tech:
        tech_prose += f"Current price is at {price_tech.value}. "
    try:
        price_f = float(price_tech.value) if price_tech else 0
        ema_f = float(ema200_node.value) if ema200_node else 0
        if price_f > ema_f:
            tech_prose += "Price trading above EMA-200 confirms a structural uptrend — appropriate for long-term accumulation."
        else:
            tech_prose += "Price trading below EMA-200 signals a structural downtrend — long-term investors may want to wait for a base to form."
    except (ValueError, TypeError):
        pass

# ── Section 10: Verdict ────────────────────────────────────────────────────────
sig_map = {"bullish": "HIGH CONVICTION BUY", "bearish": "AVOID", "neutral": "HOLD", "mixed": "ACCUMULATE ON DIPS"}
verdict_label = sig_map.get(result.overall_signal, "HOLD")
if result.overall_signal == "mixed" and conf < 0.5:
    verdict_label = "WAIT FOR BETTER ENTRY"

fund_verdict = verdicts.get("fundamental", {})
fund_dir = fund_verdict.get("direction", "N/A") if isinstance(fund_verdict, dict) else "N/A"
fund_summary = fund_verdict.get("summary", "") if isinstance(fund_verdict, dict) else ""

agenda_verdict = verdicts.get("announcement", {})
news_verdict = verdicts.get("news", {})

# Identify top risks from signals_against
top_risks = result.signals_against[:3] if result.signals_against else ["No major structural risks identified"]

# ── Assemble the 10-section report ─────────────────────────────────────────────
report_md = f"""# Stocxi — Long-Term Analysis: {SYMBOL}

---

### Section 1 — Stock Snapshot

| | |
|---|---|
| **Stock** | {result.stock} ({result.nse_symbol}) |
| **Sector** | {sector_val}{(' | Industry: ' + industry_val) if industry_val else ''} |
| **Exchange** | {exchange_line} | Market Cap: {mcap_line} |
| **Horizon** | Long Term (6 months+) |
| **Price** | {price_line} |
| **Date** | {result.analysis_date} |

---

### Section 2 — Knowledge Graph Summary

**Confluences** (nodes reinforcing each other):
{chr(10).join(confluence_lines) if confluence_lines else '_No significant confluences identified._'}

**Conflicts** (opposing signals):
{chr(10).join(conflict_lines) if conflict_lines else '_No significant contradictions identified._'}

**Knowledge Graph Visualization:** [Open 3D Interactive Graph]({graph_link})

> Edge types: CONFIRMS (×1.0), AMPLIFIES (×1.2), CONTRADICTS (×-1.0), DAMPENS (×-0.8), CAUSES (×1.1), TRIGGERS (×1.3), CONTEXTUALIZES (×0.5), CORRELATES (×0.4)

---

### Section 3 — Business Quality & Fundamentals

{chr(10).join(fund_prose_lines) if fund_prose_lines else '_Fundamental data not available for this analysis._'}

---

### Section 4 — Institutional & Promoter Conviction

{chr(10).join(holding_lines) if holding_lines else '_Holding data not available for this analysis._'}

---

### Section 5 — Financial Trend Over Multiple Periods

{chr(10).join(fin_lines) if fin_lines else '_Financial trend data not available._'}

---

### Section 6 — Sector Structural Thesis

{sector_prose if sector_prose else '_Sector trend data not available._'}

---

### Section 7 — Competitive Positioning

{peer_prose if peer_prose else '_Peer comparison data not available._'}

---

### Section 8 — Structural Announcements

{chr(10).join(ann_lines) if ann_lines else '_No structurally significant announcements that alter the long-term thesis._'}

---

### Section 9 — Technical Entry Context

{tech_prose if tech_prose else '_Technical entry context not available._'}

Technical verdict: **{tech_dir.upper()}**. {tech_summary}

---

### Section 10 — Verdict

**Long-Term Outlook: {verdict_label}**

{result.what_data_suggests}

**The Long-Term Thesis in One Line:**
> {result.signals_in_favor[0] if result.signals_in_favor else 'Insufficient data for a clear thesis.'}

**Thesis Risks:**
{chr(10).join(f"- {r}" for r in top_risks)}

**What to Monitor (annual checkpoints):**
- Revenue growth trajectory quarter-over-quarter — confirms or denies the compounding thesis
- Margin sustainability — expanding margins signal pricing power; contracting margins flag competitive pressure
- Promoter holding changes — any decline over multiple quarters is a structural red flag

---

_Data Completeness: {result.data_disclosure}_

---

## Disclaimer

{result.disclaimer}

---

_Report generated by Stocxi · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M IST')} · Model: {draft.model_id} · Prompt: {draft.prompt_version} · Weights: {draft.weight_version} · Latency: {latency_ms/1000:.1f}s · Analysis ID: {result.analysis_id}_
"""

report_path.write_text(report_md)
print(f"  Report written: {report_path}")

# ── Final summary ──────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  ANALYSIS COMPLETE")
print(f"  Stock          : {SYMBOL}")
print(f"  Signal         : {result.overall_signal.upper()}")
print(f"  Confidence     : {conf:.0%} ({conf_label})")
print(f"  Total nodes    : {len(all_nodes)}")
print(f"  Total time     : {latency_ms/1000:.1f}s")
print(f"  Report         : reports/{SYMBOL}_{datetime.date.today()}_analysis.md")
print(f"  Graph          : {graph_link}")
print(f"{'='*60}\n")
