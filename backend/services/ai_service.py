"""
ai_service.py — AI stock analysis via Google Gemini API.

From AI_CONTEXT.md:
  - API: Google Gemini with OpenAI-compatible client
  - Model: models/gemini-3-pro-preview
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


def _get_openai_compatible_client():
    """Return an OpenAI-compatible Gemini client."""
    if settings.google_api_key:
        return OpenAI(
            api_key=settings.google_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return OpenAI(
        api_key=credentials.token,
        base_url=settings.google_base_url,
    )


_client = None


def _active_model_id() -> str:
    if settings.google_api_key:
        return settings.google_model.removeprefix("google/")
    return settings.google_model

def _get_client():
    global _client
    if _client is None:
        _client = _get_openai_compatible_client()
    return _client

# ── Prompt builders ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a SEBI-aware stock analyst assistant for Indian retail investors.

Rules:
- Always include a disclaimer that this is NOT financial advice.
- Never promise guaranteed returns or specific price targets.
- Respond ONLY in valid JSON — no markdown, no commentary, just the JSON object.
- Be concise but clear in summaries. Use plain English, avoid jargon.
- Tailor your verdict to the investor's risk level."""

_REPORT_SYSTEM_PROMPT = """You are a SEBI-aware Indian equity analyst writing concise one-page stock reports.

Rules:
- Return ONLY valid JSON matching the requested schema.
- No markdown, no backticks, no extra commentary.
- Be factual, balanced, and explicit about uncertainty.
- Never guarantee returns or suggest certainty.
- Always keep language aligned with the selected audience tier.
"""


def _build_user_prompt(
    symbol: str,
    risk_level: str,
    fundamentals: dict,
    technicals: dict,
    news_headlines: list[dict],
    social_sentiment: dict | None = None,
    analysis_snapshot: dict | None = None,
) -> str:
    """
    Build the structured analysis prompt from AI_CONTEXT.md spec.
    Condenses data to avoid hitting token limits on free models.
    """
    # ── Fundamentals summary ──────────────────────────────────────────────────
    fund_lines = [
        f"Price: ₹{fundamentals.get('price', 'N/A')}",
        f"Exchange: {fundamentals.get('exchange', 'N/A')}",
        f"Sector / Industry: {fundamentals.get('sector', 'N/A')} / {fundamentals.get('industry', 'N/A')}",
        f"PE Ratio: {fundamentals.get('pe_ratio', 'N/A')}",
        f"PB Ratio: {fundamentals.get('pb_ratio', 'N/A')}",
        f"EPS: {fundamentals.get('eps', 'N/A')}",
        f"Market Cap (₹): {fundamentals.get('market_cap', 'N/A')}",
        f"Book Value: {fundamentals.get('book_value', 'N/A')}",
        f"Volume: {fundamentals.get('volume', 'N/A')}",
        f"Day Open/High/Low: {fundamentals.get('open', 'N/A')} / {fundamentals.get('day_high', 'N/A')} / {fundamentals.get('day_low', 'N/A')}",
        f"52W High/Low: {fundamentals.get('week_52_high', 'N/A')} / {fundamentals.get('week_52_low', 'N/A')}",
        f"Dividend Yield: {fundamentals.get('dividend_yield', 'N/A')}%",
        f"ROCE: {fundamentals.get('roce', 'N/A')}%",
        f"ROE: {fundamentals.get('roe', 'N/A')}%",
        f"Beta: {fundamentals.get('beta', 'N/A')}",
        f"1D Change %: {fundamentals.get('change_percent', 'N/A')}",
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

    # ── Announcement highlights ──────────────────────────────────────────────
    announcement_lines = []
    if isinstance(analysis_snapshot, dict):
        for item in (analysis_snapshot.get("important_announcements") or [])[:5]:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject") or "").strip()
            if not subject:
                continue
            category = item.get("category") or ""
            date = item.get("date") or ""
            announcement_lines.append(f"- {subject} | {category} | {date}")
    announcement_str = "\n".join(announcement_lines) if announcement_lines else "No recent important announcements available."

    # ── Structured stock snapshot from all page sections ─────────────────────
    snapshot_json = "{}"
    if isinstance(analysis_snapshot, dict):
        compact_snapshot = {
            "company_profile": analysis_snapshot.get("company_profile"),
            "key_indicators": analysis_snapshot.get("key_indicators"),
            "volume_exchange_price_context": analysis_snapshot.get("volume_exchange_price_context"),
            "technical_indicators": {
                "rsi": (analysis_snapshot.get("technical_indicators") or {}).get("rsi"),
                "macd": (analysis_snapshot.get("technical_indicators") or {}).get("macd"),
                "adx": (analysis_snapshot.get("technical_indicators") or {}).get("adx"),
                "ema_signal": (analysis_snapshot.get("technical_indicators") or {}).get("ema_signal"),
                "bb_signal": (analysis_snapshot.get("technical_indicators") or {}).get("bb_signal"),
                "overall_signal": (analysis_snapshot.get("technical_indicators") or {}).get("overall_signal"),
            },
            "important_news": (analysis_snapshot.get("important_news") or [])[:5],
            "important_announcements": (analysis_snapshot.get("important_announcements") or [])[:5],
            "financial_statement_snapshot": analysis_snapshot.get("financial_statement_snapshot"),
        }
        snapshot_json = json.dumps(compact_snapshot, ensure_ascii=False, indent=2)

    # ── Social sentiment block (optional) ────────────────────────────────────
    social_str = ""
    social_json = ""
    if social_sentiment:
        reddit  = social_sentiment.get("reddit", {})
        twitter = social_sentiment.get("twitter", {})
        social_str = f"""

SOCIAL SENTIMENT (last 7 days):
Reddit: {reddit.get('sentiment', 'Neutral')} ({reddit.get('signal', 'HOLD')}) — {reddit.get('summary', 'No data.')}
Twitter/X: {twitter.get('sentiment', 'Neutral')} ({twitter.get('signal', 'HOLD')}) — {twitter.get('summary', 'No data.')}"""

    social_json = '  "social": { "verdict": "Positive|Negative|Neutral", "summary": "1-2 sentences" },\n'

    return f"""Analyse {symbol} for a {risk_level} risk investor.

Risk policy (must apply):
- low risk: strict capital protection bias (prefer HOLD/AVOID unless conviction is strong)
- medium risk: balanced risk/reward
- high risk: opportunistic bias allowed but still avoid weak setups

Quality policy (must apply):
- Use all provided sections: key indicators, technical indicators, price movement, volume context, important news, important announcements, and financial snapshot.
- If any section has missing data, explicitly say "data unavailable" for that part instead of guessing.
- Ensure verdict consistency: the plain_english recommendation must align with final_verdict.
- Mention one concrete price/volume movement point and one concrete news/announcement cue in plain_english.

FUNDAMENTALS:
{fund_str}

TECHNICALS:
{tech_str}

RECENT NEWS:
{news_str}

IMPORTANT ANNOUNCEMENTS:
{announcement_str}{social_str}

STRUCTURED STOCK SNAPSHOT (authoritative):
{snapshot_json}

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "fundamentals": {{ "verdict": "Strong|Weak|Neutral", "summary": "2-3 sentences" }},
  "technicals": {{ "verdict": "Bullish|Bearish|Mixed", "summary": "2-3 sentences" }},
  "news": {{ "verdict": "Positive|Negative|Neutral", "summary": "1-2 sentences" }},
{social_json}  
  "final_verdict": "BUY|HOLD|AVOID",
    "plain_english": "4-6 sentences in plain English for a {risk_level} risk investor; include volume/price movement and one headline/announcement cue",
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


def _normalize_report_verdict(value: str | None) -> str:
    """Normalize report verdict labels to BUY/HOLD/AVOID (SEBI-compliant — no SELL)."""
    text = (value or "HOLD").strip().upper()
    if text in {"BUY", "HOLD", "AVOID"}:
        return text
    if text in {"SELL", "REDUCE"}:
        return "AVOID"  # SEBI Rule 12: never write "SELL" in user-facing output
    return "HOLD"


def _build_report_user_prompt(
    *,
    symbol: str,
    company_name: str,
    tier: str,
    risk_level: str,
    fundamentals: dict,
    technicals: dict,
    news: list[dict],
    announcements: list[dict],
    analysis_snapshot: dict | None,
    ai_analysis: dict | None,
) -> str:
    """Build report-generation prompt with tiered tone and full stock context."""
    tier_instructions = {
        "orbiter": (
            "Audience: beginner investor. Use plain and friendly language. "
            "Avoid jargon unless explained in simple words. Keep recommendations direct and practical."
        ),
        "stellar": (
            "Audience: intermediate investor. Use moderate technical detail with clear interpretation. "
            "Balance readability with depth."
        ),
        "apex": (
            "Audience: professional/advanced investor. Use technical terminology and market-structure language. "
            "Assume strong finance literacy."
        ),
    }
    tier_instruction = tier_instructions.get(tier, tier_instructions["stellar"])

    compact_news = []
    for item in news[:4]:
        if isinstance(item, dict) and item.get("title"):
            compact_news.append(
                {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "published": item.get("published"),
                }
            )

    compact_announcements = []
    for item in announcements[:4]:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject") or item.get("title")
        if subject:
            compact_announcements.append(
                {
                    "subject": subject,
                    "category": item.get("category"),
                    "date": item.get("date"),
                }
            )

    prior_ai = {
        "final_verdict": (ai_analysis or {}).get("final_verdict"),
        "plain_english": (ai_analysis or {}).get("plain_english"),
        "fundamentals": (ai_analysis or {}).get("fundamentals"),
        "technicals": (ai_analysis or {}).get("technicals"),
        "news": (ai_analysis or {}).get("news"),
    }

    data_blob = {
        "symbol": symbol,
        "company_name": company_name,
        "risk_level": risk_level,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "news": compact_news,
        "announcements": compact_announcements,
        "analysis_snapshot": analysis_snapshot or {},
        "prior_ai_analysis": prior_ai,
    }

    data_json = json.dumps(data_blob, ensure_ascii=False, indent=2)

    return f"""Create a one-page stock report.

Audience tier: {tier.upper()}
{tier_instruction}

Output policy:
- Integrate all key sources: key indicators, technical indicators, AI analysis context, announcements, news, and financial snapshot (quarterly/annual/balance sheet/cash flow/shareholding).
- Mention data limitations when present.
- Keep it concise enough for a one-page PDF.
- Verdict must be one of BUY, HOLD, AVOID.

Return ONLY this JSON shape:
{{
  "report_title": "string (max 80 chars)",
  "verdict": "BUY|HOLD|AVOID",
  "confidence": "High|Medium|Low",
  "investor_fit": "one sentence (max 140 chars)",
  "executive_summary": "one paragraph (max 420 chars)",
  "thesis_points": ["3-4 bullets, each max 170 chars"],
  "technical_view": "max 200 chars",
  "fundamental_view": "max 200 chars",
  "news_announcements_view": "max 200 chars",
  "financial_health_view": "max 220 chars",
  "risk_flags": ["3-4 bullets, each max 170 chars"],
  "action_plan": ["3 bullets, each max 160 chars"]
}}

Data:
{data_json}
"""


def _validate_report_payload(
    raw: dict[str, Any],
    *,
    symbol: str,
    company_name: str,
    tier: str,
    ai_analysis: dict | None,
) -> dict[str, Any]:
    """Validate and normalize AI report payload shape and defaults."""
    if not isinstance(raw, dict):
        raw = {}

    def as_text(key: str, default: str, max_chars: int) -> str:
        """Normalize a text field from raw model output."""
        text = str(raw.get(key, default) or default).strip()
        text = " ".join(text.split())
        return text[:max_chars]

    def as_list(key: str, fallback: list[str], max_items: int, max_chars: int) -> list[str]:
        """Normalize a list field from raw model output."""
        value = raw.get(key)
        items: list[str] = []
        if isinstance(value, list):
            for item in value:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    items.append(text[:max_chars])
                if len(items) >= max_items:
                    break
        return items if items else fallback[:max_items]

    report_title = as_text(
        "report_title",
        f"{symbol} Investment Report",
        80,
    )
    verdict = _normalize_report_verdict(raw.get("verdict") or (ai_analysis or {}).get("final_verdict"))
    confidence = as_text("confidence", "Medium", 12).title()
    if confidence not in {"High", "Medium", "Low"}:
        confidence = "Medium"

    investor_fit = as_text("investor_fit", "Review fit with your risk profile and time horizon.", 140)
    executive_summary = as_text(
        "executive_summary",
        str((ai_analysis or {}).get("plain_english") or "Summary unavailable."),
        420,
    )

    default_thesis = [
        "Price action and structure should be read with volume confirmation.",
        "Fundamental quality and valuation must be assessed together, not in isolation.",
        "Recent announcements and news can materially shift short-term risk/reward.",
    ]
    default_risks = [
        "Earnings execution risk can change conviction quickly.",
        "Macro or sector rotation may pressure valuation multiples.",
        "Event-driven volatility can invalidate short-term setups.",
    ]
    default_plan = [
        "Define your position size and invalidation level before entering.",
        "Track next results and key management commentary.",
        "Review allocation impact on your overall portfolio risk.",
    ]

    return {
        "report_title": report_title,
        "tier": tier,
        "symbol": symbol,
        "company_name": company_name,
        "verdict": verdict,
        "confidence": confidence,
        "investor_fit": investor_fit,
        "executive_summary": executive_summary,
        "thesis_points": as_list("thesis_points", default_thesis, 4, 170),
        "technical_view": as_text("technical_view", "Technical context is mixed.", 200),
        "fundamental_view": as_text("fundamental_view", "Fundamental context is mixed.", 200),
        "news_announcements_view": as_text("news_announcements_view", "News and announcements are neutral.", 200),
        "financial_health_view": as_text("financial_health_view", "Financial health context is limited.", 220),
        "risk_flags": as_list("risk_flags", default_risks, 4, 170),
        "action_plan": as_list("action_plan", default_plan, 3, 160),
    }


def _build_report_fallback_payload(
    *,
    symbol: str,
    company_name: str,
    tier: str,
    risk_level: str,
    ai_analysis: dict | None,
    error_text: str,
) -> dict[str, Any]:
    """Build deterministic fallback report payload when model output fails."""
    verdict = _normalize_report_verdict((ai_analysis or {}).get("final_verdict"))
    summary = str((ai_analysis or {}).get("plain_english") or "AI report generation is temporarily unavailable.")
    summary = " ".join(summary.split())[:420]

    fallback_raw = {
        "report_title": f"{symbol} Investment Report",
        "verdict": verdict,
        "confidence": "Low",
        "investor_fit": f"Prepared for {risk_level} risk profile; validate with your own plan.",
        "executive_summary": summary,
        "thesis_points": [
            "Use this report with on-screen charts and raw financial tables before acting.",
            "Wait for better data confirmation where recent signals are conflicting.",
            "Prioritize risk management over return chasing in uncertain setups.",
        ],
        "technical_view": str((ai_analysis or {}).get("technicals", {}).get("summary") or "Technical context is mixed."),
        "fundamental_view": str((ai_analysis or {}).get("fundamentals", {}).get("summary") or "Fundamental context is mixed."),
        "news_announcements_view": str((ai_analysis or {}).get("news", {}).get("summary") or "News context is neutral."),
        "financial_health_view": "Refer to quarterly, annual, balance sheet, cash flow, and shareholding sections for full confirmation.",
        "risk_flags": [
            "Model output fallback was used for this report.",
            "Event risk can move the stock quickly after announcements.",
            "Position sizing discipline is critical for capital protection.",
        ],
        "action_plan": [
            "Re-check price structure and volume trend before entry.",
            "Track next earnings release and major filings.",
            "Consult a SEBI-registered advisor before taking exposure.",
        ],
    }

    payload = _validate_report_payload(
        fallback_raw,
        symbol=symbol,
        company_name=company_name,
        tier=tier,
        ai_analysis=ai_analysis,
    )
    payload["error"] = error_text
    return payload


def _call_gemini_report(symbol: str, user_prompt: str) -> dict:
    """Call Google Gemini for report JSON with retry and JSON fence handling."""
    last_error = None
    for attempt in range(3):
        try:
            response = _get_client().chat.completions.create(
                model=_active_model_id(),
                messages=[
                    {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=8192,
            )

            raw = (response.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)

        except (RateLimitError, APIStatusError, json.JSONDecodeError) as e:
            wait = 2 ** attempt
            logger.warning(
                f"Gemini report generation failed for {symbol} (attempt {attempt+1}/3), retrying in {wait}s: {e}"
            )
            time.sleep(wait)
            last_error = e
            continue
        except Exception as e:
            logger.error(f"Gemini report unexpected error for {symbol}: {e}")
            raise

    raise last_error or RuntimeError("Report generation failed after retries")


async def generate_report_payload(
    *,
    symbol: str,
    company_name: str,
    tier: str,
    risk_level: str,
    fundamentals: dict,
    technicals: dict,
    news: list[dict],
    announcements: list[dict],
    analysis_snapshot: dict | None,
    ai_analysis: dict | None,
) -> dict[str, Any]:
    """Generate normalized AI report payload for PDF creation."""
    symbol = symbol.upper().strip()
    tier = (tier or "stellar").lower().strip()
    risk_level = (risk_level or "medium").lower().strip()

    if tier not in {"orbiter", "stellar", "apex"}:
        tier = "stellar"
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium"

    try:
        prompt = _build_report_user_prompt(
            symbol=symbol,
            company_name=company_name,
            tier=tier,
            risk_level=risk_level,
            fundamentals=fundamentals,
            technicals=technicals,
            news=news,
            announcements=announcements,
            analysis_snapshot=analysis_snapshot,
            ai_analysis=ai_analysis,
        )
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, _call_gemini_report, symbol, prompt)
        return _validate_report_payload(
            raw,
            symbol=symbol,
            company_name=company_name,
            tier=tier,
            ai_analysis=ai_analysis,
        )
    except Exception as e:
        logger.warning(f"Report payload fallback used for {symbol}: {e}")
        return _build_report_fallback_payload(
            symbol=symbol,
            company_name=company_name,
            tier=tier,
            risk_level=risk_level,
            ai_analysis=ai_analysis,
            error_text=str(e),
        )


# ── Core AI call ──────────────────────────────────────────────────────────────

def _call_gemini(symbol: str, user_prompt: str) -> dict:
    """
    Sync call to Google Gemini. Runs in thread pool.
    Retries 3x with backoff on rate limit / server errors.
    Returns parsed dict or raises on total failure.
    """
    last_error = None

    for attempt in range(3):
        try:
            response = _get_client().chat.completions.create(
                model=_active_model_id(),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
                # response_format not used — not supported by all free models
                # JSON is enforced via explicit prompt instruction instead
            )

            raw = response.choices[0].message.content.strip()
            logger.info(f"Gemini response for {symbol}: {len(raw)} chars")

            # Strip markdown fences if model wraps in ```json ... ```
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            return json.loads(raw)

        except RateLimitError as e:
            wait = 2 ** attempt
            logger.warning(f"Gemini rate limit (attempt {attempt+1}/3), retrying in {wait}s: {e}")
            time.sleep(wait)
            last_error = e

        except json.JSONDecodeError as e:
            wait = 2 ** attempt
            logger.warning(
                f"Gemini returned invalid JSON for {symbol} "
                f"(attempt {attempt+1}/3), retrying in {wait}s: {e}"
            )
            time.sleep(wait)
            last_error = e
            continue

        except APIStatusError as e:
            if e.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(f"Gemini server error {e.status_code} (attempt {attempt+1}/3), retrying in {wait}s")
                time.sleep(wait)
                last_error = e
            else:
                raise  # 4xx errors (bad key, wrong model) shouldn't be retried

        except Exception as e:
            logger.error(f"Gemini unexpected error for {symbol}: {e}")
            raise

    raise last_error or RuntimeError("Gemini call failed after 3 attempts")


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

    # If model prose conflicts with final verdict language, make stance explicit.
    verdict_mentions = re.findall(r"\b(BUY|HOLD|AVOID)\b", plain_english.upper())
    if verdict_mentions and adjusted_final not in verdict_mentions:
        plain_english = f"Final verdict: {adjusted_final}. {plain_english}"
    elif not verdict_mentions:
        plain_english = f"{plain_english.rstrip()} Overall stance for this risk profile: {adjusted_final}."

    risk_match = raw.get("risk_match")
    if not isinstance(risk_match, bool):
        risk_match = adjusted_final != "AVOID"

    social = raw.get("social", {"verdict": "Neutral", "summary": "No social data available."})
    if not isinstance(social, dict):
        social = {"verdict": "Neutral", "summary": "No social data available."}

    return {
        "symbol":          symbol.upper(),
        "risk_level":      risk_level,
        "fundamentals":    fundamentals,
        "technicals":      technicals,
        "news":            news,
        "social":          social,
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


def _build_rule_based_fallback(
    symbol: str,
    risk_level: str,
    fundamentals: dict,
    technicals: dict,
    news: list[dict],
    analysis_snapshot: dict | None,
    error_text: str,
) -> dict:
    """Build deterministic fallback analysis when LLM output is unavailable."""
    # Fundamentals scoring
    score_f = 0.0
    roe = fundamentals.get("roe")
    roce = fundamentals.get("roce")
    pe = fundamentals.get("pe_ratio")
    dy = fundamentals.get("dividend_yield")
    eps = fundamentals.get("eps")

    if isinstance(roe, (int, float)):
        score_f += 1.0 if roe >= 15 else -0.5
    if isinstance(roce, (int, float)):
        score_f += 1.0 if roce >= 15 else -0.5
    if isinstance(pe, (int, float)):
        if pe <= 30:
            score_f += 0.5
        elif pe >= 60:
            score_f -= 0.5
    if isinstance(dy, (int, float)) and dy >= 1:
        score_f += 0.25
    if isinstance(eps, (int, float)) and eps > 0:
        score_f += 0.25

    if score_f >= 1.5:
        f_verdict = "Strong"
    elif score_f <= -0.5:
        f_verdict = "Weak"
    else:
        f_verdict = "Neutral"

    # Technical verdict from calculated signal first
    overall_tech = str(technicals.get("overall_signal") or "").lower()
    if overall_tech == "bullish":
        t_verdict = "Bullish"
    elif overall_tech == "bearish":
        t_verdict = "Bearish"
    else:
        t_verdict = "Mixed"

    # News verdict via lightweight keyword heuristic
    positive_words = {"gain", "growth", "up", "approval", "order", "beat", "buy", "expands"}
    negative_words = {"fall", "down", "decline", "probe", "loss", "miss", "downgrade", "penalty"}
    headlines = []
    for item in news[:5]:
        if isinstance(item, dict) and item.get("title"):
            headlines.append(str(item.get("title")))
    if isinstance(analysis_snapshot, dict):
        for item in (analysis_snapshot.get("important_announcements") or [])[:5]:
            if isinstance(item, dict) and item.get("subject"):
                headlines.append(str(item.get("subject")))

    pos_hits = 0
    neg_hits = 0
    for title in headlines:
        t = title.lower()
        pos_hits += sum(word in t for word in positive_words)
        neg_hits += sum(word in t for word in negative_words)

    if pos_hits > neg_hits + 1:
        n_verdict = "Positive"
    elif neg_hits > pos_hits + 1:
        n_verdict = "Negative"
    else:
        n_verdict = "Neutral"

    final_verdict = _risk_adjusted_verdict(
        risk_level=risk_level,
        fundamentals_verdict=f_verdict,
        technicals_verdict=t_verdict,
        news_verdict=n_verdict,
        model_final="HOLD",
    )

    # Build plain-English summary from enriched context
    movement_1m = None
    trend_signal = "sideways"
    volume_ratio = None
    if isinstance(analysis_snapshot, dict):
        ctx = analysis_snapshot.get("volume_exchange_price_context") or {}
        movement = ctx.get("price_movement") or {}
        movement_1m = ((movement.get("1mo") or {}).get("change_pct"))
        trend_signal = movement.get("trend_signal") or "sideways"
        volume_ratio = ((ctx.get("volume") or {}).get("volume_ratio_vs_20d"))

    movement_text = "price movement data is limited"
    if isinstance(movement_1m, (int, float)):
        direction = "up" if movement_1m >= 0 else "down"
        movement_text = f"price is {direction} {abs(movement_1m):.2f}% over 1 month with a {trend_signal} structure"

    volume_text = "volume trend is neutral"
    if isinstance(volume_ratio, (int, float)):
        if volume_ratio >= 1.5:
            volume_text = f"volume is strong at {volume_ratio:.2f}x of 20-day average"
        elif volume_ratio < 0.7:
            volume_text = f"volume is weak at {volume_ratio:.2f}x of 20-day average"
        else:
            volume_text = f"volume is near normal at {volume_ratio:.2f}x of 20-day average"

    headline_text = headlines[0] if headlines else "no major news or announcements are available"

    plain_english = (
        f"For a {risk_level} risk investor, fundamentals look {f_verdict.lower()} while technicals remain {t_verdict.lower()}. "
        f"The stock context shows {movement_text}, and {volume_text}. "
        f"Recent cue: {headline_text}. "
        f"Overall stance for this risk profile: {final_verdict}."
    )

    return {
        "symbol": symbol,
        "risk_level": risk_level,
        "error": error_text,
        "final_verdict": final_verdict,
        "plain_english": plain_english,
        "fundamentals": {
            "verdict": f_verdict,
            "summary": "Rule-based fallback used due temporary AI provider issue.",
        },
        "technicals": {
            "verdict": t_verdict,
            "summary": "Based on overall technical signal and indicator alignment.",
        },
        "news": {
            "verdict": n_verdict,
            "summary": "Derived from latest headlines and announcement language.",
        },
        "social": {
            "verdict": "Neutral",
            "summary": "Social signal not used in fallback mode.",
        },
        "risk_match": final_verdict != "AVOID",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
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
    social_sentiment: dict | None = None,
    analysis_snapshot: dict | None = None,
) -> dict:
    """
    Async entry point — runs blocking Gemini call in thread pool.

    Args:
        symbol:           NSE stock symbol (e.g. "RELIANCE")
        fundamentals:     merged dict from yfinance + screener ratios
        technicals:       dict from technicals_service.calculate_technicals()
        news:             list from news_service.get_news()
        risk_level:       "low" | "medium" | "high"
        social_sentiment: optional dict from sentiment_service.get_sentiment()
        analysis_snapshot: structured snapshot built from all page-relevant data

    Returns:
        Structured analysis dict. Never raises — returns error dict on failure.
    """
    symbol     = symbol.upper().strip()
    risk_level = risk_level.lower().strip()

    if risk_level not in ("low", "medium", "high"):
        risk_level = "medium"

    try:
        user_prompt = _build_user_prompt(
            symbol,
            risk_level,
            fundamentals,
            technicals,
            news,
            social_sentiment,
            analysis_snapshot,
        )
        loop = asyncio.get_running_loop()
        raw  = await loop.run_in_executor(None, _call_gemini, symbol, user_prompt)
        return _validate_and_enrich(raw, symbol, risk_level)

    except Exception as e:
        logger.error(f"AI analysis failed for {symbol}: {e}")
        return _build_rule_based_fallback(
            symbol=symbol,
            risk_level=risk_level,
            fundamentals=fundamentals,
            technicals=technicals,
            news=news,
            analysis_snapshot=analysis_snapshot,
            error_text=str(e),
        )
