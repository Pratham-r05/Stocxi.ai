"""
announcements_service.py — Corporate announcement nodes: NSE + BSE (parallel fetch).

Unlike most services, announcements are fetched from BOTH sources simultaneously
and merged (not a waterfall). NSE and BSE often have different subsets of filings.

Sources:
  NSE: announcements() + boardMeetings(symbol) + actions(symbol)
  BSE: actions(scripcode) + announcements(scripcode)

Output nodes (NodeCategory.announcement):
  Board_Meeting     — upcoming/recent board meetings
  Dividend_Declared — dividend declarations (ex-date, amount)
  Bonus_Split       — bonus issues and stock splits
  Corporate_Action  — other actions (rights, buyback, AGM)
  NSE_Filing        — regulatory filings, exchange notices

Signal logic:
  Board meetings near a result date → neutral (watch signal)
  Dividend declaration → positive (income signal)
  Bonus/split → positive (confidence signal)
  Regulatory filing → neutral (informational)

LLM Summarization:
  After PDF enrichment, all items are batch-summarized via Gemini 2.5 Pro.
  Each announcement gets a 1-2 line summary stored in node.value.
  Falls back to text truncation on LLM failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Any

from backend.fetchers import bse_client, nse_client
from backend.schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from backend.schemas.messages import UserProfile
from backend.config import yaml_cfg, settings
from backend.util.ist_calendar import now_ist

logger = logging.getLogger(__name__)


def _normalise_date(raw: str) -> str:
    """
    Normalise a date string to ISO format (YYYY-MM-DD).

    NSE/BSE return dates in "DD-Mon-YYYY" (e.g. "12-May-2026").
    Slicing to [:10] truncates the year — this helper converts to ISO instead.

    Args:
        raw: Raw date string from NSE/BSE (any format).

    Returns:
        ISO date string "YYYY-MM-DD", or the raw string unchanged if parsing fails.
    """
    if not raw:
        return raw
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    # Generic fallback via pandas if available
    try:
        import pandas as pd
        parsed = pd.to_datetime(raw, errors="coerce")
        if parsed is not pd.NaT:
            return parsed.date().isoformat()
    except Exception:
        pass
    logger.debug("_normalise_date: could not parse %r — returning as-is", raw)
    return raw


async def _summarize_announcements(items: list[dict], symbol: str) -> list[dict]:
    """
    Batch-summarize announcements using Gemini 2.5 Pro.

    Takes enriched announcement items (with purpose + pdf_text) and generates
    a 1-2 line summary for each. Attaches ``llm_summary`` to each item dict.

    Falls back gracefully — on any failure, items are returned unchanged
    (node builder will use text truncation).

    Args:
        items:  Announcement dicts with ``purpose`` and optional ``pdf_text``.
        symbol: NSE ticker for context.

    Returns:
        Same list with ``llm_summary`` key added where possible.
    """
    if not items:
        return items

    # Build compact input: index + purpose + date + truncated pdf_text
    numbered: list[str] = []
    for i, item in enumerate(items):
        purpose = str(item.get("purpose") or item.get("subject") or "")[:200]
        iso_date = _normalise_date(str(item.get("date") or item.get("ex_date") or ""))
        pdf_text = str(item.get("pdf_text") or "")[:300]
        cls = _classify(purpose, item.get("_type", "corporate_action"))
        chunk = f"[{i}] type={cls} date={iso_date}\n{purpose}"
        if pdf_text:
            chunk += f"\nFiling excerpt: {pdf_text}"
        numbered.append(chunk)

    prompt = (
        f"You are a SEBI-aware Indian equity analyst. Summarize each corporate "
        f"announcement for {symbol} in 1-2 concise sentences (max 150 chars each). "
        f"Focus on what happened and its likely market impact.\n\n"
        f"Announcements:\n\n" + "\n---\n".join(numbered) +
        f"\n\nReturn ONLY a JSON array of strings, one summary per announcement, "
        f"in the same order. Example: [\"Board approved Q3 results showing 12% PAT growth.\", ...]"
    )

    try:
        import google.auth
        import google.auth.transport.requests
        from openai import OpenAI

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        client = OpenAI(
            api_key=credentials.token,
            base_url=settings.google_base_url,
        )

        model_id = yaml_cfg.versions.get("llm", {}).get("active", "google/gemini-2.5-pro")

        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "Output ONLY a valid JSON array of strings. No markdown, no backticks, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=4096,
        )

        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        summaries: list[str] = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                summaries = [str(s) for s in parsed]
        except json.JSONDecodeError:
            # Try to fix truncated JSON: find last complete string entry
            # e.g. '["summary1", "summary2", "summary3'  →  '["summary1", "summary2"]'
            try:
                # Find all complete quoted strings in the array
                import re
                strings = re.findall(r'"([^"]*)"', raw)
                if strings:
                    summaries = strings
                    logger.warning("_summarize_announcements: recovered %d summaries from truncated JSON", len(summaries))
            except Exception:
                pass

        if not summaries:
            raise ValueError("No summaries recovered from LLM response")

        # Attach summaries to items
        for i, item in enumerate(items):
            if i < len(summaries) and summaries[i].strip():
                item["llm_summary"] = summaries[i].strip()[:150]

        logger.info("_summarize_announcements: %s — %d/%d summaries generated",
                    symbol, sum(1 for i in items if "llm_summary" in i), len(items))

    except Exception as exc:
        logger.warning("_summarize_announcements: LLM call failed for %s — falling back to truncation: %s",
                       symbol, exc)

    return items


async def get_announcements(
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
    request_id: str = "",
) -> list[Node]:
    """
    Fetch corporate announcements from NSE and BSE in parallel and merge.

    Pipeline:
      1. Fetch from NSE (boardMeetings + actions) and BSE (actions) in parallel
      2. Sort by date descending, deduplicate by (date, purpose)
      3. Keep top 10
      4. Enrich with PDF text (best-effort)
      5. Batch-summarize via Gemini 2.5 Pro (LLM)
      6. Build one Node per announcement with summary as value

    Args:
        symbol:     NSE ticker in uppercase.
        as_of_date: Analysis date (nodes stamped with this date).
        profile:    User profile for weight selection.
        request_id: Trace ID for logging.

    Returns:
        list[Node] — announcement nodes, deduplicated by (date, purpose).
        Empty list if both sources fail.
    """
    symbol = symbol.upper().strip()
    bse_code = await _try_bse_code(symbol)

    # Fetch from NSE and BSE concurrently
    nse_result, bse_result = await asyncio.gather(
        _fetch_nse(symbol),
        _fetch_bse(symbol, bse_code),
        return_exceptions=True,
    )

    all_items: list[dict] = []

    if isinstance(nse_result, dict):
        all_items.extend(nse_result.get("board_meetings", []))
        all_items.extend(nse_result.get("actions", []))
    else:
        logger.debug("NSE announcements failed for %s: %s", symbol, nse_result)

    if isinstance(bse_result, dict):
        all_items.extend(bse_result.get("actions", []))
    else:
        logger.debug("BSE announcements failed for %s: %s", symbol, bse_result)

    if not all_items:
        return []

    # Sort by date descending (newest first) before deduplication
    def _sort_key(item: dict) -> str:
        raw = str(item.get("date") or item.get("ex_date") or "")
        return _normalise_date(raw) or "0000-00-00"

    all_items.sort(key=_sort_key, reverse=True)

    # Deduplicate by (date, purpose) — NSE and BSE often carry the same events
    seen: set[tuple] = set()
    unique: list[dict] = []
    for item in all_items:
        key = (
            _normalise_date(str(item.get("date") or item.get("ex_date") or "")),
            str(item.get("purpose") or "")[:50].lower(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Keep only the 10 most recent meaningful announcements
    unique = unique[:10]

    # Enrich with PDF text (best-effort, failures silently skipped)
    enriched = await _enrich_with_pdf_text(unique)

    # Batch-summarize via Gemini 2.5 Pro (LLM) — attaches llm_summary to each item
    enriched = await _summarize_announcements(enriched, symbol)

    return _build_nodes(enriched, symbol, as_of_date, profile, now_ist())


# ── Fetch helpers ─────────────────────────────────────────────────────────────

async def _fetch_nse(symbol: str) -> dict:
    """Fetch board meetings + actions from NSE."""
    meetings_task = nse_client.fetch_board_meetings(symbol)
    actions_task  = nse_client.fetch_actions(symbol)
    meetings, actions = await asyncio.gather(
        meetings_task, actions_task, return_exceptions=True
    )
    result: dict = {"board_meetings": [], "actions": []}
    if isinstance(meetings, dict):
        result["board_meetings"] = [
            {**m, "_type": "board_meeting", "_source": "nse_library"}
            for m in meetings.get("meetings", [])
        ]
    if isinstance(actions, dict):
        result["actions"] = [
            {**a, "_type": "corporate_action", "_source": "nse_library"}
            for a in actions.get("actions", [])
        ]
    return result


async def _fetch_bse(symbol: str, bse_code: str | None) -> dict:
    """Fetch actions from BSE."""
    if not bse_code:
        return {"actions": []}
    try:
        actions = await bse_client.fetch_actions(symbol)
        return {
            "actions": [
                {**a, "_type": "corporate_action", "_source": "bse_library"}
                for a in actions.get("actions", [])
            ]
        }
    except Exception as exc:
        logger.debug("BSE actions fetch failed for %s: %s", symbol, exc)
        return {"actions": []}


# ── Node builder ──────────────────────────────────────────────────────────────

def _build_nodes(
    items: list[dict],
    symbol: str,
    as_of_date: date,
    profile: UserProfile,
    fetched_at: datetime,
) -> list[Node]:
    """Convert raw announcement items to Node list.

    Deduplicates by node_id so multiple announcements of the same
    classification on the same date don't produce duplicate nodes.
    When duplicates share a classification, a numeric suffix is appended
    to the node name (e.g. ``Board_Meeting_2``, ``Board_Meeting_3``)
    to produce unique node_ids.
    """
    raw_nodes: list[Node] = []
    w_ver = yaml_cfg.versions.get("weight_version", "")

    for item in items:
        node = _item_to_node(item, symbol, as_of_date, profile, fetched_at, w_ver)
        if node is not None:
            raw_nodes.append(node)

    seen_ids: dict[str, int] = {}
    nodes: list[Node] = []
    for node in raw_nodes:
        nid = node.node_id
        if nid not in seen_ids:
            seen_ids[nid] = 1
            nodes.append(node)
        else:
            seen_ids[nid] += 1
            new_name = f"{node.name}_{seen_ids[nid]}"
            cat = node.category.value if hasattr(node.category, "value") else str(node.category)
            new_node_id = f"{node.stock}|{cat}|{new_name}|{node.as_of_date}"
            node = node.model_copy(update={"name": new_name, "node_id": new_node_id})
            nodes.append(node)

    return nodes


def _classify(purpose: str, item_type: str) -> str:
    """
    Classify an announcement into one of the 14 weight classes defined in weights.yaml.

    Order matters — higher-impact classes are checked first so a SEBI notice is
    never misclassified as a generic filing.

    Args:
        purpose:   Lowercased purpose/subject text.
        item_type: Raw "_type" field from the fetcher ("board_meeting" / "corporate_action").

    Returns:
        Classification key matching a key in weights.yaml announcement section.
    """
    p = purpose.lower()

    # Tier 1 — regulatory / legal risk (check before anything else)
    if any(k in p for k in ("sebi", "securities and exchange", "investigation",
                             "penalty", "show cause", "enforcement", "violation",
                             "insider trading", "market manipulation")):
        return "sebi_action"

    # Tier 2 — fraud / audit risk
    if any(k in p for k in ("fraud", "forensic", "accounting irregulari",
                             "qualified opinion", "audit qualification",
                             "going concern", "embezzlement", "misappropriation")):
        return "fraud_allegation"

    # Tier 3 — promoter activity
    if any(k in p for k in ("promoter", "pledge", "encumber",
                             "creeping acquisition", "open offer")):
        return "promoter_trade"

    # Tier 4 — leadership change
    if any(k in p for k in ("appointment", "resignation", "cessation",
                             "managing director", "chief executive", "ceo", "cfo",
                             "chief financial", "whole-time director", "key managerial")):
        return "leadership_change"

    # Tier 5 — credit rating
    if any(k in p for k in ("credit rating", "crisil", "icra", "care rating",
                             "fitch", "rating upgrade", "rating downgrade",
                             "rating reaffirm", "rating assigned")):
        return "credit_rating"

    # Tier 6 — M&A / restructuring
    if any(k in p for k in ("merger", "amalgamation", "acquisition", "demerger",
                             "scheme of arrangement", "joint venture", "takeover",
                             "slump sale", "business transfer")):
        return "ma_event"

    # Tier 7 — buyback
    if any(k in p for k in ("buyback", "buy back", "share repurchase")):
        return "buyback"

    # Tier 8 — dividend
    if any(k in p for k in ("dividend", "interim div", "final div",
                             "special dividend")):
        return "dividend_declared"

    # Tier 9 — bonus / split
    if any(k in p for k in ("bonus", "stock split", "sub-division",
                             "consolidation of shares")):
        return "bonus_split"

    # Tier 10 — rights issue
    if any(k in p for k in ("rights issue", "rights entitlement",
                             "rights share", "fpo", "further public offer")):
        return "rights_issue"

    # Tier 11 — board meeting (results agenda vs generic)
    if item_type == "board_meeting" or "board meeting" in p or "board of directors" in p:
        if any(k in p for k in ("financial result", "quarterly result",
                                 "q1", "q2", "q3", "q4", "annual result",
                                 "unaudited result", "audited result")):
            return "board_meeting_results"
        return "board_meeting_generic"

    # Tier 12 — AGM / EGM
    if any(k in p for k in ("annual general meeting", "agm",
                             "extraordinary general meeting", "egm",
                             "general meeting")):
        return "agm_egm"

    # Default — generic regulatory filing
    return "nse_filing_generic"


def _item_to_node(
    item: dict,
    symbol: str,
    as_of_date: date,
    profile: "UserProfile",
    fetched_at: datetime,
    w_ver: str,
) -> Node | None:
    """
    Convert one announcement item to a Node.

    Classification is done by _classify() → 14 impact classes.
    Weight and horizon_relevance are read from weights.yaml for the class.
    Node name reflects the actual impact class, not just a generic bucket.

    Args:
        item:       Raw announcement dict from fetcher.
        symbol:     NSE ticker.
        as_of_date: Analysis date.
        profile:    UserProfile — determines short vs long weight.
        fetched_at: Fetch timestamp.
        w_ver:      Weight version string from versions.yaml.

    Returns:
        Node, or None if purpose text is missing.
    """
    purpose = str(item.get("purpose") or item.get("subject") or item.get("details") or "").strip()
    if not purpose:
        return None

    event_date = (
        item.get("date") or
        item.get("ex_date") or
        item.get("record_date") or
        str(as_of_date)
    )
    iso_date   = _normalise_date(str(event_date))
    source     = item.get("_source", "nse_library")
    item_type  = item.get("_type", "corporate_action")
    pdf_text   = item.get("pdf_text") or ""

    # ── Classify ──────────────────────────────────────────────────────────────
    cls = _classify(purpose, item_type)

    # ── Weight lookup from weights.yaml ───────────────────────────────────────
    ann_weights = yaml_cfg.weights.get("announcement", {})
    cls_cfg     = ann_weights.get(cls, {})
    is_short    = getattr(profile, "horizon", "short") in ("short", "Horizon.short")
    weight      = float(cls_cfg.get("short" if is_short else "long", 0.10))
    horizon_str = cls_cfg.get("horizon", "both")
    horizon     = HorizonRelevance(horizon_str) if horizon_str in ("short", "long", "both") else HorizonRelevance.both

    # ── Node name (human-readable, matches classification) ────────────────────
    _NODE_NAMES: dict[str, str] = {
        "sebi_action":           "SEBI_Action",
        "fraud_allegation":      "Fraud_Flag",
        "promoter_trade":        "Promoter_Trade",
        "leadership_change":     "Leadership_Change",
        "credit_rating":         "Credit_Rating_Change",
        "ma_event":              "MA_Event",
        "buyback":               "Buyback",
        "dividend_declared":     "Dividend_Declared",
        "bonus_split":           "Bonus_Split",
        "rights_issue":          "Rights_Issue",
        "board_meeting_results": "Board_Meeting",
        "agm_egm":               "AGM_EGM",
        "board_meeting_generic": "Board_Meeting",
        "nse_filing_generic":    "NSE_Filing",
    }
    name = _NODE_NAMES.get(cls, "NSE_Filing")

    # ── Signal ────────────────────────────────────────────────────────────────
    # Use yaml signal hint as default, then override for context-dependent cases.
    _SIGNAL_DEFAULTS: dict[str, NodeSignal] = {
        "sebi_action":           NodeSignal.negative,
        "fraud_allegation":      NodeSignal.negative,
        "promoter_trade":        NodeSignal.neutral,   # caller must check buy vs sell
        "leadership_change":     NodeSignal.neutral,
        "credit_rating":         NodeSignal.neutral,   # caller must check upgrade vs downgrade
        "ma_event":              NodeSignal.neutral,
        "buyback":               NodeSignal.positive,
        "dividend_declared":     NodeSignal.positive,
        "bonus_split":           NodeSignal.positive,
        "rights_issue":          NodeSignal.neutral,
        "board_meeting_results": NodeSignal.neutral,
        "agm_egm":               NodeSignal.neutral,
        "board_meeting_generic": NodeSignal.neutral,
        "nse_filing_generic":    NodeSignal.neutral,
    }
    signal = _SIGNAL_DEFAULTS.get(cls, NodeSignal.neutral)

    # Refine signal for context-dependent classes
    p_low = purpose.lower()
    if cls == "promoter_trade":
        if any(k in p_low for k in ("purchase", "acquisition", "buy", "increase")):
            signal = NodeSignal.positive
        elif any(k in p_low for k in ("sale", "sell", "pledge", "encumber", "reduce")):
            signal = NodeSignal.negative
    elif cls == "credit_rating":
        if any(k in p_low for k in ("upgrade", "positive outlook", "reaffirm")):
            signal = NodeSignal.positive
        elif any(k in p_low for k in ("downgrade", "negative outlook", "watch negative")):
            signal = NodeSignal.negative
    elif cls == "leadership_change":
        if "resignation" in p_low or "cessation" in p_low:
            signal = NodeSignal.negative   # exits are a flag

    # ── Value string — prefer LLM summary, fallback to truncated text ────────
    llm_summary = item.get("llm_summary", "").strip()
    if llm_summary:
        value = llm_summary[:150]
    else:
        pdf_snippet = f" | Filing: {pdf_text[:120].strip()}" if pdf_text else ""
        amount = _to_float(item.get("facevalue"))

        if cls == "dividend_declared":
            base = (f"Dividend: ₹{amount}/share, ex-date {iso_date}"
                    if amount else f"Dividend declared, ex-date {iso_date}")
        elif cls == "buyback":
            base = f"Buyback: {purpose[:100]}"
        elif cls in ("board_meeting_results", "board_meeting_generic"):
            base = f"Board meeting: {purpose[:80]} on {iso_date}"
        elif cls == "sebi_action":
            base = f"SEBI/Regulatory action: {purpose[:100]}"
        elif cls == "fraud_allegation":
            base = f"Fraud/audit flag: {purpose[:100]}"
        elif cls == "leadership_change":
            base = f"Leadership: {purpose[:100]}"
        elif cls == "ma_event":
            base = f"M&A/Restructuring: {purpose[:100]}"
        elif cls == "promoter_trade":
            base = f"Promoter activity: {purpose[:100]}"
        elif cls == "credit_rating":
            base = f"Credit rating: {purpose[:100]}"
        elif cls == "rights_issue":
            base = f"Rights issue: {purpose[:100]}"
        elif cls == "agm_egm":
            base = f"General meeting: {purpose[:100]}"
        elif cls == "bonus_split":
            base = f"{purpose[:100]}, date: {iso_date}"
        else:
            base = purpose[:120]

        value = (base + pdf_snippet)[:150]   # cap at Node.value max 150 chars

    return Node(
        stock=symbol,
        category=NodeCategory.announcement,
        name=name,
        value=value,
        value_raw={
            "purpose":        purpose,
            "classification": cls,
            "date":           iso_date,
            "attachment_url": item.get("pdf_url") or "",
            "pdf_text":       pdf_text,
            "llm_summary":    llm_summary,
            "filing_type":    item_type,
            "facevalue":      item.get("facevalue"),
            "ex_date":        _normalise_date(str(item.get("ex_date") or "")),
            "record_date":    _normalise_date(str(item.get("record_date") or "")),
            "source":         source,
        },
        signal=signal,
        confidence=1.00,   # both NSE and BSE are L1
        source=source,
        source_url=item.get("pdf_url") or "",
        as_of_date=as_of_date,
        fetched_at_ist=fetched_at,
        horizon_relevance=horizon,
        weight=weight,
        weight_version=w_ver,
        sanitized=False,
    )


# ── PDF extraction ────────────────────────────────────────────────────────────

_PDF_ALLOWED_DOMAINS = {"nseindia.com", "bseindia.com", "static.bseindia.com"}
_PDF_MAX_CHARS       = 1000   # first N chars of extracted text per announcement
_PDF_FETCH_TIMEOUT   = 10     # seconds


async def _enrich_with_pdf_text(items: list[dict]) -> list[dict]:
    """
    Fetch and parse PDF attachments for items that have a pdf_url.

    Runs fetches concurrently. Each item gets a `pdf_text` key added.
    Failures are silently skipped — the announcement is kept without pdf_text.

    Args:
        items: List of raw announcement dicts.

    Returns:
        Same list with `pdf_text` populated where available.
    """
    tasks = [_fetch_pdf_text(item.get("pdf_url") or "") for item in items]
    texts = await asyncio.gather(*tasks, return_exceptions=True)
    for item, text in zip(items, texts):
        item["pdf_text"] = text if isinstance(text, str) else ""
    return items


async def _fetch_pdf_text(url: str) -> str:
    """
    Download a PDF from an approved NSE/BSE domain and extract the first 1000 chars.

    Args:
        url: Absolute URL to the PDF file.

    Returns:
        Extracted text (up to _PDF_MAX_CHARS), or "" on any failure.

    Raises:
        Nothing — all exceptions caught and logged at DEBUG level.
    """
    if not url or not url.lower().endswith(".pdf"):
        return ""

    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""

    if not any(domain == d or domain.endswith("." + d) for d in _PDF_ALLOWED_DOMAINS):
        logger.debug("_fetch_pdf_text: skipping unapproved domain %s", domain)
        return ""

    try:
        import io
        import httpx
        import pypdf

        async with httpx.AsyncClient(timeout=_PDF_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

        reader = pypdf.PdfReader(io.BytesIO(resp.content))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) >= _PDF_MAX_CHARS:
                break

        full_text = " ".join(parts).strip()
        return full_text[:_PDF_MAX_CHARS]

    except Exception as exc:
        logger.debug("_fetch_pdf_text: failed for %s — %s", url, exc)
        return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _try_bse_code(symbol: str) -> str | None:
    try:
        return await bse_client.resolve_scrip_code(symbol)
    except Exception:
        return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f
    except (ValueError, TypeError):
        return None
