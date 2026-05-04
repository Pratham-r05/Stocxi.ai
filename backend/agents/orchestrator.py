"""
orchestrator.py — Full Analysis Pipeline Orchestrator.

Contract (AGENTS.md §6 / ARCHITECTURE §13-14):
  Input:  FetchRequest
  Output: (AnalysisResult, admin_view dict)

Responsibilities:
  - Parallel fan-out to all 5 data agents (45s per-agent timeout)
  - AnonMap construction + identity scrub of sanitized=False nodes
  - INSUFFICIENT_DATA gate (ARCHITECTURE §14)
  - Redis 3-tier cache lookup (before LLM) and write (after format)
  - Chains: agent_analysis → agent_verifier → formatter → audit_log
  - Owns analysis_id (UUID) and latency_ms measurement
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from agents import (
    agent_announcement,
    agent_context,
    agent_fundamental,
    agent_news,
    agent_technical,
)
from agents import agent_analysis, agent_verifier, formatter
from audit.audit_log import compute_data_hash, log_analysis
from cache.redis_client import TTL_ANALYSIS_RESULT, cache_get, cache_set
from calibration import apply_calibration
from schemas.messages import AnalysisResult, FetchFailure, FetchRequest
from schemas.node import Node
from util.sanitizer import AnonMap, build_anon_map, scrub_text
from graph.stocxi_knowledge_graph import StocxiKnowledgeGraph
from graph.knowledge_graph import build_graph, render_3d_html

logger = logging.getLogger(__name__)

# ── Knowledge graph output dir ─────────────────────────────────────────────────
_GRAPH_DIR = Path(__file__).parents[2] / "graphify-out" / "stocks"

# ── Config ─────────────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).parents[2] / "config"
_VERSIONS   = yaml.safe_load((_CONFIG_DIR / "versions.yaml").read_text())

_PROMPT_VER = _VERSIONS["prompt_version"]
_WEIGHT_VER = _VERSIONS["weight_version"]
_N_MIN      = _VERSIONS["min_nodes"]

# Calibration map — loaded once at import. Empty dict = identity pass-through.
_CALIB_PATH = _CONFIG_DIR / "calibration.yaml"
_CALIB_MAP: dict[str, Any] = {}
try:
    if _CALIB_PATH.exists():
        _CALIB_MAP = yaml.safe_load(_CALIB_PATH.read_text(encoding="utf-8")) or {}
except Exception as exc:
    logger.warning("orchestrator: could not load calibration.yaml — %s", exc)
    _CALIB_MAP = {}

AGENT_TIMEOUT_S = 120.0


# ── Exceptions ─────────────────────────────────────────────────────────────────

class InsufficientDataError(Exception):
    """Raised when node counts fall below N_MIN thresholds (ARCHITECTURE §14)."""

    def __init__(self, counts: dict[str, int], thresholds: dict[str, int]) -> None:
        missing = {
            cat: (counts.get(cat, 0), need)
            for cat, need in thresholds.items()
            if counts.get(cat, 0) < need
        }
        detail = "; ".join(f"{cat}: got {got}, need {need}" for cat, (got, need) in missing.items())
        super().__init__(f"INSUFFICIENT_DATA — {detail}")
        self.counts   = counts
        self.missing  = missing


# ── Cache key ──────────────────────────────────────────────────────────────────

def _cache_key(stock: str, profile_bucket: str, data_hash: str) -> str:
    return f"analysis:v{_PROMPT_VER}:{_WEIGHT_VER}:{stock.upper()}:{profile_bucket}:{data_hash}"


# ── Node sanitization ──────────────────────────────────────────────────────────

def _sanitize_nodes(nodes: list[Node], anon_map: AnonMap) -> list[Node]:
    """
    Apply identity scrub to nodes with sanitized=False (news, announcement).
    Returns a new list — originals are not mutated.
    """
    out: list[Node] = []
    for n in nodes:
        if n.sanitized:
            out.append(n)
        else:
            scrubbed_value = scrub_text(n.value, anon_map)
            out.append(n.model_copy(update={"value": scrubbed_value, "sanitized": True}))
    return out


# ── INSUFFICIENT_DATA gate ─────────────────────────────────────────────────────

def _check_sufficient(nodes: list[Node]) -> dict[str, int]:
    """Count nodes per category; raise InsufficientDataError if below N_MIN."""
    counts: dict[str, int] = {}
    for n in nodes:
        cat = n.category.value
        counts[cat] = counts.get(cat, 0) + 1

    thresholds = {
        "technical":    _N_MIN["technical"],
        "fundamental":  _N_MIN["fundamental"],
        "announcement": _N_MIN["announcement"],
    }
    failing = {cat for cat, need in thresholds.items() if counts.get(cat, 0) < need}
    if failing:
        raise InsufficientDataError(counts, thresholds)
    return counts


# ── Fan-out helpers ────────────────────────────────────────────────────────────

_AGENTS = [
    ("technical",    agent_technical),
    ("fundamental",  agent_fundamental),
    ("news",         agent_news),
    ("announcement", agent_announcement),
    ("context",      agent_context),
]


async def _run_agent_safe(
    name: str, module: Any, request: FetchRequest
) -> tuple[str, list[Node]]:
    """Run one data agent with a hard timeout. Returns empty list on any failure."""
    try:
        result = await asyncio.wait_for(module.run(request), timeout=AGENT_TIMEOUT_S)
        if isinstance(result, FetchFailure):
            logger.warning(
                "orchestrator: agent=%s FetchFailure — domain=%s reason=%s error=%s",
                name, result.domain, result.reason, result.error,
            )
            return name, []
        logger.info("orchestrator: agent=%s nodes=%d", name, len(result))
        return name, result
    except asyncio.TimeoutError:
        logger.warning("orchestrator: agent=%s timed out after %.0fs", name, AGENT_TIMEOUT_S)
        return name, []
    except Exception as exc:
        logger.warning("orchestrator: agent=%s failed — %s", name, exc)
        return name, []


# ── Public entry point ─────────────────────────────────────────────────────────

async def run(request: FetchRequest) -> tuple[AnalysisResult, dict[str, Any]]:
    """
    Run the full analysis pipeline for one FetchRequest.

    Steps:
      1. Parallel fan-out → 5 data agents (50s timeout each)
      2. AnonMap construction + scrub sanitized=False nodes
      3. Cache lookup — return early on hit
      4. INSUFFICIENT_DATA gate
      5. Build knowledge graph (BEFORE analysis — KG serialization goes into prompt)
      6. agent_analysis → agent_verifier → formatter
      7. Audit log write
      8. Cache write
      9. 3D graph render + backward propagation (post-analysis, non-blocking)

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

    # ── 6b. Confidence calibration ──────────────────────────────────────────────
    raw_confidence = verified.draft.raw_confidence
    calibrated_confidence = apply_calibration(raw_confidence, _CALIB_MAP)
    result = result.model_copy(update={"calibrated_confidence": calibrated_confidence})
    admin_view["calibrated_confidence"] = calibrated_confidence
    admin_view["calibration_method"] = _CALIB_MAP.get("method", "identity")

    # ── 7. Audit log ───────────────────────────────────────────────────────────
    log_analysis(
        analysis_id=analysis_id, stock=request.stock,
        profile_bucket=request.profile.bucket, as_of_date=str(request.as_of_date),
        node_ids=node_ids, prompt_version=draft.prompt_version,
        weight_version=draft.weight_version, model_id=draft.model_id,
        input_nodes_json=json.dumps([n.node_id for n in all_nodes]),
        full_prompt=full_prompt, full_raw_output=full_raw_output,
        final_output=result.model_dump(mode="json"), admin_view=admin_view,
    )

    # ── 8. Cache write ─────────────────────────────────────────────────────────
    cache_payload = result.model_dump(mode="json")
    cache_payload["_admin_view"] = admin_view
    await cache_set(ckey, cache_payload, TTL_ANALYSIS_RESULT)

    # ── 9. 3D graph render + backward propagation ─────────────────────────────
    try:
        from datetime import date as _date
        graph_date = str(request.as_of_date) if request.as_of_date else str(_date.today())
        graph_path = _GRAPH_DIR / request.stock / f"{graph_date}.html"

        if kg is not None:
            G = build_graph(
                all_nodes, admin_view,
                edges=kg._edges,
                effective_weights=kg._effective_weights,
                horizon=horizon,
            )
            admin_view["knowledge_graph_path"] = str(graph_path)
            admin_view["graph_edge_types"] = len(kg._edges)

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
            G = build_graph(all_nodes, admin_view, horizon=horizon)

        render_3d_html(
            G,
            title=f"Stocxi — {request.stock}",
            stock_name=request.stock,
            horizon=horizon,
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
