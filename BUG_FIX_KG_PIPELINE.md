# BUG_FIX_KG_PIPELINE.md — Knowledge Graph USP Pipeline Fix

> Created: 2026-04-28
> Status: READY FOR EXECUTION
> Priority: CRITICAL — the knowledge graph is the USP but is completely disconnected from analysis

---

## Problem Summary

The StocxiKnowledgeGraph (HFBP algorithm) and per-node context generation are **built but never connected** to the analysis pipeline. Gemini never sees the graph relationships, effective weights, or node context strings. The entire KG USP is dead code in production.

---

## 5 Critical Gaps

| # | Gap | Impact | File(s) |
|---|---|---|---|
| G1 | Orchestrator uses legacy `score_all()` → `build_edges()` → `serialize_for_llm()` pipeline instead of `StocxiKnowledgeGraph` | HFBP algorithm never runs; no horizon-aware weights | `backend/agents/orchestrator.py:276-303` |
| G2 | `prompt_template.jinja` never renders `{{ n.context }}` | All Gemini-generated context strings invisible to analysis LLM | `backend/analysis/prompt_template.jinja:44-108` |
| G3 | `kg_serialization` computed but never passed to analysis agent | No graph relationships or effective weights in LLM prompt | `orchestrator.py:288`, `agent_analysis.py:342-389` |
| G4 | Analysis prompt has no knowledge graph section | LLM sees isolated nodes — no CONFIRMS/AMPLIFIES/CONTRADICTS relationships | `prompt_template.jinja` |
| G5 | No API endpoint to serve 3D graph HTML in browser | User can't view the knowledge graph | `backend/routers/v2_analysis.py` |

---

## What IS Working (verified via code audit)

| Component | Status | Detail |
|---|---|---|
| Technical context generation | ✅ | `generate_technical_context()` batch-calls Gemini, writes 1-2 sentence context per indicator into `node.context` |
| Fundamental ratio context | ✅ | `generate_fundamental_context()` explains each ratio vs sector benchmarks |
| Financial statement context | ✅ | `generate_financial_context()` extracts last 4 quarters, Gemini assesses QoQ/YoY trends |
| News summarization | ✅ | `_summarize_articles()` → Gemini generates summary + relevance + signal_class + horizon, stored in `llm_summary` |
| Announcement summarization | ✅ | `_summarize_announcements()` → Gemini generates 1-2 line summaries, stored in `llm_summary` |
| News context promotion | ✅ | `apply_news_context()` promotes `llm_summary` → `node.context` |
| Announcement context promotion | ✅ | `apply_announcement_context()` promotes `llm_summary` → `node.context` |
| HFBP algorithm | ✅ | `StocxiKnowledgeGraph` builds, forward/backward propagates, serializes for LLM |
| Context generator wiring in agents | ✅ | All 4 agents (technical, fundamental, news, announcement) call their context generators |
| News cap at 10 | ✅ | `sources.yaml` has `max_items_per_analysis: 10` |
| Announcements cap at 10 | ✅ | `unique = unique[:10]` in `announcements_service.py:262` |

---

## Fix Plan — 6 Tasks (Sequential Dependencies)

### Task 1: Add `node.context` to Jinja prompt template

**File:** `backend/analysis/prompt_template.jinja`

For EACH category section (technical, fundamental, news, announcement), add `context:` line after `weight:`:

```jinja
{% for n in technical_nodes %}
node_id: {{ n.node_id }}
  name:       {{ n.name }}
  value:      {{ n.value }}
  signal:     {{ n.signal.value }}
  confidence: {{ "%.2f"|format(n.confidence) }}
  weight:     {{ "%.4f"|format(n.weight) }}
  context:    {{ n.context }}
{% endfor %}
```

Same pattern for `fundamental_nodes`, `news_nodes`, `announcement_nodes`. Context nodes do NOT need context (they are context already).

---

### Task 2: Add KG section to Jinja prompt template

**File:** `backend/analysis/prompt_template.jinja`

After the CONTEXT section (line ~108) and BEFORE the 10-STEP PROTOCOL section (line ~110), add:

```jinja
{% if kg_serialization %}
══════════════════════════════════════════════════════════════
KNOWLEDGE GRAPH — Node Relationships & Effective Weights
══════════════════════════════════════════════════════════════
{{ kg_serialization }}

Use this graph information to:
- Prioritize nodes with higher effective_weight in your analysis
- Understand relationships (CONFIRMS, AMPLIFIES, CONTRADICTS, DAMPENS) between indicators
- Resolve contradictions using the hierarchy in Step 9
- Note that nodes below the weight threshold are less relevant for this horizon
{% endif %}
```

---

### Task 3: Update `agent_analysis.py` to accept and forward `kg_serialization`

**File:** `backend/agents/agent_analysis.py`

Change 1 — Function signature (line ~342):
```python
async def run(
    nodes: list[Node], request: FetchRequest, kg_serialization: str = ""
) -> tuple[AnalysisDraft, str, str]:
```

Change 2 — `_render_prompt` signature (line ~117):
```python
def _render_prompt(nodes: list[Node], request: FetchRequest, kg_serialization: str = "") -> str:
```

Change 3 — Template render call (line ~123), add `kg_serialization=kg_serialization`:
```python
return _TEMPLATE.render(
    prompt_version=_PROMPT_VER,
    weight_version=_WEIGHT_VER,
    model_id=_MODEL_ID,
    profile_horizon=horizon,
    profile_risk=risk,
    cat_weight_technical=weights["technical"],
    cat_weight_fundamental=weights["fundamental"],
    cat_weight_news=weights["news"],
    cat_weight_announcement=weights["announcement"],
    technical_nodes=cats["technical"],
    fundamental_nodes=cats["fundamental"],
    news_nodes=cats["news"],
    announcement_nodes=cats["announcement"],
    context_nodes=cats["context"],
    kg_serialization=kg_serialization,
)
```

Change 4 — Pass through in `run()` (line ~368):
```python
prompt = _render_prompt(nodes, request, kg_serialization)
```

---

### Task 4: Rewrite orchestrator — use StocxiKnowledgeGraph + REORDER pipeline

**File:** `backend/agents/orchestrator.py`

This is the biggest change. Full rewritten `run()` function:

**Import changes** (top of file):
```python
# REMOVE these:
# from backend.graph.knowledge_graph import build_graph, render_3d_html, serialize_for_llm
# from backend.graph.builder import build_edges
# from backend.graph.scorer import score_all

# ADD these:
from backend.graph.stocxi_knowledge_graph import StocxiKnowledgeGraph
from backend.graph.knowledge_graph import build_graph, render_3d_html
```

**Full restructured `run()` function:**

Key changes:
1. KG build moved BEFORE analysis agent call (step 5, not step 8)
2. `kg_serialization` passed to `agent_analysis.run()`
3. Backward propagation + weight saving happens after analysis
4. 3D render uses KG edges directly
5. All graph code wrapped in try/except — analysis continues if KG fails

```python
async def run(request: FetchRequest) -> tuple[AnalysisResult, dict[str, Any]]:
    """
    Run the full analysis pipeline for one FetchRequest.

    Steps:
      1. Parallel fan-out → 5 data agents (50s timeout each)
      2. AnonMap construction + scrub sanitized=False nodes
      3. Cache lookup — return early on hit
      4. Build knowledge graph (BEFORE analysis — KG serialization goes into prompt)
      5. agent_analysis → agent_verifier → formatter
      6. Audit log write
      7. Cache write
      8. 3D graph render + backward propagation (post-analysis, non-blocking)

    Returns:
        (AnalysisResult, admin_view dict)

    Raises:
        InsufficientDataError: node counts below N_MIN.
        RuntimeError: LLM call failed after retries.
    """
    t0 = time.monotonic()
    analysis_id = str(uuid.uuid4())

    # ── 1. Parallel fan-out ────────────────────────────────────────────────────
    agent_results = await asyncio.gather(
        *[_run_agent_safe(name, mod, request) for name, mod in _AGENTS]
    )

    all_nodes: list[Node] = []
    failed_agents: list[str] = []
    for name, nodes in agent_results:
        if nodes:
            all_nodes.extend(nodes)
        else:
            failed_agents.append(name)

    # ── 2. AnonMap + identity scrub ────────────────────────────────────────────
    anon_map = build_anon_map(stock=request.stock, sector=request.profile.sector)
    all_nodes = _sanitize_nodes(all_nodes, anon_map)

    # ── 3. Cache lookup ────────────────────────────────────────────────────────
    node_ids = [n.node_id for n in all_nodes]
    data_hash = compute_data_hash(node_ids)
    ckey = _cache_key(request.stock, request.profile.bucket, data_hash)

    cached = await cache_get(ckey)
    if cached:
        logger.info("orchestrator: cache HIT — %s/%s", request.stock, request.profile.bucket)
        result = AnalysisResult(**cached)
        admin_view = cached.get("_admin_view", {})
        return result.model_copy(update={"cache_hit": True}), admin_view

    # ── 4. INSUFFICIENT_DATA gate ──────────────────────────────────────────────
    _check_sufficient(all_nodes)

    # ── 5. Build knowledge graph (BEFORE analysis) ─────────────────────────────
    kg_serialization = ""
    kg: StocxiKnowledgeGraph | None = None
    kg_admin_meta: dict[str, Any] = {}
    horizon = (
        request.profile.horizon.value
        if hasattr(request.profile.horizon, "value")
        else str(request.profile.horizon)
    )
    try:
        kg = StocxiKnowledgeGraph(ticker=request.stock, horizon=horizon)
        kg.build(all_nodes, analysis_id=analysis_id)
        kg.forward_propagate()
        kg_serialization = kg.serialize_for_llm()
        kg_json = kg.to_json()
        kg_admin_meta = {
            "graph_node_count": kg_json["meta"]["node_count"],
            "graph_edge_count": kg_json["meta"]["edge_count"],
            "graph_active_nodes": kg_json["meta"]["active_node_count"],
        }
        logger.info(
            "orchestrator: KG built — %d nodes, %d edges, %d active (horizon=%s)",
            len(all_nodes), len(kg._edges), kg_json["meta"]["active_node_count"], horizon,
        )
    except Exception as kg_exc:
        logger.warning("orchestrator: KG build failed (non-fatal, analysis continues) — %s", kg_exc)

    # ── 6. Analysis pipeline ───────────────────────────────────────────────────
    failed_msgs = (
        [f"{a} data unavailable today" for a in failed_agents]
        if failed_agents else None
    )

    draft, full_prompt, full_raw_output = await agent_analysis.run(
        all_nodes, request, kg_serialization=kg_serialization
    )
    verified = agent_verifier.run(draft, all_nodes)

    latency_ms = int((time.monotonic() - t0) * 1000)
    result, admin_view = formatter.format_result(
        verified=verified, anon_map=anon_map, request=request,
        nodes=all_nodes, failed_fetches=failed_msgs,
        analysis_id=analysis_id, latency_ms=latency_ms, cache_hit=False,
    )
    admin_view.update(kg_admin_meta)

    # ── 7. Confidence calibration ──────────────────────────────────────────────
    raw_confidence = verified.draft.raw_confidence
    calibrated_confidence = apply_calibration(raw_confidence, _CALIB_MAP)
    result = result.model_copy(update={"calibrated_confidence": calibrated_confidence})
    admin_view["calibrated_confidence"] = calibrated_confidence
    admin_view["calibration_method"] = _CALIB_MAP.get("method", "identity")

    # ── 8. Audit log ──────────────────────────────────────────────────────────
    log_analysis(
        analysis_id=analysis_id, stock=request.stock,
        profile_bucket=request.profile.bucket, as_of_date=str(request.as_of_date),
        node_ids=node_ids, prompt_version=draft.prompt_version,
        weight_version=draft.weight_version, model_id=draft.model_id,
        input_nodes_json=json.dumps([n.node_id for n in all_nodes]),
        full_prompt=full_prompt, full_raw_output=full_raw_output,
        final_output=result.model_dump(mode="json"), admin_view=admin_view,
    )

    # ── 9. Cache write ────────────────────────────────────────────────────────
    cache_payload = result.model_dump(mode="json")
    cache_payload["_admin_view"] = admin_view
    await cache_set(ckey, cache_payload, TTL_ANALYSIS_RESULT)

    # ── 10. 3D graph render + backward propagation ─────────────────────────────
    try:
        from datetime import date as _date
        graph_date = str(request.as_of_date) if request.as_of_date else str(_date.today())
        graph_path = _GRAPH_DIR / request.stock / f"{graph_date}.html"

        if kg is not None:
            # Use edges from StocxiKnowledgeGraph (HFBP-typed)
            G = build_graph(all_nodes, admin_view, edges=kg._edges)
            admin_view["knowledge_graph_path"] = str(graph_path)
            admin_view["graph_edge_types"] = len(kg._edges)

            # Backward propagation — update learned weights for future runs
            try:
                per_node_relevance = {
                    n.node_id: max(0.3, n.weight * n.confidence)
                    for n in all_nodes
                }
                kg.backward_propagate(per_node_relevance)
                kg.save_weights()
                logger.info("orchestrator: backward propagation + weight save complete for %s", request.stock)
            except Exception as bp_exc:
                logger.warning("orchestrator: backward propagation failed (non-fatal) — %s", bp_exc)
        else:
            # Fallback: render without HFBP edges
            G = build_graph(all_nodes, admin_view)

        render_3d_html(
            G,
            title=f"Stocxi — {request.stock} | {graph_date}",
            output_path=graph_path,
        )
        if "knowledge_graph_path" not in admin_view:
            admin_view["knowledge_graph_path"] = str(graph_path)
    except Exception as graph_exc:
        logger.warning("orchestrator: 3D graph render failed (non-fatal) — %s", graph_exc)

    logger.info(
        "orchestrator: %s/%s — overall=%s raw_conf=%.2f calib_conf=%.2f method=%s latency=%dms stripped=%d cache=MISS",
        request.stock, request.profile.bucket,
        result.overall_signal, raw_confidence, calibrated_confidence,
        _CALIB_MAP.get("method", "identity"),
        latency_ms, verified.stripped_claims,
    )
    return result, admin_view
```

---

### Task 5: Add graph HTML serving endpoint

**File:** `backend/routers/v2_analysis.py`

Add at the bottom, before the closing:

```python
from pathlib import Path
from fastapi.responses import FileResponse

_GRAPH_DIR = Path(__file__).parents[2] / "graphify-out" / "stocks"


@router.get("/{symbol}/graph")
async def get_knowledge_graph(
    symbol: str,
    as_of_date: str = Query(
        default="",
        description="ISO date string (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Serve the 3D knowledge graph HTML for visualization in browser."""
    from datetime import date as _date

    graph_date = as_of_date if as_of_date else str(_date.today())
    graph_path = _GRAPH_DIR / symbol.upper() / f"{graph_date}.html"
    if not graph_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Knowledge graph not found for {symbol.upper()} on {graph_date}. "
                f"Run analysis first via GET /api/v2/analysis/{symbol}"
            ),
        )
    return FileResponse(
        path=str(graph_path),
        media_type="text/html",
        filename=f"{symbol.upper()}_{graph_date}_graph.html",
    )
```

---

### Task 6: Bump versions

**File:** `config/versions.yaml`

Since the prompt template changed (added `context` + `kg_serialization`), bump versions:

```yaml
arch_version: "2026.04.b"      # was "2026.04.a"
prompt_version: "2026.04.b"    # was "2026.04.a"
```

---

### Task 7: End-to-end smoke test with BAJAJ-AUTO

After all changes, run:

```bash
conda run -n stocxi python -c "
import asyncio
from datetime import date
from backend.agents.orchestrator import run
from backend.schemas.messages import FetchRequest, UserProfile, Horizon, Risk

async def test():
    req = FetchRequest(
        stock='BAJAJ-AUTO',
        as_of_date=date.today(),
        profile=UserProfile(horizon=Horizon('short'), risk=Risk('moderate'), sector=''),
        request_id='test-e2e-001',
    )
    result, admin = await run(req)
    print(f'Signal: {result.overall_signal}')
    print(f'Confidence: {result.calibrated_confidence}')
    print(f'KG nodes: {admin.get(\"graph_node_count\", \"N/A\")}')
    print(f'KG active: {admin.get(\"graph_active_nodes\", \"N/A\")}')
    print(f'KG edges: {admin.get(\"graph_edge_count\", \"N/A\")}')
    print(f'Graph path: {admin.get(\"knowledge_graph_path\", \"N/A\")}')
    print('E2E pipeline works')

asyncio.run(test())
"
```

Then verify the graph is viewable:
```bash
conda run -n stocxi uvicorn backend.main:app --reload --port 8000
# In browser: http://localhost:8000/api/v2/analysis/BAJAJ-AUTO
# Then: http://localhost:8000/api/v2/analysis/BAJAJ-AUTO/graph
```

---

## Execution Order

Task 1 (template context) + Task 2 (template KG section) can be done together.
Task 3 (agent_analysis.py) depends on Task 1+2 (template must exist first).
Task 4 (orchestrator rewrite) depends on Task 3 (analysis agent must accept kg_serialization).
Task 5 (endpoint) is independent.
Task 6 (version bump) must be last (after all code changes).
Task 7 (E2E test) depends on all prior tasks.

---

## Key Architecture Notes for Next Session

1. **StocxiKnowledgeGraph constructor:** `StocxiKnowledgeGraph(ticker, horizon)` — NOT keyword args `nodes=`, `edges=`, etc. Call `kg.build(nodes, analysis_id)` then `kg.forward_propagate()`.

2. **Node.source_url** is `str` with default `""` (not `Optional[str]`). Never pass `None`.

3. **Conda environment:** Always use `conda run -n stocxi python ...` — never `.venv312`.

4. **Prompt version bump** flushes the analysis cache automatically (cache key includes `prompt_version`).

5. **All graph code is wrapped in try/except** — if the KG fails, the analysis pipeline continues without it. This is production-safe.

6. **Backward propagation** (`kg.backward_propagate()` + `kg.save_weights()`) is non-blocking and non-fatal. It saves learned edge weights for future runs.

7. **The v2_analysis.py router** already imports from `agents.orchestrator` (relative import without `backend.` prefix). Keep consistent.

8. **`build_graph()` and `render_3d_html()`** are from `backend.graph.knowledge_graph` — legacy functions for 3D HTML rendering. They still work with HFBP edges because the Edge dataclass has a compatible shape.

---

*This file is the single source of truth for the KG pipeline fix. Update NEW_PROGRESS.md after completion.*