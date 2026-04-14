"""
ai_service.py — AI stock analysis via OpenRouter → DeepSeek (free tier).

From AI_CONTEXT.md:
  - API: OpenRouter with OpenAI-compatible client
  - Model: deepseek/deepseek-chat-v3-0324:free (zero cost, strong JSON output)
  - Prompt structure: system (SEBI-aware analyst) + user (structured data)
  - Response: strict JSON with 6 keys

Retry strategy:
  - 3 attempts with exponential backoff on rate limit (429) or server errors
  - On total failure → return error dict (frontend shows "Analysis unavailable")

Cache TTL: 21600s (6 hrs) — defined in redis_client.TTL_ANALYSIS
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI, RateLimitError, APIStatusError

from config import settings

logger = logging.getLogger(__name__)

# OpenAI-compatible client pointed at OpenRouter
_client = OpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
)

# ── Prompt builders ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a SEBI-aware stock analyst assistant for Indian retail investors.

Rules:
- Always include a disclaimer that this is NOT financial advice.
- Never promise guaranteed returns or specific price targets.
- Respond ONLY in valid JSON — no markdown, no commentary, just the JSON object.
- Be concise but clear in summaries. Use plain English, avoid jargon.
- Tailor your verdict to the investor's risk level."""


def _build_user_prompt(
    symbol: str,
    risk_level: str,
    fundamentals: dict,
    technicals: dict,
    news_headlines: list[dict],
) -> str:
    """
    Build the structured analysis prompt from AI_CONTEXT.md spec.
    Condenses data to avoid hitting token limits on free models.
    """
    # ── Fundamentals summary ──────────────────────────────────────────────────
    fund_lines = [
        f"Price: ₹{fundamentals.get('price', 'N/A')}",
        f"PE Ratio: {fundamentals.get('pe_ratio', 'N/A')}",
        f"Market Cap: {fundamentals.get('market_cap', 'N/A')} Cr",
        f"Book Value: {fundamentals.get('book_value', 'N/A')}",
        f"52W High/Low: {fundamentals.get('week_52_high', 'N/A')} / {fundamentals.get('week_52_low', 'N/A')}",
        f"Dividend Yield: {fundamentals.get('dividend_yield', 'N/A')}%",
        f"ROCE: {fundamentals.get('roce', 'N/A')}%",
        f"ROE: {fundamentals.get('roe', 'N/A')}%",
    ]
    fund_str = "\n".join(fund_lines)

    # ── Technicals summary ────────────────────────────────────────────────────
    tech_lines = [
        f"RSI(14): {technicals.get('rsi', 'N/A')} → {technicals.get('rsi_signal', 'N/A')}",
        f"MACD: {technicals.get('macd', 'N/A')} → {technicals.get('macd_signal', 'N/A')}",
        f"ADX(14): {technicals.get('adx', 'N/A')} → {technicals.get('adx_signal', 'N/A')}",
        f"EMA 20/50/200: {technicals.get('ema_20', 'N/A')} / {technicals.get('ema_50', 'N/A')} / {technicals.get('ema_200', 'N/A')}",
        f"EMA Signal: {technicals.get('ema_signal', 'N/A')}",
        f"BB: Upper {technicals.get('bb_upper', 'N/A')} / Lower {technicals.get('bb_lower', 'N/A')} → {technicals.get('bb_signal', 'N/A')}",
        f"Overall Technical Signal: {technicals.get('overall_signal', 'N/A')}",
    ]
    tech_str = "\n".join(tech_lines)

    # ── News headlines (top 5 only to save tokens) ────────────────────────────
    headlines = [n.get("title", "") for n in news_headlines[:5] if n.get("title")]
    news_str = "\n".join(f"- {h}" for h in headlines) if headlines else "No recent news available."

    return f"""Analyse {symbol} for a {risk_level} risk investor.

Risk policy (must apply):
- low risk: strict capital protection bias (prefer HOLD/AVOID unless conviction is strong)
- medium risk: balanced risk/reward
- high risk: opportunistic bias allowed but still avoid weak setups

FUNDAMENTALS:
{fund_str}

TECHNICALS:
{tech_str}

RECENT NEWS:
{news_str}

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "fundamentals": {{ "verdict": "Strong|Weak|Neutral", "summary": "2-3 sentences" }},
  "technicals": {{ "verdict": "Bullish|Bearish|Mixed", "summary": "2-3 sentences" }},
  "news": {{ "verdict": "Positive|Negative|Neutral", "summary": "1-2 sentences" }},
  "final_verdict": "BUY|HOLD|AVOID",
  "plain_english": "3-4 sentences explaining in simple terms for a {risk_level} risk investor",
  "risk_match": true|false
}}"""


def _normalize_final_verdict(value: str | None) -> str:
    """Map model output to BUY/HOLD/AVOID with safe fallback."""
    text = (value or "HOLD").strip().upper()
    if text in {"BUY", "HOLD", "AVOID"}:
        return text
    if text in {"SELL", "REDUCE"}:
        return "AVOID"
    return "HOLD"


def _risk_adjusted_verdict(
    risk_level: str,
    fundamentals_verdict: str,
    technicals_verdict: str,
    news_verdict: str,
    model_final: str,
) -> str:
    """
    Apply a light deterministic risk overlay so risk profiles are reflected
    consistently even when model output is conservative.
    """
    score = 0.0

    score += {"STRONG": 1.0, "NEUTRAL": 0.0, "WEAK": -1.0}.get(fundamentals_verdict.upper(), 0.0)
    score += {"BULLISH": 1.0, "MIXED": 0.0, "BEARISH": -1.0}.get(technicals_verdict.upper(), 0.0)
    score += {"POSITIVE": 0.5, "NEUTRAL": 0.0, "NEGATIVE": -0.5}.get(news_verdict.upper(), 0.0)

    if risk_level == "low":
        if score >= 1.75:
            overlay = "BUY"
        elif score >= 0.25:
            overlay = "HOLD"
        else:
            overlay = "AVOID"
    elif risk_level == "high":
        if score >= 0.25:
            overlay = "BUY"
        elif score >= -1.25:
            overlay = "HOLD"
        else:
            overlay = "AVOID"
    else:  # medium
        if score >= 1.0:
            overlay = "BUY"
        elif score >= -0.5:
            overlay = "HOLD"
        else:
            overlay = "AVOID"

    if model_final == "AVOID" and overlay == "BUY":
        return "HOLD"
    if model_final == "BUY" and overlay == "AVOID":
        return "HOLD"
    return overlay


# ── Core AI call ──────────────────────────────────────────────────────────────

def _call_openrouter(symbol: str, user_prompt: str) -> dict:
    """
    Sync call to OpenRouter. Runs in thread pool.
    Retries 3x with backoff on rate limit / server errors.
    Returns parsed dict or raises on total failure.
    """
    last_error = None

    for attempt in range(3):
        try:
            response = _client.chat.completions.create(
                model=settings.openrouter_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
                # response_format not used — not supported by all free models
                # JSON is enforced via explicit prompt instruction instead
            )

            raw = response.choices[0].message.content.strip()
            logger.info(f"OpenRouter response for {symbol}: {len(raw)} chars")

            # Strip markdown fences if model wraps in ```json ... ```
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            return json.loads(raw)

        except RateLimitError as e:
            wait = 2 ** attempt
            logger.warning(f"OpenRouter rate limit (attempt {attempt+1}/3), retrying in {wait}s: {e}")
            time.sleep(wait)
            last_error = e

        except json.JSONDecodeError as e:
            wait = 2 ** attempt
            logger.warning(
                f"OpenRouter returned invalid JSON for {symbol} "
                f"(attempt {attempt+1}/3), retrying in {wait}s: {e}"
            )
            time.sleep(wait)
            last_error = e
            continue

        except APIStatusError as e:
            if e.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(f"OpenRouter server error {e.status_code} (attempt {attempt+1}/3), retrying in {wait}s")
                time.sleep(wait)
                last_error = e
            else:
                raise  # 4xx errors (bad key, wrong model) shouldn't be retried

        except Exception as e:
            logger.error(f"OpenRouter unexpected error for {symbol}: {e}")
            raise

    raise last_error or RuntimeError("OpenRouter call failed after 3 attempts")


# ── Response validation ───────────────────────────────────────────────────────

def _validate_and_enrich(raw: dict, symbol: str, risk_level: str) -> dict:
    """
    Ensure response has expected keys. Fill defaults for missing fields.
    Adds metadata: symbol, risk_level, generated_at.
    """
    def ensure_section(key, default_verdict, default_summary):
        section = raw.get(key, {})
        if not isinstance(section, dict):
            section = {}
        return {
            "verdict": section.get("verdict", default_verdict),
            "summary": section.get("summary", default_summary),
        }

    fundamentals = ensure_section("fundamentals", "Neutral", "Insufficient data for analysis.")
    technicals = ensure_section("technicals", "Mixed", "Insufficient technical data.")
    news = ensure_section("news", "Neutral", "No significant news detected.")

    model_final = _normalize_final_verdict(raw.get("final_verdict"))
    adjusted_final = _risk_adjusted_verdict(
        risk_level=risk_level,
        fundamentals_verdict=fundamentals["verdict"],
        technicals_verdict=technicals["verdict"],
        news_verdict=news["verdict"],
        model_final=model_final,
    )

    plain_english = raw.get("plain_english", "Unable to generate analysis at this time.")
    plain_english = str(plain_english).strip() if plain_english is not None else ""
    if not plain_english:
        plain_english = "Unable to generate analysis at this time."

    # Normalize common unicode dash variants for consistent plain-text output.
    plain_english = plain_english.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")

    prefix = f"For a {risk_level} risk investor, "
    low_plain = plain_english.lower()
    if not (
        low_plain.startswith(prefix.lower())
        or low_plain.startswith(f"for a {risk_level}-risk investor")
        or low_plain.startswith(f"for a {risk_level} risk profile")
    ):
        plain_english = prefix + plain_english[0].lower() + plain_english[1:] if len(plain_english) > 1 else prefix + plain_english

    # De-duplicate intros like:
    # "For a low risk investor, for a low-risk investor, ..."
    dup_intro = re.compile(
        rf"^(For a {risk_level} risk investor, )for a {risk_level}-risk investor, ",
        re.IGNORECASE,
    )
    plain_english = dup_intro.sub(r"\1", plain_english)

    risk_match = raw.get("risk_match")
    if not isinstance(risk_match, bool):
        risk_match = adjusted_final != "AVOID"

    return {
        "symbol":          symbol.upper(),
        "risk_level":      risk_level,
        "fundamentals":    fundamentals,
        "technicals":      technicals,
        "news":            news,
        "final_verdict":   adjusted_final,
        "plain_english":   plain_english,
        "risk_match":      risk_match,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "disclaimer":      (
            "This analysis is AI-generated and for informational purposes only. "
            "It is NOT financial advice. Please consult a SEBI-registered advisor "
            "before making investment decisions."
        ),
    }


# ── Public async API ──────────────────────────────────────────────────────────

async def analyse(
    symbol: str,
    fundamentals: dict,
    technicals: dict,
    news: list[dict],
    risk_level: str = "medium",
) -> dict:
    """
    Async entry point — runs blocking OpenRouter call in thread pool.

    Args:
        symbol:       NSE stock symbol (e.g. "RELIANCE")
        fundamentals: merged dict from yfinance + screener ratios
        technicals:   dict from technicals_service.calculate_technicals()
        news:         list from news_service.get_news()
        risk_level:   "low" | "medium" | "high"

    Returns:
        Structured analysis dict. Never raises — returns error dict on failure.
    """
    symbol     = symbol.upper().strip()
    risk_level = risk_level.lower().strip()

    if risk_level not in ("low", "medium", "high"):
        risk_level = "medium"

    try:
        user_prompt = _build_user_prompt(symbol, risk_level, fundamentals, technicals, news)
        loop = asyncio.get_event_loop()
        raw  = await loop.run_in_executor(None, _call_openrouter, symbol, user_prompt)
        return _validate_and_enrich(raw, symbol, risk_level)

    except Exception as e:
        logger.error(f"AI analysis failed for {symbol}: {e}")
        return {
            "symbol":       symbol,
            "risk_level":   risk_level,
            "error":        str(e),
            "final_verdict": "HOLD",
            "plain_english": "AI analysis is currently unavailable. Please try again later.",
            "fundamentals": {"verdict": "Unknown", "summary": "Analysis failed."},
            "technicals":   {"verdict": "Unknown", "summary": "Analysis failed."},
            "news":         {"verdict": "Unknown", "summary": "Analysis failed."},
            "risk_match":   False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer":   "This is NOT financial advice.",
        }
