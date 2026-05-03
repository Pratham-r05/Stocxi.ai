"""
gemini_analysis.py — Gemini knowledge graph analysis engine.

Loads horizon instruction files, serializes the knowledge graph into a
structured prompt, calls the Gemini API, and returns the raw Markdown report.

Flow:
    parse_md(symbol) → nodes
    build_kg_summary(nodes) → compact JSON for the prompt
    load_horizon_instructions(horizon) → instruction text
    call_gemini(prompt) → Markdown report string
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types as genai_types

# ── Project root resolution ───────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parents[2]          # backend/analysis/ → stocxi/
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import settings, yaml_cfg       # type: ignore
from build_knowledge_graph import parse_md, ParsedNode  # type: ignore

logger = logging.getLogger(__name__)

# ── Types ─────────────────────────────────────────────────────────────────────

Horizon   = Literal["short", "medium", "long"]
UserLevel = Literal["beginner", "medium", "pro"]

HORIZON_FILE: dict[str, str] = {
    "short":  "docs/output/01_short_term_output.md",
    "medium": "docs/output/02_medium_term_output.md",
    "long":   "docs/output/03_long_term_output.md",
}

STANDARD_SECTION_HEADINGS = [
    "About",
    "Fundamentals",
    "Technical Indicators",
    "Announcements",
    "News",
    "Financial Statements",
    "Overall Summary & AI Opinion",
]

HEADING_ALIASES = {
    "about the company": "About",
    "company overview": "About",
    "business overview": "About",
    "technical analysis": "Technical Indicators",
    "technicals": "Technical Indicators",
    "financials": "Financial Statements",
    "financial statement": "Financial Statements",
    "financial statements": "Financial Statements",
    "ai opinion and overall summary": "Overall Summary & AI Opinion",
    "overall summary and ai opinion": "Overall Summary & AI Opinion",
    "overall summary": "Overall Summary & AI Opinion",
    "ai opinion": "Overall Summary & AI Opinion",
}

# Gemini model — pinned for determinism (read from versions.yaml at runtime)
_MODEL_ID = yaml_cfg.versions.get("llm", {}).get("active", "gemini-2.5-flash").replace("google/", "")

_SYSTEM_INSTRUCTION = """You are a senior equity research analyst at a top-tier Indian institutional brokerage with 15 years of experience covering NSE/BSE-listed stocks across all sectors. Your speciality is translating raw financial data and market signals into clear, evidence-backed research notes that help investors of all levels understand what the numbers actually mean.

Your standards:
- Every number you write must come directly from the knowledge graph data provided. Never invent or estimate figures.
- You write like a professional analyst: precise, structured, and substantive. No vague language, no filler phrases.
- For every metric, you state the value AND explain its implication for the specific investment horizon. A number without context is useless.
- You cover P&L, Balance Sheet, and Cash Flow in full — not summaries. Multi-year tables with actual figures are your baseline standard.
- You compare the latest year against prior years to show the direction of the business. Growth, stagnation, and deterioration each tell a different story.
- You explain technical indicators as price behaviour signals, not dictionary definitions.
- You treat news and announcements as catalysts — classify their likely magnitude and timing impact clearly.
- You never leave a table cell as N/A if the data is present in the knowledge graph. Multi-year values appear as pipe-separated strings in the `value` field — parse all of them.
- You do not use emoji or coloured symbols anywhere. Your signal language is plain English: Positive, Negative, Neutral, Improving, Deteriorating, Strong, Weak.
- You do not include charts or chart code. All visual trends are described in text and tables.
- You are NOT a SEBI-registered advisor. You never say buy, sell, recommend, or advise. You describe what the data has historically implied.
- You write comprehensive reports. Short analysis is incomplete analysis.
- You always use the exact seven Markdown H2 headings requested. No alternate headings."""

# ── Gemini client init ────────────────────────────────────────────────────────

_client = genai.Client(api_key=settings.google_api_key)


# ── Instruction loader ────────────────────────────────────────────────────────

_instruction_cache: dict[str, str] = {}


def load_horizon_instructions(horizon: Horizon) -> str:
    """Load and cache horizon instruction file. Raises FileNotFoundError if missing."""
    if horizon in _instruction_cache:
        return _instruction_cache[horizon]

    fname = HORIZON_FILE[horizon]
    path  = _PROJECT_ROOT / fname
    if not path.exists():
        raise FileNotFoundError(
            f"Horizon instruction file not found: {path}\n"
            f"Expected one of: {list(HORIZON_FILE.values())}"
        )

    text = path.read_text(encoding="utf-8")
    _instruction_cache[horizon] = text
    return text


# ── Knowledge graph serializer ────────────────────────────────────────────────

def _signal_value(signal: str) -> float:
    """Convert signal string to numeric for weighted scoring."""
    return {"positive": 1.0, "negative": -1.0, "neutral": 0.0, "mixed": 0.3}.get(signal, 0.0)


CATEGORY_WEIGHT: dict[str, float] = {
    "fundamental":    1.5,
    "technical":      1.2,
    "financial":      0.8,
    "announcement":   0.6,
    "news":           0.5,
    "market_context": 1.0,
}


def build_kg_summary(
    meta: dict[str, str],
    nodes: list[ParsedNode],
) -> dict:
    """
    Serialize knowledge graph nodes into a compact dict for the Gemini prompt.

    Returns a dict with:
      - meta: stock frontmatter
      - signal_distribution: counts by signal type
      - weighted_score: sum(weight * signal_value) / sum(weights), range [-1, +1]
      - categories: {category_name: [node dicts]}
    """
    by_cat: dict[str, list[dict]] = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for node in nodes:
        w = CATEGORY_WEIGHT.get(node.category, 1.0)
        sv = _signal_value(node.signal)
        total_weight += w
        weighted_sum += w * sv

        entry = {
            "label":      node.label,
            "signal":     node.signal,
            "value":      node.value_text,
            "summary":    node.summary,
            "analysis":   node.context,
            "relates_to": node.relates,
        }
        if node.group:
            entry["group"] = node.group

        by_cat.setdefault(node.category, []).append(entry)

    sig_counts = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    for n in nodes:
        sig_counts[n.signal] = sig_counts.get(n.signal, 0) + 1

    return {
        "meta": meta,
        "signal_distribution": sig_counts,
        "weighted_score": round(weighted_sum / total_weight, 3) if total_weight else 0.0,
        "categories": by_cat,
    }


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(
    kg_summary: dict,
    horizon: Horizon,
    user_level: UserLevel,
    horizon_instructions: str,
    kg_link: str = "",
) -> str:
    """
    Assemble the full prompt sent to Gemini.

    Structure:
        1. System instructions (horizon file)
        2. Invocation parameters (horizon, user_level)
        3. Knowledge graph data (JSON)
        4. KG link for the report footer
    """
    kg_json = json.dumps(kg_summary, ensure_ascii=False, indent=2)

    return f"""{horizon_instructions}

---

## INVOCATION PARAMETERS

horizon:    {horizon}
user_level: {user_level}
kg_link:    {kg_link or "[KG_LINK_PLACEHOLDER]"}

Produce the report format for user_level="{user_level}" exactly as defined above.
Replace [KG_LINK_PLACEHOLDER] with the kg_link value above.

---

## MANDATORY OUTPUT SKELETON

Use these exact Markdown headings, in this order, for every horizon and user level:

1. ## About
2. ## Fundamentals
3. ## Technical Indicators
4. ## Announcements
5. ## News
6. ## Financial Statements
7. ## Overall Summary & AI Opinion

Rules:
- Do not add, rename, reorder, or skip these H2 headings.
- Put all horizon-specific content inside these same sections.
- Do not create different section structures for short, medium, or long horizon.
- Start the report with one H1 title, then the seven H2 sections.
- If a section has no source data, write one concise sentence saying data is unavailable.
- Format numeric comparisons as Markdown tables, not inline pipe text.
- Every table must include the separator row, for example: | A | B | then |---|---|.
- In Financial Statements, include P&L, balance sheet, and cash flow when supplied.
- After each Financial Statements table, write 2-3 sentences interpreting the numbers.
- Even for short-term analysis, explain the latest quarter and cash-flow quality.

Keep the horizon-specific focus and depth requirements from the instructions above.

---

## KNOWLEDGE GRAPH DATA (JSON)

The following JSON contains all nodes extracted from the stock's data file.
Use this as your sole data source. Do not invent numbers not present here.

```json
{kg_json}
```

---

Begin the report now. Start directly with the company name / header line.
"""


def standardize_report_markdown(md_text: str) -> str:
    """Force the public report into the fixed seven-section Markdown contract."""
    text = md_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    intro_lines: list[str] = []
    sections: dict[str, list[str]] = {heading: [] for heading in STANDARD_SECTION_HEADINGS}
    current: str | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip().strip("#").strip()
            canonical = HEADING_ALIASES.get(heading.lower(), heading)
            if canonical in STANDARD_SECTION_HEADINGS:
                current = canonical
                continue
        if current:
            sections[current].append(raw_line)
        else:
            intro_lines.append(raw_line)

    rebuilt: list[str] = [line for line in intro_lines if line.strip()]
    for heading in STANDARD_SECTION_HEADINGS:
        body = "\n".join(sections[heading]).strip()
        rebuilt.extend(["", f"## {heading}"])
        if body:
            rebuilt.append(body)
        else:
            rebuilt.append("Data unavailable in the supplied nodes.")
    return "\n".join(rebuilt).strip()


# ── Main analysis function ────────────────────────────────────────────────────

def run_analysis(
    symbol: str,
    horizon: Horizon,
    user_level: UserLevel,
    kg_link: str = "",
) -> str:
    """
    Run end-to-end Gemini analysis for a stock symbol.

    Args:
        symbol:     NSE stock symbol (e.g. "RELIANCE")
        horizon:    "short" | "medium" | "long"
        user_level: "beginner" | "medium" | "pro"
        kg_link:    Path or URL to the generated knowledge graph HTML (optional)

    Returns:
        Markdown string — the complete analysis report.

    Raises:
        FileNotFoundError: if data/*.md or horizon instruction file is missing.
        google.api_core.exceptions.GoogleAPIError: on Gemini API failure.
    """
    # 1. Parse stock data
    data_path = _PROJECT_ROOT / "data" / f"{symbol.upper()}_data.md"
    if not data_path.exists():
        raise FileNotFoundError(
            f"Stock data file not found: {data_path}\n"
            f"Run: python fetch_phase1_data.py {symbol.upper()}"
        )

    logger.info("[gemini_analysis] Parsing %s", data_path.name)
    meta, nodes = parse_md(data_path)
    logger.info("[gemini_analysis] %d nodes parsed", len(nodes))

    # 2. Build KG summary
    kg_summary = build_kg_summary(meta, nodes)

    # 3. Load instructions
    instructions = load_horizon_instructions(horizon)

    # 4. Build prompt
    prompt = build_prompt(kg_summary, horizon, user_level, instructions, kg_link)

    # 5. Call Gemini
    logger.info(
        "[gemini_analysis] Calling %s | horizon=%s | level=%s | nodes=%d",
        _MODEL_ID, horizon, user_level, len(nodes),
    )

    response = _client.models.generate_content(
        model=_MODEL_ID,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.0,
            candidate_count=1,
            max_output_tokens=32768,
        ),
    )
    report = standardize_report_markdown(response.text or "")

    logger.info("[gemini_analysis] Report generated — %d chars", len(report))
    return report
