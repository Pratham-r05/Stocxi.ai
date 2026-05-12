"""
announcement_summary_service.py — Gemini Flash summarisation for announcements.

Generates a one-sentence investor-relevant context for each corporate announcement
based on its subject, date, and category. Uses a single batched Gemini call so
the overhead is one API round-trip per page load (cached by the announcements endpoint).

Model: gemini-2.5-flash (cheap, fast, sufficient for single-sentence generation).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types as genai_types

try:
    from config import settings  # type: ignore
except ImportError:
    from config import settings  # type: ignore

logger = logging.getLogger(__name__)

_FLASH_MODEL = "gemini-2.5-flash"
_client = genai.Client(
    vertexai=True,
    project=settings.google_cloud_project,
    location=settings.vertex_location,
)

_SYSTEM = (
    "You are a concise Indian equity analyst assistant. "
    "Given a list of corporate announcements, return a JSON array where each element "
    "has an 'id' (matching the input id) and a 'summary' (one sentence, ≤18 words) "
    "explaining what this announcement means for a retail investor. "
    "Never say buy/sell/recommend. Use plain English. Return only the JSON array."
)


def _build_prompt(symbol: str, items: list[dict]) -> str:
    rows = [
        {
            "id": i,
            "subject": it["subject"],
            "category": it["category"],
            "date": it["date"],
            "pdf_text": _meaningful_pdf_snippet(it.get("pdf_text") or ""),
            "details": _clean_summary_text(it.get("details") or "", 220),
        }
        for i, it in enumerate(items)
    ]
    return (
        f"Stock: {symbol}\n"
        f"Announcements:\n{json.dumps(rows, ensure_ascii=False)}"
    )


def _clean_summary_text(text: str, max_len: int = 140) -> str:
    cleaned = " ".join(str(text or "").replace("\n", " ").split()).strip()
    return cleaned[:max_len]


def _meaningful_pdf_snippet(text: str) -> str:
    """Keep filing substance, not address/header boilerplate."""
    blocked = (
        "corporate office", "registered office", "regd. office", "cin:",
        "phone", "email", "www.", "floor", "road", "nagar", "address",
        "dear sir", "dear madam", "scrip code", "subject:", "ref:",
    )
    useful = (
        "approved", "consider", "fund raising", "financial results",
        "dividend", "bonus", "split", "record date", "appointment",
        "resignation", "acquisition", "meeting", "outcome",
    )
    lines = [line.strip() for line in str(text or "").splitlines()]
    for line in lines:
        compact = " ".join(line.split())
        low = compact.lower()
        if len(compact) < 24:
            continue
        if any(token in low for token in blocked):
            continue
        if any(token in low for token in useful):
            return _clean_summary_text(compact, 220)
    return ""


def _fallback_summary(item: dict) -> str:
    subject = str(item.get("subject") or item.get("title") or "").strip()
    category = str(item.get("category") or "").strip()
    date = str(item.get("date") or "").strip()
    pdf_text = _meaningful_pdf_snippet(item.get("pdf_text") or "")
    details = _clean_summary_text(item.get("details") or "", 220)
    context = " ".join(part for part in (subject, category, pdf_text, details) if part)
    specific = _clean_summary_text(pdf_text or details or subject, 100).rstrip(" .;:")

    low = context.lower()
    if "dividend" in low:
        amount = _extract_dividend_amount(context)
        if amount:
            return _clean_summary_text(f"Dividend filing: board declared {amount} dividend; {specific}.")
        return _clean_summary_text(f"Dividend filing: {specific}.")
    if "fund raising" in low or "fundraising" in low or "raising of funds" in low:
        return _clean_summary_text(f"Fund-raising filing: {specific}.")
    if "financial result" in low or "result" in low:
        if "dividend" in low:
            return _clean_summary_text(f"Results and dividend filing: {specific}.")
        return _clean_summary_text(f"Results filing: {specific}.")
    if "bonus" in low:
        return _clean_summary_text(f"Bonus issue filing: {specific}.")
    if "board meeting" in low or "board meeting" in category.lower():
        if "dividend" in low and ("consider" in low or "approve" in low):
            return _clean_summary_text(f"Board meeting notice: {specific}.")
        if "result" in low:
            return _clean_summary_text(f"Board meeting notice: {specific}.")
        return _clean_summary_text(f"Board meeting notice: {specific}.")
    if "investor meet" in low or "analyst" in low:
        return _clean_summary_text(f"Investor meet filing: {specific}.")
    if "investor presentation" in low:
        return _clean_summary_text(f"Investor presentation: {specific}.")
    if "press release" in low or "media release" in low:
        return _clean_summary_text(f"Press release filing: {specific}.")
    if "annual general meeting" in low or " agm" in low:
        return _clean_summary_text(f"AGM filing: {specific}.")
    if "record date" in low:
        return _clean_summary_text(f"Record date filing: {specific}.")
    if "appointment" in low or "re-appointment" in low or "resignation" in low:
        return _clean_summary_text(f"Leadership filing: {specific}.")
    if "regulation 30" in low or "lodr" in low:
        return _clean_summary_text(f"Regulation 30 filing: {specific}.")
    if "certificate under reg. 74" in low or "74 (5)" in low:
        return _clean_summary_text(f"Compliance filing: {specific}.")

    if pdf_text:
        return _clean_summary_text(f"Filing update: {pdf_text}", 140)
    base = subject or category or "Corporate filing"
    return _clean_summary_text(f"Corporate filing: {base}.")


def _extract_dividend_amount(text: str) -> str:
    patterns = (
        r"(?:rs\.?|inr|₹)\s*[\d]+(?:\.\d+)?\s*(?:per\s+share|/[- ]?share)?",
        r"[\d]+(?:\.\d+)?\s*(?:per\s+share|/[- ]?share)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_summary_text(match.group(0), 40)
    return ""


def _is_generic_summary(text: str) -> bool:
    low = str(text or "").lower()
    generic = (
        "board meeting update:",
        "dividend filing:",
        "results filing:",
        "reported on",
        " on 20",
    )
    return any(token in low for token in generic)


def _summary_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _parse_summaries(text: str, n: int) -> list[str]:
    """Extract summaries from Gemini JSON response. Falls back to empty strings."""
    try:
        # Strip markdown code fences if present
        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            if all(isinstance(entry, str) for entry in parsed):
                return [str(entry).strip() for entry in parsed][:n] + [""] * max(0, n - len(parsed))

            by_id: dict[int, str] = {}
            for entry in parsed:
                if not isinstance(entry, dict) or "id" not in entry:
                    continue
                try:
                    idx = int(entry.get("id"))
                except (TypeError, ValueError):
                    continue
                by_id[idx] = str(entry.get("summary", "")).strip()
            if by_id:
                return [by_id.get(i, "") for i in range(n)]
    except Exception:
        pass
    return [""] * n


async def summarise_announcements(
    symbol: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Add a 'summary' field to each announcement dict via a single Gemini Flash call.

    Args:
        symbol: NSE ticker for context.
        items:  List of announcement dicts (subject, date, category, …).

    Returns:
        Same list with 'summary' field added to each item.
        Falls back gracefully — if Gemini fails, summaries are empty strings.
    """
    if not items:
        return items

    prompt = _build_prompt(symbol, items)
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _client.models.generate_content(
                model=_FLASH_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_SYSTEM,
                    temperature=0.0,
                    max_output_tokens=512,
                ),
            ),
        )
        summaries = _parse_summaries(response.text, len(items))
        logger.info("announcement_summary: %d summaries generated for %s", len(items), symbol)
    except Exception as exc:
        logger.warning("announcement_summary: Gemini call failed for %s — %s", symbol, exc)
        summaries = [""] * len(items)

    prepared: list[str] = []
    for item, summary in zip(items, summaries):
        final_summary = _clean_summary_text(summary.strip())
        if not final_summary or _is_generic_summary(final_summary):
            final_summary = _fallback_summary(item)
        prepared.append(final_summary)

    counts: dict[str, int] = {}
    for summary in prepared:
        key = _summary_key(summary)
        if key:
            counts[key] = counts.get(key, 0) + 1

    result = []
    for item, final_summary in zip(items, prepared):
        if counts.get(_summary_key(final_summary), 0) > 1:
            final_summary = _fallback_summary(item)
        result.append({**item, "summary": final_summary})
    return result
