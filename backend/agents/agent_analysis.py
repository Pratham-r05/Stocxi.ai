"""
agent_analysis.py — LLM Analysis Agent.

Contract (AGENTS.md §3):
  Input:  list[Node] (validated, sanitized, anonymized) + FetchRequest
  Output: AnalysisDraft — every claim tagged with node_ids

Rules:
  - Uses pinned model id, temp=0, pinned prompt version (all from config/versions.yaml)
  - Renders prompt_template.jinja with Jinja2 — no runtime prompt mutation
  - Calls Google Gemini via OpenAI-compatible client
  - On model output failure: retry once, then raise (orchestrator owns fallback)
  - Never does de-anonymization — that is the Formatter's job
  - Never raises for data reasons — only raises on LLM/config failures
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

from schemas.messages import (
    AnalysisDraft,
    AgreementLink,
    Claim,
    ContradictionLink,
    FetchRequest,
    Verdict,
)
from schemas.node import Node, NodeCategory
from analysis.output_instructions import load_shorthand_book, load_horizon_instructions

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

_CONFIG_DIR = next((p / "config" for p in Path(__file__).resolve().parents if (p / "config").exists()), Path(__file__).resolve().parent.parent.parent / "config")
_VERSIONS      = yaml.safe_load((_CONFIG_DIR / "versions.yaml").read_text())
_PROFILES      = yaml.safe_load((_CONFIG_DIR / "profiles.yaml").read_text())

_MODEL_ID      = _VERSIONS["llm"]["active"]
_GOOGLE_MODEL  = _MODEL_ID
_TEMPERATURE   = float(_VERSIONS["llm"]["temperature"])
assert _TEMPERATURE == 0.0, f"LLM temperature must be 0 for deterministic output, got {_TEMPERATURE}"
_MAX_TOKENS    = int(_VERSIONS["llm"]["max_tokens"])
_PROMPT_VER    = _VERSIONS["prompt_version"]
_WEIGHT_VER    = _VERSIONS["weight_version"]

# Jinja2 environment pointing at backend/analysis/
_ANALYSIS_DIR  = Path(__file__).parents[1] / "analysis"
_JINJA_ENV     = Environment(
    loader=FileSystemLoader(str(_ANALYSIS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)
_TEMPLATE      = _JINJA_ENV.get_template("prompt_template.jinja")


def _get_llm_client():
    """Return OpenAI-compatible client using Vertex AI ADC credentials."""
    import google.auth
    import google.auth.transport.requests
    from openai import OpenAI
    from config import settings

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return OpenAI(
        api_key=credentials.token,
        base_url=settings.google_base_url,
    )


# ── Category weight lookup ─────────────────────────────────────────────────────

def _category_weights(horizon: str, risk: str) -> dict[str, float]:
    """
    Return the category mix for the given horizon, adjusted for risk.
    Values from config/profiles.yaml.
    """
    mix = dict(_PROFILES["category_mix"].get(horizon, _PROFILES["category_mix"]["long"]))
    adjustments = _PROFILES.get("risk_adjustments", {}).get(risk, {})

    # Risk adjustments are multipliers on specific indicator sub-classes, not categories.
    # For the prompt-level weight we expose the raw category mix — indicator-level
    # risk weighting happens inside each data agent at node creation time.
    return {
        "technical":    mix.get("technical", 0.20),
        "fundamental":  mix.get("fundamental", 0.50),
        "news":         mix.get("news", 0.10),
        "announcement": mix.get("announcement", 0.20),
    }


# ── Prompt rendering ───────────────────────────────────────────────────────────

def _split_by_category(nodes: list[Node]) -> dict[str, list[Node]]:
    buckets: dict[str, list[Node]] = {
        "technical": [], "fundamental": [], "news": [],
        "announcement": [], "context": [],
    }
    for n in nodes:
        key = n.category.value
        if key in buckets:
            buckets[key].append(n)
    return buckets


def _render_prompt(nodes: list[Node], request: FetchRequest, kg_serialization: str = "") -> str:
    horizon = request.profile.horizon.value
    risk    = request.profile.risk.value
    cats    = _split_by_category(nodes)
    weights = _category_weights(horizon, risk)

    # Load output instruction files (cached after first read)
    shorthand_book = load_shorthand_book()
    horizon_instructions = load_horizon_instructions(horizon)

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
        shorthand_book=shorthand_book,
        horizon_instructions=horizon_instructions,
    )


# ── LLM call ───────────────────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    """Remove ```json ... ``` fences some models add despite instructions."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw = "\n".join(inner)
    return raw.strip()


def _repair_truncated_json(raw: str) -> dict[str, Any] | None:
    """Best-effort repair of a JSON string truncated mid-stream (token limit hit).

    Strategy:
      1. Find the last position where the top-level object could still be valid.
      2. Close any unclosed arrays and objects to produce valid JSON.
      3. Return parsed dict, or None if repair fails.
    """
    if not raw.strip().startswith("{"):
        return None
    # Close unclosed structures by tracking bracket depth
    stack: list[str] = []
    in_string = False
    escape_next = False
    last_good_idx = 0
    for i, ch in enumerate(raw):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
                if not stack:
                    last_good_idx = i
    # Truncate to last fully-closed top-level object
    if last_good_idx > 0:
        try:
            return json.loads(raw[: last_good_idx + 1])
        except json.JSONDecodeError:
            pass
    # Fallback: append closing brackets in reverse stack order
    closing = "".join(reversed(stack))
    # Strip trailing comma before closing
    trimmed = raw.rstrip().rstrip(",")
    candidate = trimmed + closing
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _call_llm(prompt: str) -> tuple[dict[str, Any], str]:
    """Synchronous LLM call. Returns (parsed_dict, raw_response_str).
    Retries once on JSON parse failure. Re-raises all other exceptions immediately."""
    client = _get_llm_client()

    model = _MODEL_ID

    system_msg = (
        "You are a strict financial data analysis engine. "
        "Output ONLY a single valid JSON object. No markdown, no explanation."
    )

    last_raw = ""
    for attempt in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": prompt},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )
        last_raw = response.choices[0].message.content or ""
        finish   = response.choices[0].finish_reason or ""
        logger.info("agent_analysis: LLM response %d chars finish=%s (attempt %d)",
                    len(last_raw), finish, attempt + 1)
        cleaned = _strip_fences(last_raw)
        try:
            return json.loads(cleaned), last_raw
        except json.JSONDecodeError as e:
            repaired = _repair_truncated_json(cleaned)
            if repaired is not None:
                logger.warning("agent_analysis: JSON repaired (truncated response) — finish=%s", finish)
                return repaired, last_raw
            if attempt == 0:
                logger.warning("agent_analysis: JSON parse failed, retrying: %s", e)
                time.sleep(1)
                continue
            logger.error("agent_analysis: JSON parse failed after retry: %s", e)
            raise

    raise RuntimeError("LLM call exhausted retries")  # unreachable but satisfies type checkers


# ── Response parsing ───────────────────────────────────────────────────────────


def _parse_claim(raw: dict) -> Claim:
    return Claim(
        text=str(raw.get("text", "")),
        node_ids=[str(x) for x in raw.get("node_ids", [])],
        is_positive=raw.get("is_positive"),
    )


def _parse_verdict(raw: dict, category: str) -> Verdict:
    direction = raw.get("direction", "neutral")
    if direction not in ("bullish", "bearish", "neutral", "mixed"):
        direction = "neutral"
    return Verdict(
        category=category,
        direction=direction,
        summary=str(raw.get("summary", "")),
        supporting_node_ids=[str(x) for x in raw.get("supporting_node_ids", [])],
        confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.5)))),
    )


def _parse_draft(raw: dict) -> AnalysisDraft:
    """Parse LLM dict into AnalysisDraft."""
    verdicts_raw = raw.get("verdicts", {})
    verdicts: dict[str, Verdict] = {}
    for cat in ("technical", "fundamental", "news", "announcement"):
        v = verdicts_raw.get(cat, {})
        verdicts[cat] = _parse_verdict(v if isinstance(v, dict) else {}, cat)

    overall = raw.get("overall_signal", "neutral")
    if overall not in ("bullish", "bearish", "neutral", "mixed"):
        overall = "neutral"

    raw_conf = raw.get("raw_confidence", 0.5)
    try:
        raw_conf = max(0.0, min(1.0, float(raw_conf)))
    except (TypeError, ValueError):
        raw_conf = 0.5

    def parse_claims(key: str) -> list[Claim]:
        items = raw.get(key, [])
        if not isinstance(items, list):
            return []
        return [_parse_claim(c) for c in items if isinstance(c, dict) and c.get("text")]

    agreements = []
    for ag in (raw.get("agreements") or []):
        if not isinstance(ag, dict):
            continue
        agreements.append(AgreementLink(
            node_id_a=str(ag.get("node_id_a", "")),
            node_id_b=str(ag.get("node_id_b", "")),
            reason=str(ag.get("reason", "")),
        ))

    contradictions = []
    for ct in (raw.get("contradictions") or []):
        if not isinstance(ct, dict):
            continue
        tier = ct.get("tier_applied", 6)
        try:
            tier = max(1, min(6, int(tier)))
        except (TypeError, ValueError):
            tier = 6
        contradictions.append(ContradictionLink(
            node_id_positive=str(ct.get("node_id_positive", "")),
            node_id_negative=str(ct.get("node_id_negative", "")),
            resolution=str(ct.get("resolution", "")),
            tier_applied=tier,
        ))

    return AnalysisDraft(
        what_data_suggests=parse_claims("what_data_suggests"),
        signals_in_favor=parse_claims("signals_in_favor"),
        signals_against=parse_claims("signals_against"),
        verdicts=verdicts,
        agreements=agreements,
        contradictions=contradictions,
        overall_signal=overall,
        raw_confidence=raw_conf,
        model_id=_MODEL_ID,
        prompt_version=_PROMPT_VER,
        weight_version=_WEIGHT_VER,
    )


# ── Public entry point ─────────────────────────────────────────────────────────

async def run(
    nodes: list[Node], request: FetchRequest, kg_serialization: str = ""
) -> tuple[AnalysisDraft, str, str]:
    """
    Render prompt, call LLM, parse response into AnalysisDraft.

    Args:
        nodes:   Validated, sanitized, anonymized nodes from all data agents.
                 Must all have sanitized=True before this is called.
        request: Original FetchRequest (used for profile weights and tracing).

    Returns:
        (AnalysisDraft, rendered_prompt, raw_llm_response) — prompt and raw
        response are returned so the orchestrator can write them to the audit log.

    Raises:
        ValueError:  if any node has sanitized=False.
        RuntimeError: if LLM call fails after retry or JSON is unrecoverable.
    """
    unsanitized = [n.node_id for n in nodes if not n.sanitized]
    if unsanitized:
        raise ValueError(
            f"agent_analysis: {len(unsanitized)} unsanitized nodes reached the LLM layer — "
            f"first: {unsanitized[0]}"
        )

    prompt = _render_prompt(nodes, request, kg_serialization)
    logger.info(
        "agent_analysis: %s — prompt %d chars, %d nodes, model=%s",
        request.stock, len(prompt), len(nodes), _MODEL_ID,
    )

    loop = asyncio.get_running_loop()
    raw_dict, raw_str = await loop.run_in_executor(None, _call_llm, prompt)
    draft = _parse_draft(raw_dict)

    logger.info(
        "agent_analysis: %s — draft: overall=%s conf=%.2f "
        "wds=%d favor=%d against=%d agreements=%d contradictions=%d",
        request.stock,
        draft.overall_signal,
        draft.raw_confidence,
        len(draft.what_data_suggests),
        len(draft.signals_in_favor),
        len(draft.signals_against),
        len(draft.agreements),
        len(draft.contradictions),
    )
    return draft, prompt, raw_str
