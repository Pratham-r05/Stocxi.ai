"""
context_generator.py — Gemini-powered context generation for knowledge graph nodes.

Role: At data-fetch time, before the HFBP algorithm runs, this service generates
a human-readable, horizon-aware context string for each node that explains what the
signal means for the investor's specific time horizon.

Why this exists:
  - Raw indicator values (RSI: 72.4) are meaningless without interpretation.
  - The same RSI value means something different for a SHORT vs LONG investor.
  - Financial nodes need QoQ/YoY comparison context to be useful.
  - Context generated here is stored in node.context and injected into the
    knowledge graph LLM serialization so Gemini can reason about relationships.

Context generation by category:
  - Technical:    What the indicator signals + why it matters for this horizon.
  - Fundamental:  What the ratio value means vs sector/historical benchmarks.
  - Financial:    QoQ and YoY comparison — acceleration, deceleration, reversal.
  - News:         Uses existing llm_summary from news_service (no extra call).
  - Announcement: Uses existing llm_summary from announcements_service (no extra call).

All calls are sync (run inside thread pool executor from async agents).
Falls back gracefully — any failure returns nodes unchanged with empty context.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.schemas.node import Node, NodeCategory

logger = logging.getLogger(__name__)

# ── Technical subcategory labels for horizon-aware prompt ─────────────────────
_MOMENTUM_TECH: frozenset[str] = frozenset([
    "RSI_14", "Stochastic_K", "Stochastic_D", "Stochastic", "Williams_R", "CCI", "ROC",
])
_TREND_TECH: frozenset[str] = frozenset([
    "MACD", "ADX_14", "SMA_20", "SMA_50", "SMA_200", "SMA",
    "EMA_12", "EMA_26", "EMA", "Ichimoku", "Parabolic_SAR",
])
_VOLUME_TECH: frozenset[str] = frozenset([
    "OBV", "VWAP", "Volume_SMA_20", "CMF", "MFI",
])
_VOLATILITY_TECH: frozenset[str] = frozenset([
    "Bollinger_Upper", "Bollinger_Lower", "Bollinger_Bands", "ATR_14",
    "52W_HL_Ratio",
])

# Fundamental ratio nodes (as opposed to financial statement nodes)
_RATIO_NODES: frozenset[str] = frozenset([
    "PE_Ratio", "PB_Ratio", "ROE", "ROCE", "EPS", "OPM", "NPM",
    "Dividend_Yield", "Book_Value", "Market_Cap", "52W_High_Low",
    "Debt_To_Equity", "Interest_Coverage", "EBITDA_Margin",
    "Promoter_Holding", "Public_Retail_Holding", "FII_Holding", "DII_Holding",
])

_FINANCIAL_NODES: frozenset[str] = frozenset([
    "Revenue_Quarterly", "Net_Profit_Quarterly", "OPM_Quarterly",
    "EPS_Quarterly", "Expenses_Quarterly", "Operating_Profit_Quarterly",
    "Revenue_Annual", "Net_Profit_Annual", "OPM_Annual",
    "EPS_Annual", "Expenses_Annual", "Operating_Profit_Annual",
    "Balance_Sheet", "Cash_Flow",
    "Revenue_Growth", "Profit_Growth",
    "Revenue_TTM", "Revenue_Growth_YoY", "PAT_TTM", "PAT_Growth_YoY",
    "EBITDA_TTM", "EBITDA_Margin",
    "Debt_To_Equity", "Operating_Cash_Flow", "Free_Cashflow", "Interest_Coverage",
    "Total_Assets", "Total_Liabilities", "Reserves", "Borrowings",
    "Cash_From_Investing", "Cash_From_Financing",
])

# Financial statement nodes (need QoQ/YoY analysis)
_FINANCIAL_NODES: frozenset[str] = frozenset([
    "Revenue_Quarterly", "Net_Profit_Quarterly", "OPM_Quarterly",
    "EPS_Quarterly", "Revenue_Annual", "Net_Profit_Annual",
    "Balance_Sheet", "Cash_Flow", "Revenue_Growth", "Profit_Growth",
    "Debt_To_Equity", "Operating_Cash_Flow",
])

_HORIZON_DESCRIPTIONS = {
    "short":  "1–2 weeks (short-term price direction and momentum)",
    "medium": "1–3 months (medium-term trend and fundamentals)",
    "long":   "1–3 years (long-term compounding and value creation)",
}


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_technical_context(
    nodes: list[Node],
    horizon: str,
    ticker: str = "STOCK_A",
) -> list[Node]:
    """Generate horizon-aware context strings for all technical indicator nodes.

    Sends technical nodes in batches of 12 to Gemini. Each node gets a
    1-2 sentence context string explaining what the signal means for the
    investor's chosen time horizon.

    Args:
        nodes:   List of Node objects from the technical agent.
        horizon: "short", "medium", or "long".
        ticker:  Anonymized ticker (default STOCK_A — real name never sent to LLM).

    Returns:
        Same list with node.context populated. Nodes without context get "".
    """
    tech_nodes = [n for n in nodes if n.category == NodeCategory.technical]
    if not tech_nodes:
        return nodes

    horizon_desc = _HORIZON_DESCRIPTIONS.get(horizon, horizon)
    all_results: list[dict[str, Any]] = []

    for batch_start in range(0, len(tech_nodes), _BATCH_SIZE):
        batch = tech_nodes[batch_start:batch_start + _BATCH_SIZE]
        node_lines: list[str] = []
        for i, node in enumerate(batch):
            subcat = _get_tech_subcat(node.name)
            node_lines.append(
                f"[{i}] {node.name} | value: {node.value} | signal: {node.signal.value} "
                f"| subcategory: {subcat}"
            )

        prompt = (
            f"You are a technical analyst for Indian equity markets.\n"
            f"The stock is {ticker}. The investor's horizon is: {horizon_desc}.\n\n"
            f"Below are technical indicator nodes from the knowledge graph.\n"
            f"For EACH node, write ONE concise sentence (max 120 chars) that explains:\n"
            f"  - What this specific value/signal means in market terms\n"
            f"  - Why it is relevant (or not relevant) for a {horizon} investor\n"
            f"  - Any key risk or confirmation this indicator provides\n\n"
            f"Return a JSON array with one object per node:\n"
            f'  [{{"index": 0, "context": "..."}}]\n\n'
            f"Nodes:\n" + "\n".join(node_lines) +
            f"\n\nReturn ONLY valid JSON array. No markdown."
        )

        batch_results = _call_gemini_batch(prompt, len(batch), ticker, "technical")
        # Remap batch-local indices to global indices
        for item in batch_results:
            if "index" in item:
                item["index"] = int(item["index"]) + batch_start
        all_results.extend(batch_results)

    return _apply_context(nodes, tech_nodes, all_results)


def generate_fundamental_context(
    nodes: list[Node],
    horizon: str,
    ticker: str = "STOCK_A",
) -> list[Node]:
    """Generate horizon-aware context for ALL fundamental nodes.

    Sends every fundamental node (ratios + financial statements + balance sheet +
    cash flow + shareholding) to Gemini in batches of 12. Each node gets a
    concise context string explaining what the value means for the investor's horizon.

    Args:
        nodes:   All nodes (non-fundamental are passed through unchanged).
        horizon: "short", "medium", or "long".
        ticker:  Anonymized ticker.

    Returns:
        Same list with node.context populated for all fundamental nodes.
    """
    fund_nodes = [n for n in nodes if n.category == NodeCategory.fundamental]
    if not fund_nodes:
        return nodes

    horizon_desc = _HORIZON_DESCRIPTIONS.get(horizon, horizon)
    all_results: list[dict[str, Any]] = []

    for batch_start in range(0, len(fund_nodes), _BATCH_SIZE):
        batch = fund_nodes[batch_start:batch_start + _BATCH_SIZE]
        node_lines: list[str] = []
        for i, node in enumerate(batch):
            vr = node.value_raw or {}
            extras = ""
            if "sector_pe" in vr:
                extras += f" | sector_pe: {vr['sector_pe']}"
            if "yoy_pct" in vr:
                extras += f" | yoy: {vr['yoy_pct']}%"
            if "qoq_pct" in vr:
                extras += f" | qoq: {vr['qoq_pct']}%"
            if "cagr_3y_pct" in vr:
                extras += f" | 3y_cagr: {vr['cagr_3y_pct']}%"
            node_lines.append(
                f"[{i}] {node.name} | {node.value} | signal: {node.signal.value}{extras}"
            )

        prompt = (
            f"You are a fundamental analyst for Indian equity markets.\n"
            f"The company is {ticker}. Investor horizon: {horizon_desc}.\n\n"
            f"For each node, write ONE concise sentence (max 150 chars) explaining:\n"
            f"  - What this value means about the company's financial health or valuation\n"
            f"  - Whether it is positive, negative, or neutral for a {horizon} investor\n"
            f"  - For statement items: QoQ/YoY trend direction (accelerating/decelerating/reversing/stable)\n"
            f"  - For ratios: comparison vs sector benchmarks if relevant\n\n"
            f"Return JSON array: [{{'index': 0, 'context': '...'}}]\n\n"
            f"Nodes:\n" + "\n".join(node_lines) +
            f"\n\nReturn ONLY valid JSON array. No markdown."
        )

        batch_results = _call_gemini_batch(prompt, len(batch), ticker, "fundamental")
        for item in batch_results:
            if "index" in item:
                item["index"] = int(item["index"]) + batch_start
        all_results.extend(batch_results)

    return _apply_context(nodes, fund_nodes, all_results)


def generate_financial_context(
    nodes: list[Node],
    horizon: str,
    ticker: str = "STOCK_A",
) -> list[Node]:
    """Generate QoQ/YoY context for financial statement nodes.

    This is now a superset pass — it processes ALL fundamental nodes that still
    lack context after generate_fundamental_context, plus enriches financial
    statement nodes with QoQ/YoY trend data from value_raw.

    Args:
        nodes:   All nodes (non-fundamental passed through unchanged).
        horizon: "short", "medium", or "long".
        ticker:  Anonymized ticker.

    Returns:
        Same list with node.context populated/enriched for financial statement nodes.
    """
    fin_nodes = [
        n for n in nodes
        if n.category == NodeCategory.fundamental and n.name in _FINANCIAL_NODES and not n.context
    ]
    if not fin_nodes:
        return nodes

    horizon_desc = _HORIZON_DESCRIPTIONS.get(horizon, horizon)
    all_results: list[dict[str, Any]] = []

    for batch_start in range(0, len(fin_nodes), _BATCH_SIZE):
        batch = fin_nodes[batch_start:batch_start + _BATCH_SIZE]
        node_lines: list[str] = []
        for i, node in enumerate(batch):
            vr = node.value_raw or {}
            periods_str = ""
            if "periods" in vr and vr["periods"]:
                recent = vr["periods"][:4]
                parts = [f"{p.get('period','?')}: {p.get('value_cr', p.get('value_pct', p.get('value','?')))}" for p in recent]
                periods_str = " | ".join(parts)
            elif "yoy_pct" in vr:
                periods_str = (
                    f"YoY: {vr.get('yoy_pct','?')}% | "
                    f"QoQ: {vr.get('qoq_pct','?')}% | "
                    f"3Y CAGR: {vr.get('cagr_3y_pct','?')}%"
                )

            node_lines.append(
                f"[{i}] {node.name} | {node.value} | signal: {node.signal.value}"
                + (f" | recent_data: {periods_str}" if periods_str else "")
            )

        prompt = (
            f"You are a financial analyst for Indian equity markets.\n"
            f"The company is {ticker}. Investor horizon: {horizon_desc}.\n\n"
            f"For each financial statement node, write ONE sentence (max 150 chars) that:\n"
            f"  1. States the QoQ trend (accelerating / decelerating / reversing / stable)\n"
            f"  2. States the YoY trend if data is available\n"
            f"  3. Interprets what this means for a {horizon} investor\n"
            f"     (e.g. margin expansion, revenue deceleration, debt increasing)\n\n"
            f"Return JSON array: [{{'index': 0, 'context': '...'}}]\n\n"
            f"Nodes:\n" + "\n".join(node_lines) +
            f"\n\nReturn ONLY valid JSON array. No markdown."
        )

        batch_results = _call_gemini_batch(prompt, len(batch), ticker, "financial")
        for item in batch_results:
            if "index" in item:
                item["index"] = int(item["index"]) + batch_start
        all_results.extend(batch_results)

    return _apply_context(nodes, fin_nodes, all_results)


def apply_news_context(nodes: list[Node]) -> list[Node]:
    """Copy llm_summary from value_raw into node.context for news nodes.

    News nodes already have Gemini summaries from news_service._summarize_articles.
    This just promotes them into the context field — no extra LLM call needed.

    Args:
        nodes: All nodes from the news agent.

    Returns:
        Same list with news node.context populated from llm_summary.
    """
    updated: list[Node] = []
    for node in nodes:
        if node.category == NodeCategory.news:
            summary = (node.value_raw or {}).get("llm_summary", "")
            if summary and not node.context:
                node = node.model_copy(update={"context": str(summary)[:200]})
        updated.append(node)
    return updated


def apply_announcement_context(nodes: list[Node]) -> list[Node]:
    """Copy llm_summary from value_raw into node.context for announcement nodes.

    Announcement nodes already have Gemini summaries from announcements_service.
    This just promotes them into the context field — no extra LLM call needed.

    Args:
        nodes: All nodes from the announcement agent.

    Returns:
        Same list with announcement node.context populated from llm_summary.
    """
    updated: list[Node] = []
    for node in nodes:
        if node.category == NodeCategory.announcement:
            summary = (node.value_raw or {}).get("llm_summary", "")
            if summary and not node.context:
                node = node.model_copy(update={"context": str(summary)[:200]})
        updated.append(node)
    return updated


def generate_context_category_context(
    nodes: list[Node],
    horizon: str,
    ticker: str = "STOCK_A",
) -> list[Node]:
    """Generate context for market regime / sector / peer / completeness nodes.

    These nodes often have placeholder values when data is unavailable. When
    they DO have real values, we generate a brief horizon-aware interpretation.
    No LLM call is made for placeholder values like "Unknown" — context stays empty.

    Args:
        nodes:   All nodes (context-category subset is extracted).
        horizon: "short", "medium", or "long".
        ticker:  Anonymized ticker.

    Returns:
        Same list with node.context populated where meaningful data exists.
    """
    PLACEHOLDERS = {"unknown", "data unavailable", "n/a", "computed by orchestrator",
                    "peer data not yet implemented", ""}
    ctx_nodes = [
        n for n in nodes
        if n.category == NodeCategory.context
        and n.value.strip().lower() not in PLACEHOLDERS
    ]
    if not ctx_nodes:
        return nodes

    horizon_desc = _HORIZON_DESCRIPTIONS.get(horizon, horizon)
    node_lines: list[str] = []
    for i, node in enumerate(ctx_nodes):
        node_lines.append(
            f"[{i}] {node.name} | {node.value} | signal: {node.signal.value}"
        )

    prompt = (
        f"You are a market analyst for Indian equity markets.\n"
        f"The stock is {ticker}. Investor horizon: {horizon_desc}.\n\n"
        f"For each context node, write ONE sentence (max 120 chars) interpreting:\n"
        f"  - What the value means for the broader market or sector environment\n"
        f"  - How it affects a {horizon} investor's decision\n\n"
        f"Return JSON array: [{{'index': 0, 'context': '...'}}]\n\n"
        f"Nodes:\n" + "\n".join(node_lines) +
        f"\n\nReturn ONLY valid JSON array. No markdown."
    )

    results = _call_gemini_batch(prompt, len(ctx_nodes), ticker, "context")
    return _apply_context(nodes, ctx_nodes, results)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_tech_subcat(name: str) -> str:
    """Return the technical subcategory label for a node name."""
    if name in _MOMENTUM_TECH:
        return "momentum"
    if name in _TREND_TECH:
        return "trend"
    if name in _VOLUME_TECH:
        return "volume"
    if name in _VOLATILITY_TECH:
        return "volatility"
    return "other"


_BATCH_SIZE = 12

def _call_gemini_batch(
    prompt: str,
    expected_count: int,
    ticker: str,
    batch_label: str,
) -> list[dict[str, Any]]:
    """Send a single batch prompt to Gemini and parse the JSON array response.

    Args:
        prompt:         Full prompt string.
        expected_count: Number of items expected in the response array.
        ticker:         Used for logging only.
        batch_label:    Used for logging ("technical", "fundamental", etc.).

    Returns:
        List of dicts with at minimum {"index": int, "context": str}.
        Returns [] on any failure — callers fall back gracefully.
    """
    try:
        import google.auth
        import google.auth.transport.requests
        from openai import OpenAI

        from backend.config import settings, yaml_cfg

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        client = OpenAI(
            api_key=credentials.token,
            base_url=settings.google_base_url,
        )

        model_id = yaml_cfg.versions.get("llm", {}).get(
            "active", "google/gemini-2.5-pro"
        )

        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=8192,
        )

        raw = response.choices[0].message.content or ""

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            logger.warning(
                "context_generator: %s/%s — LLM returned non-list", ticker, batch_label
            )
            return []

        logger.info(
            "context_generator: %s/%s — %d/%d contexts generated",
            ticker, batch_label, len(parsed), expected_count,
        )
        return parsed

    except json.JSONDecodeError:
        # Try extracting individual JSON objects via regex
        try:
            objects = re.findall(r'\{[^{}]+\}', raw)
            recovered = [json.loads(o) for o in objects if '"context"' in o]
            if recovered:
                logger.info(
                    "context_generator: %s/%s — recovered %d via regex",
                    ticker, batch_label, len(recovered),
                )
                return recovered
        except Exception:
            pass
        logger.warning(
            "context_generator: %s/%s — JSON parse failed, skipping context",
            ticker, batch_label,
        )
        return []

    except Exception as exc:
        logger.warning(
            "context_generator: %s/%s — Gemini call failed: %s",
            ticker, batch_label, exc,
        )
        return []


def _apply_context(
    all_nodes: list[Node],
    target_nodes: list[Node],
    results: list[dict[str, Any]],
) -> list[Node]:
    """Apply Gemini context results back to nodes, return full node list.

    Args:
        all_nodes:    Full list of all nodes (returned unchanged for non-targets).
        target_nodes: The subset that was sent to Gemini (indexed by position).
        results:      List of dicts from Gemini with 'index' and 'context' keys.

    Returns:
        all_nodes with target_nodes updated in-place by node_id.
    """
    if not results:
        return all_nodes

    # Build index → context map
    context_map: dict[int, str] = {}
    for item in results:
        idx = item.get("index")
        ctx = str(item.get("context", "")).strip()
        if isinstance(idx, int) and ctx:
            context_map[idx] = ctx[:200]  # cap at 200 chars

    # Build node_id → new_context map
    node_id_map: dict[str, str] = {}
    for i, node in enumerate(target_nodes):
        if i in context_map:
            node_id_map[node.node_id] = context_map[i]

    # Apply updates
    updated: list[Node] = []
    for node in all_nodes:
        ctx = node_id_map.get(node.node_id)
        if ctx:
            node = node.model_copy(update={"context": ctx})
        updated.append(node)

    return updated
