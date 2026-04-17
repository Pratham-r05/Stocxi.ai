"""
sentiment_service.py — Reddit + X/Twitter social sentiment for a stock symbol.

Data sources (no credentials required in the app):
  Reddit  → rdt CLI  (rdt-cli, pipx install rdt-cli)
  Twitter → twitter CLI (twitter-cli, pipx install twitter-cli)

Both CLIs are called as subprocesses and return JSON.
Window: Last 7 days only (filtered client-side for Reddit, recency-based for Twitter)
Sentiment: vaderSentiment — compound score aggregated across posts
Signal: score > 0.15 → BUY | score < -0.15 → AVOID | else → HOLD

MUST NEVER FAIL: every public function returns a valid dict even on total error.
Cache keys:
  stock:sentiment:reddit:{symbol}    TTL: 3600s
  stock:sentiment:twitter:{symbol}   TTL: 3600s
  stock:sentiment:chart:{symbol}     TTL: 3600s
"""

import asyncio
from collections import Counter
from html import unescape
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

TTL_SENTIMENT = 3600  # 1 hour
_CLI_TIMEOUT = 20     # seconds per subprocess call
_MAX_RETRIES = 3      # retry attempts on CLI failure
_SOCIAL_TIMEOUT = 10
_SOCIAL_MAX_ITEMS = 30

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# ── Import guard: vaderSentiment ─────────────────────────────────────────────
_vader = None
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except ImportError:
    logger.warning("vaderSentiment not installed — all scores will default to 0.0")

from cache.redis_client import cache_get, cache_set
from config import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


_ai_client = None
if OpenAI is not None and getattr(settings, "openrouter_api_key", None):
    try:
        _ai_client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
    except Exception as e:
        logger.warning(f"Sentiment AI client init failed: {e}")


# ── CLI discovery ─────────────────────────────────────────────────────────────

def _find_cli(name: str) -> str | None:
    """Find a CLI executable; checks PATH first, then common pipx locations."""
    # 1. Check PATH
    found = shutil.which(name)
    if found:
        return found
    # 2. pipx default location
    local_bin = os.path.expanduser(f"~/.local/bin/{name}")
    if os.path.isfile(local_bin) and os.access(local_bin, os.X_OK):
        return local_bin
    # 3. Homebrew / macOS locations
    for prefix in ("/usr/local/bin", "/opt/homebrew/bin"):
        candidate = os.path.join(prefix, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# ── Subprocess runner with retry ──────────────────────────────────────────────

def _run_cli(cmd: list[str], retries: int = _MAX_RETRIES) -> str | None:
    """
    Run a CLI command, return stdout as string.
    Retries up to `retries` times on non-zero exit or timeout.
    Returns None on total failure — never raises.
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_CLI_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            stderr = result.stderr.strip()[:200]
            logger.warning(
                f"CLI attempt {attempt}/{retries} failed (exit {result.returncode}): "
                f"{' '.join(cmd[:3])} — {stderr}"
            )
            last_error = stderr
        except subprocess.TimeoutExpired:
            logger.warning(f"CLI timeout on attempt {attempt}/{retries}: {' '.join(cmd[:3])}")
            last_error = "timeout"
        except Exception as e:
            logger.warning(f"CLI error on attempt {attempt}/{retries}: {e}")
            last_error = str(e)
    logger.error(f"CLI gave up after {retries} attempts: {' '.join(cmd[:3])} — {last_error}")
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_company_name(symbol: str) -> str:
    """Resolves NSE symbol → company name via yfinance; returns symbol on fail."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{symbol}.NS")
        name = (
            getattr(ticker.fast_info, "company_name", None)
            or ticker.info.get("longName")
        )
        return name.strip() if name else symbol
    except Exception:
        return symbol


def _score_posts(posts: list[dict]) -> float:
    """Runs vaderSentiment on post texts; returns average compound score (0.0 on fail)."""
    if not posts or _vader is None:
        return 0.0
    scores = []
    for post in posts:
        text = str(post.get("text", "")).strip()
        if not text:
            continue
        try:
            compound = _vader.polarity_scores(text).get("compound", 0.0)
            # NaN guard
            if compound != compound:
                compound = 0.0
            scores.append(compound)
        except Exception:
            scores.append(0.0)
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _score_to_signal(score: float) -> str:
    """Maps float compound score to BUY/HOLD/AVOID string (thresholds: ±0.15)."""
    if score > 0.15:
        return "BUY"
    if score < -0.15:
        return "AVOID"
    return "HOLD"


def _score_to_label(score: float) -> str:
    """Maps float compound score to Positive/Negative/Neutral string."""
    if score > 0.05:
        return "Positive"
    if score < -0.05:
        return "Negative"
    return "Neutral"


def _score_text(text: str) -> float:
    """Score a single text string; returns 0.0 if vader unavailable or on error."""
    if not _vader or not text:
        return 0.0
    try:
        compound = _vader.polarity_scores(str(text)).get("compound", 0.0)
        return 0.0 if compound != compound else round(compound, 4)
    except Exception:
        return 0.0


def _is_relevant_market_post(text: str, symbol: str, company_name: str) -> bool:
    """Checks if a post is likely a real market opinion for the target stock."""
    cleaned = _clean_summary_text(text)
    if not _is_informative_social_text(cleaned):
        return False

    low = cleaned.lower()

    # Filter obvious prompt-engineering / coding noise that is not investor sentiment.
    noise_markers = [
        "claude code",
        "chatgpt",
        "prompt",
        "using ai",
        "build me",
        "code to analyse",
        "display depends on the prompt",
    ]
    if any(marker in low for marker in noise_markers):
        return False

    # Reject non-investing chatter that often appears in symbol/company searches.
    non_market_markers = [
        "interview",
        "placement",
        "off campus",
        "on campus",
        "hackwith",
        "hackathon",
        "internship",
        "job opening",
        "hiring",
        "resume",
        "cv",
        "referral",
        "salary",
        "ctc",
        "leetcode",
        "dsa",
    ]
    if any(marker in low for marker in non_market_markers):
        return False

    has_finance_context = _has_finance_context(low)

    symbol_l = symbol.lower().strip()
    has_symbol = bool(symbol_l and re.search(rf"\b{re.escape(symbol_l)}\b", low))

    company_l = company_name.lower().strip()
    company_tokens = [
        tok for tok in re.split(r"[^a-z0-9]+", company_l)
        if tok and len(tok) >= 3 and tok not in {"limited", "ltd", "india", "the", "and"}
    ]
    token_hits = sum(1 for tok in company_tokens if re.search(rf"\b{re.escape(tok)}\b", low))
    has_company_context = (token_hits >= 2) or (company_l and company_l in low)

    # Require context + stock mention (symbol or enough company-token matches).
    return has_finance_context and (has_symbol or has_company_context)


def _clean_summary_text(text: str) -> str:
    """Cleans social text to readable snippet for summaries."""
    if not text:
        return ""
    cleaned = unescape(str(text))
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"http\S+", "", cleaned)
    cleaned = re.sub(r"[#@]\w+", "", cleaned)
    cleaned = re.sub(r"\b(?:x\.com|twitter\.com|reddit\.com)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[|•·]+\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _has_finance_context(low_text: str) -> bool:
    """Check if text carries stock-market context."""
    finance_markers = [
        "stock", "share", "buy", "sell", "hold", "target", "results", "earnings",
        "revenue", "profit", "valuation", "pe", "p/e", "nse", "bse", "bullish", "bearish",
        "ipo", "q1", "q2", "q3", "q4", "guidance", "margin", "brokerage", "market cap",
    ]
    return any(marker in low_text for marker in finance_markers)


def _is_informative_social_text(cleaned_text: str) -> bool:
    """Reject noisy social chatter and keep only informative investor posts."""
    if len(cleaned_text) < 28:
        return False

    low = cleaned_text.lower()
    noise_markers = [
        "liked this post",
        "proud moment",
        "follow me",
        "subscribe",
        "giveaway",
        "coupon",
        "meme",
        "lol",
        "lmao",
        "happy birthday",
        "good morning",
        "what a day",
    ]
    if any(marker in low for marker in noise_markers):
        return False

    letters = re.sub(r"[^a-zA-Z]", "", cleaned_text)
    if len(letters) < 18:
        return False

    return _has_finance_context(low)


def _looks_like_target_stock_post(text: str, symbol: str, company_name: str) -> bool:
    """Relaxed relevance check for fallback sources where metadata is sparse."""
    cleaned = _clean_summary_text(text)
    if not _is_informative_social_text(cleaned):
        return False

    low = cleaned.lower()
    if not low:
        return False

    symbol_l = symbol.lower().strip()
    has_symbol = bool(symbol_l and re.search(rf"\b{re.escape(symbol_l)}\b", low))

    company_l = company_name.lower().strip()
    company_tokens = [
        tok for tok in re.split(r"[^a-z0-9]+", company_l)
        if tok and len(tok) >= 4 and tok not in {"limited", "india", "retail", "ltd"}
    ]
    token_hits = sum(1 for tok in company_tokens if re.search(rf"\b{re.escape(tok)}\b", low))
    has_company = (token_hits >= 1) or (company_l and company_l in low)

    return has_symbol or has_company


def _rss_pub_to_iso(pub_date: str) -> str:
    """Parse RSS pubDate to ISO string; returns raw date on parse failure."""
    raw = str(pub_date or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return raw


def _is_valid_source_url(url: str, source: str) -> bool:
    """Strict URL validator per social source to avoid broken/irrelevant links."""
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (parsed.path or "").lower()
    except Exception:
        return False

    if source == "twitter":
        return host in {"x.com", "twitter.com", "mobile.twitter.com"} and "/status/" in path
    if source == "reddit":
        return "reddit.com" in host
    return bool(host)


def _fetch_social_from_google_news(symbol: str, source: str) -> list[dict]:
    """Fetch Reddit/X links via Google News RSS, deploy-safe fallback for serverless."""
    company_name = _get_company_name(symbol)
    after_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    if source == "reddit":
        site_filter = "site:reddit.com"
    else:
        site_filter = "(site:x.com OR site:twitter.com)"

    query = f"({symbol} OR \"{company_name}\") stock india {site_filter} after:{after_date}"
    url = (
        "https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=_SOCIAL_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        logger.warning(f"Google News social fallback failed for {symbol} {source}: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    items: list[dict] = []
    seen_urls: set[str] = set()

    for item in root.findall(".//item")[:_SOCIAL_MAX_ITEMS]:
        title = str(item.findtext("title", "")).strip()
        link = str(item.findtext("link", "")).strip()
        pub_date = str(item.findtext("pubDate", "")).strip()
        description = str(item.findtext("description", "")).strip()
        source_el = item.find("source")
        source_url = ""
        source_name = ""
        if source_el is not None:
            source_url = str(source_el.attrib.get("url", "")).strip().lower()
            source_name = str(source_el.text or "").strip().lower()

        if not title or not link or link in seen_urls:
            continue

        low_link = link.lower()
        source_hint = " ".join([source_url, source_name, low_link])
        if source == "reddit":
            if "reddit.com" not in source_hint:
                continue
        else:
            if "x.com" not in source_hint and "twitter.com" not in source_hint:
                continue

        if not _is_valid_source_url(link, source):
            continue

        text = _clean_summary_text(f"{title} {description}")
        if not _looks_like_target_stock_post(text, symbol, company_name):
            continue

        post_iso = _rss_pub_to_iso(pub_date)
        try:
            parsed_dt = datetime.fromisoformat(post_iso.replace("Z", "+00:00"))
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            if parsed_dt < cutoff:
                continue
        except Exception:
            pass

        seen_urls.add(link)
        items.append({
            "text": text[:500],
            "date": post_iso,
            "url": link,
            "source": source,
        })

    logger.info(f"Google News social fallback: {len(items)} posts for {symbol} {source}")
    return items


def _short_snippet(text: str, limit: int = 120) -> str:
    """Returns a clipped snippet preserving whole-word readability."""
    txt = _clean_summary_text(text)
    if len(txt) <= limit:
        return txt
    clipped = txt[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped}..." if clipped else f"{txt[:limit]}..."


def _extract_themes(posts: list[dict]) -> list[str]:
    """Extracts top discussion themes from post texts using keyword buckets."""
    theme_keywords = {
        "Earnings": ["result", "earnings", "profit", "revenue", "margin", "q1", "q2", "q3", "q4"],
        "Valuation": ["valuation", "undervalued", "overvalued", "pe", "p/e", "expensive", "cheap"],
        "Momentum": ["trend", "momentum", "breakout", "support", "resistance", "rsi", "macd"],
        "Business Growth": ["order", "deal", "guidance", "capex", "demand", "expansion", "market share"],
        "Risk": ["risk", "debt", "pledge", "penalty", "lawsuit", "regulation", "selloff"],
        "Income": ["dividend", "yield", "buyback"],
    }

    counts: Counter[str] = Counter()
    for post in posts:
        text = _clean_summary_text(post.get("text", "")).lower()
        if not text:
            continue
        for theme, keywords in theme_keywords.items():
            if any(k in text for k in keywords):
                counts[theme] += 1

    return [theme for theme, _ in counts.most_common(3)]


def _build_structured_summary(posts: list[dict], signal: str, source: str) -> dict:
    """Builds structured sentiment insights for beginner-friendly UI rendering."""
    source_label = "Reddit" if source == "reddit" else "Twitter/X"
    total_posts = len(posts)

    if total_posts == 0:
        return {
            "overall_view": f"No meaningful {source_label} discussions were found in the last 7 days.",
            "investor_takeaway": "Treat social sentiment as unavailable and rely more on fundamentals + technicals.",
            "key_themes": [],
            "bullish_points": [],
            "risk_points": [],
            "key_discussions": [],
        }

    scored: list[tuple[str, float]] = []
    seen_texts: set[str] = set()
    for post in posts:
        raw = post.get("text", "")
        cleaned = _clean_summary_text(raw)
        if len(cleaned) < 16:
            continue
        key = cleaned.lower()
        if key in seen_texts:
            continue
        seen_texts.add(key)
        val = post.get("score", 0.0)
        score = float(val) if isinstance(val, (int, float)) else _score_text(cleaned)
        scored.append((cleaned, score))

    bullish = [_short_snippet(t) for t, s in sorted(scored, key=lambda x: x[1], reverse=True) if s > 0.10][:3]
    risks = [_short_snippet(t) for t, s in sorted(scored, key=lambda x: x[1]) if s < -0.10][:3]
    discussions = [_short_snippet(t) for t, _ in scored[:4]]
    themes = _extract_themes(posts)

    pos = sum(1 for _, s in scored if s > 0.05)
    neg = sum(1 for _, s in scored if s < -0.05)
    neu = max(0, len(scored) - pos - neg)

    if signal == "BUY":
        overall = f"{source_label} crowd mood is mildly bullish with more optimistic than negative commentary."
        takeaway = "Retail discussion is supportive, but confirm with earnings quality and valuation before buying."
    elif signal == "AVOID":
        overall = f"{source_label} crowd mood is cautious to bearish with concerns dominating discussions."
        takeaway = "Sentiment is weak; wait for clearer reversal signals or stronger business updates."
    else:
        overall = f"{source_label} crowd mood is neutral/mixed with no strong directional consensus."
        takeaway = "Use social chatter as context only; decision should depend on fundamentals, trend, and risk appetite."

    if scored:
        overall = f"{overall} Post mix: {pos} positive, {neg} negative, {neu} neutral from {len(scored)} readable posts."

    return {
        "overall_view": overall,
        "investor_takeaway": takeaway,
        "key_themes": themes,
        "bullish_points": bullish,
        "risk_points": risks,
        "key_discussions": discussions,
    }


def _build_summary(posts: list[dict], signal: str, source: str) -> str:
    """Builds a concise plain-English summary string for backward compatibility."""
    if not posts:
        source_label = "Reddit" if source == "reddit" else "Twitter/X"
        return f"No meaningful {source_label} sentiment was found in the last 7 days."

    structured = _build_structured_summary(posts, signal, source)
    themes = structured.get("key_themes", [])
    themes_txt = f" Top themes: {', '.join(themes)}." if themes else ""
    return f"{structured.get('overall_view', '')} {structured.get('investor_takeaway', '')}{themes_txt}".strip()


def _build_summary_lines(
    *,
    source: str,
    signal: str,
    sentiment: str,
    score: float,
    posts: list[dict],
    structured_summary: dict,
) -> list[str]:
    """Build concise source-specific summary lines for UI tabs."""
    source_label = "Reddit" if source == "reddit" else "Twitter/X"
    themes = structured_summary.get("key_themes", []) if isinstance(structured_summary, dict) else []
    bullish = structured_summary.get("bullish_points", []) if isinstance(structured_summary, dict) else []
    risks = structured_summary.get("risk_points", []) if isinstance(structured_summary, dict) else []
    discussions = structured_summary.get("key_discussions", []) if isinstance(structured_summary, dict) else []
    overall = (structured_summary.get("overall_view", "") if isinstance(structured_summary, dict) else "").strip()
    takeaway = (structured_summary.get("investor_takeaway", "") if isinstance(structured_summary, dict) else "").strip()

    lines: list[str] = [
        f"From {source_label}, {len(posts)} relevant market discussions were analyzed from the last 7 days.",
        f"Overall signal is {signal} with a {sentiment.lower()} mood and sentiment score {score:+.2f}.",
        overall or "Overall discussion was mixed without a strong consensus.",
        takeaway or "Use this sentiment as supporting context, not as the only decision input.",
        f"Main themes discussed: {', '.join(themes)}." if themes else "Main themes were scattered and did not cluster strongly.",
        f"Bullish side: {bullish[0]}" if bullish else "Bullish side had no strong high-confidence point repeated across posts.",
        f"Risk side: {risks[0]}" if risks else "Risk side had no dominant bearish point repeated across posts.",
        f"Most repeated discussion point: {discussions[0]}" if discussions else "No single discussion point dominated, opinions were fragmented.",
    ]

    return lines[:8]


def _parse_ai_lines(raw_text: str) -> list[str]:
    """Parse AI output into clean line list (JSON array preferred, text fallback)."""
    text = (raw_text or "").strip()
    if not text:
        return []

    # Try direct JSON array first.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass

    # Try extracting a JSON array from mixed content.
    arr_match = re.search(r"\[[\s\S]*\]", text)
    if arr_match:
        try:
            parsed = json.loads(arr_match.group(0))
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

    # Fallback: split plain text lines and strip list prefixes.
    out: list[str] = []
    for line in text.splitlines():
        clean = re.sub(r"^\s*(?:[-*]|\d+[\.)])\s*", "", line).strip()
        if clean:
            out.append(clean)
    return out


def _build_ai_summary_lines(
    *,
    source: str,
    symbol: str,
    signal: str,
    sentiment: str,
    score: float,
    posts: list[dict],
) -> list[str] | None:
    """Generate exactly 10 concise source summary lines using OpenRouter; return None on any failure."""
    if _ai_client is None or not posts:
        return None

    source_label = "Reddit" if source == "reddit" else "Twitter/X"
    compact_posts = []
    for p in posts[:10]:
        txt = _short_snippet(p.get("text", ""), 180)
        if not txt:
            continue
        compact_posts.append(
            {
                "text": txt,
                "date": str(p.get("date", ""))[:10],
                "url": p.get("url", ""),
            }
        )

    if not compact_posts:
        return None

    prompt = (
        f"Summarize last-7-days {source_label} investor discussion for stock {symbol}.\n"
        f"Signal={signal}, Sentiment={sentiment}, Score={score:+.2f}.\n"
        "Return EXACTLY a JSON array with 10 short strings (one insight per string).\n"
        "No markdown, no extra keys, no numbering.\n"
        f"Posts JSON: {json.dumps(compact_posts, ensure_ascii=False)}"
    )

    try:
        resp = _ai_client.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": "You are a precise market summary assistant. Output strict JSON array only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=380,
            timeout=8,
        )
        content = ""
        if resp and resp.choices and resp.choices[0].message:
            content = resp.choices[0].message.content or ""
        lines = _parse_ai_lines(content)
        if not lines:
            return None
        lines = lines[:10]
        while len(lines) < 10:
            lines.append("No additional high-confidence insight from available posts.")
        return lines
    except Exception as e:
        logger.warning(f"AI summary generation failed for {symbol} {source}: {e}")
        return None


def _fallback_source(source: str) -> dict:
    """Returns a valid empty fallback dict for 'reddit' or 'twitter'."""
    source_label = "Reddit" if source == "reddit" else "Twitter/X"
    return {
        "posts": [],
        "summary": f"No meaningful {source_label} data available right now.",
        "summary_lines": [
            f"No credible {source_label} posts were found in the last 7 days for this stock.",
            "Current social signal stays HOLD with neutral sentiment due to insufficient reliable discussion volume.",
            "No trustworthy bullish argument appeared repeatedly across recent posts.",
            "No trustworthy bearish argument appeared repeatedly across recent posts.",
            "No stable theme emerged from this source in the selected window.",
            "Use fundamentals, technical indicators, and official news as primary decision inputs for now.",
            "Treat this as temporary social-data unavailability, not as a directional market signal.",
            "Refresh later when new posts with real market context are available.",
        ],
        "structured_summary": {
            "overall_view": f"No meaningful {source_label} discussions were found in the last 7 days.",
            "investor_takeaway": "Use fundamentals and technical indicators until social data is available.",
            "key_themes": [],
            "bullish_points": [],
            "risk_points": [],
            "key_discussions": [],
        },
        "sentiment": "Neutral",
        "sentiment_score": 0.0,
        "signal": "HOLD",
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Reddit fetch ──────────────────────────────────────────────────────────────

def _fetch_reddit_sync(symbol: str) -> list[dict]:
    """
    Fetch last-7-days Reddit posts via rdt CLI.
    Uses rdt search with --json flag; filters by created_utc client-side.
    Returns unified post list or [] on any failure.
    """
    cli = _find_cli("rdt")
    if not cli:
        logger.warning("rdt CLI not found — using Google News fallback for Reddit")
        return _fetch_social_from_google_news(symbol, "reddit")

    company_name = _get_company_name(symbol)
    queries_raw = [
        f"{symbol} NSE stock",
        f"{symbol} stock india",
        f"{symbol} nse",
        symbol,
    ]
    if company_name != symbol:
        queries_raw.extend([
            f"{company_name} India stock",
            f"{company_name} stock",
            company_name,
        ])

    queries: list[str] = []
    seen_q: set[str] = set()
    for q in queries_raw:
        q_norm = " ".join(q.split()).strip().lower()
        if q_norm and q_norm not in seen_q:
            seen_q.add(q_norm)
            queries.append(q.strip())

    all_posts: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for query in queries[:6]:
        after: str | None = None
        for _page in range(2):
            cmd = [cli, "search", query, "--limit", "25", "--json"]
            if after:
                cmd.extend(["--after", after])

            raw = _run_cli(cmd)
            if not raw:
                break
            try:
                parsed = json.loads(raw)
                if not parsed.get("ok"):
                    logger.warning(f"rdt returned ok=false for query '{query}'")
                    break

                listing_data = parsed.get("data", {}).get("data", {})
                children = listing_data.get("children", [])
                after = listing_data.get("after")

                if not isinstance(children, list) or not children:
                    break

                for child in children:
                    post = child.get("data", {})
                    # Filter by date
                    created_utc = post.get("created_utc", 0)
                    try:
                        post_dt = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
                    except Exception:
                        post_dt = datetime.now(timezone.utc)

                    if post_dt < cutoff:
                        continue

                    title = str(post.get("title", "")).strip()
                    body  = str(post.get("selftext", "")).strip()
                    text  = f"{title} {body}".strip() if body else title
                    if not text:
                        continue
                    if not _is_relevant_market_post(text, symbol, company_name):
                        continue

                    permalink = post.get("permalink", "")
                    all_posts.append({
                        "text":   text[:500],
                        "date":   post_dt.isoformat(),
                        "url":    f"https://reddit.com{permalink}" if permalink else "",
                        "source": "reddit",
                    })

                if not after:
                    break
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"rdt parse error for query '{query}': {e}")
                break

    # Deduplicate by url
    seen: set[str] = set()
    unique: list[dict] = []
    for p in all_posts:
        key = p.get("url", p.get("text", "")[:60])
        if key not in seen:
            seen.add(key)
            unique.append(p)

    logger.info(f"Reddit: {len(unique)} posts fetched for {symbol}")
    if unique:
        return unique

    logger.info(f"Reddit CLI returned 0 posts for {symbol}, trying fallback")
    return _fetch_social_from_google_news(symbol, "reddit")


# ── Twitter fetch ─────────────────────────────────────────────────────────────

def _fetch_twitter_sync(symbol: str) -> list[dict]:
    """
    Fetch recent Twitter/X posts via twitter CLI.
    Uses twitter search --json; returns unified post list or [] on any failure.
    """
    cli = _find_cli("twitter")
    if not cli:
        logger.warning("twitter CLI not found — returning no Twitter/X posts")
        return []

    company_name = _get_company_name(symbol)
    query = f"{symbol} NSE stock"
    if company_name != symbol:
        query = f"({symbol} OR {company_name}) NSE stock"

    raw = _run_cli([cli, "search", query, "-n", "25", "--json"])
    if not raw:
        # Fallback: try with just the symbol if complex query fails
        raw = _run_cli([cli, "search", f"{symbol} NSE", "-n", "25", "--json"])
    if not raw:
        logger.warning(f"twitter CLI returned no output for {symbol}")
        return []

    posts: list[dict] = []
    try:
        parsed = json.loads(raw)
        if not parsed.get("ok"):
            logger.warning(f"twitter CLI returned ok=false for {symbol}")
            return []

        items = parsed.get("data", [])
        if not isinstance(items, list):
            logger.warning(f"Unexpected twitter data type: {type(items)}")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        for item in items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            if not _is_relevant_market_post(text, symbol, company_name):
                continue

            # Parse date
            date_iso = item.get("createdAtISO", "")
            try:
                post_dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
            except Exception:
                post_dt = datetime.now(timezone.utc)

            if post_dt < cutoff:
                continue

            tweet_id = item.get("id", "")
            url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""
            if url and not _is_valid_source_url(url, "twitter"):
                url = ""

            posts.append({
                "text":   text[:500],
                "date":   post_dt.isoformat(),
                "url":    url,
                "source": "twitter",
            })

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"twitter parse error for {symbol}: {e}")
        return []

    logger.info(f"Twitter: {len(posts)} posts fetched for {symbol}")
    if posts:
        return posts

    logger.info(f"Twitter CLI returned 0 valid posts for {symbol}")
    return []


# ── Processing ────────────────────────────────────────────────────────────────

def _process_source(raw_posts: list[dict], source: str) -> dict:
    """Scores + summarizes a list of posts into the unified schema dict."""
    enriched: list[dict] = []
    for p in raw_posts:
        text = p.get("text", "")
        item_score = _score_text(text)
        enriched.append({
            "text":   text,
            "score":  item_score,
            "date":   p.get("date", ""),
            "created_at": p.get("date", ""),
            "url":    p.get("url", ""),
            "source": source,
        })

    score  = _score_posts(raw_posts)
    signal = _score_to_signal(score)
    label  = _score_to_label(score)
    structured_summary = _build_structured_summary(enriched, signal, source)
    summary = _build_summary(enriched, signal, source)
    fallback_lines = _build_summary_lines(
        source=source,
        signal=signal,
        sentiment=label,
        score=score,
        posts=enriched,
        structured_summary=structured_summary,
    )
    summary_lines = fallback_lines

    return {
        "posts":           enriched,
        "summary":         summary,
        "summary_lines":   summary_lines,
        "structured_summary": structured_summary,
        "sentiment":       label,
        "sentiment_score": score,
        "signal":          signal,
        "source":          source,
        "fetched_at":      datetime.now(timezone.utc).isoformat(),
    }


def _build_chart_data(reddit_data: dict, twitter_data: dict) -> list[dict]:
    """
    Builds 7-day daily chart data by grouping posts per day and averaging scores.
    Always returns exactly 7 entries (one per day), with 0.0 for days with no posts.
    """
    today = datetime.now(timezone.utc).date()
    days  = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

    reddit_by_day:  dict[str, list[float]] = {d: [] for d in days}
    twitter_by_day: dict[str, list[float]] = {d: [] for d in days}

    for post in reddit_data.get("posts", []):
        try:
            day = str(post.get("date", ""))[:10]
            if day in reddit_by_day:
                reddit_by_day[day].append(float(post.get("score", 0.0)))
        except Exception:
            pass

    for post in twitter_data.get("posts", []):
        try:
            day = str(post.get("date", ""))[:10]
            if day in twitter_by_day:
                twitter_by_day[day].append(float(post.get("score", 0.0)))
        except Exception:
            pass

    chart: list[dict] = []
    for day in days:
        r = reddit_by_day[day]
        t = twitter_by_day[day]
        chart.append({
            "date":          day,
            "reddit_score":  round(sum(r) / len(r), 4) if r else 0.0,
            "twitter_score": round(sum(t) / len(t), 4) if t else 0.0,
        })
    return chart


# ── Public async API ──────────────────────────────────────────────────────────

async def get_sentiment(symbol: str, force_refresh: bool = False) -> dict:
    """
    Async public entry — fetches Reddit + Twitter in parallel via CLI subprocess.
    Caches results per source. Returns combined sentiment dict.
    NEVER raises — returns valid fallback structure on any/all errors.
    """
    symbol = symbol.upper().strip()

    # ── Cache check ───────────────────────────────────────────────────────────
    reddit_key  = f"stock:sentiment:reddit:v5:{symbol}"
    twitter_key = f"stock:sentiment:twitter:v5:{symbol}"
    chart_key   = f"stock:sentiment:chart:v5:{symbol}"

    cached_reddit  = await cache_get(reddit_key)
    cached_twitter = await cache_get(twitter_key)
    cached_chart   = await cache_get(chart_key)

    if (not force_refresh) and cached_reddit and cached_twitter and cached_chart:
        logger.info(f"Cache hit: sentiment for {symbol}")
        reddit_data  = cached_reddit
        twitter_data = cached_twitter
        chart_data   = cached_chart
    else:
        # ── Fetch both sources concurrently in thread pool ────────────────────
        loop = asyncio.get_event_loop()
        try:
            reddit_raw, twitter_raw = await asyncio.gather(
                loop.run_in_executor(None, _fetch_reddit_sync, symbol),
                loop.run_in_executor(None, _fetch_twitter_sync, symbol),
                return_exceptions=True,
            )
        except Exception as e:
            logger.error(f"Sentiment gather failed for {symbol}: {e}")
            reddit_raw  = []
            twitter_raw = []

        # Handle any exceptions returned by gather
        if isinstance(reddit_raw, Exception):
            logger.warning(f"Reddit gather exception for {symbol}: {reddit_raw}")
            reddit_raw = []
        if isinstance(twitter_raw, Exception):
            logger.warning(f"Twitter gather exception for {symbol}: {twitter_raw}")
            twitter_raw = []

        # Guaranteed valid list at this point
        reddit_raw  = reddit_raw  if isinstance(reddit_raw,  list) else []
        twitter_raw = twitter_raw if isinstance(twitter_raw, list) else []

        reddit_data  = _process_source(reddit_raw,  "reddit")
        twitter_data = _process_source(twitter_raw, "twitter")

        # Keep deterministic summary lines for consistency and predictable quality.
        chart_data   = _build_chart_data(reddit_data, twitter_data)

        # ── Cache results ─────────────────────────────────────────────────────
        await cache_set(reddit_key,  reddit_data,  TTL_SENTIMENT)
        await cache_set(twitter_key, twitter_data, TTL_SENTIMENT)
        await cache_set(chart_key,   chart_data,   TTL_SENTIMENT)

    # ── Combined signal (average of both scores) ──────────────────────────────
    r_score = float(reddit_data.get("sentiment_score", 0.0))
    t_score = float(twitter_data.get("sentiment_score", 0.0))
    combined_score  = round((r_score + t_score) / 2, 4)
    combined_signal = _score_to_signal(combined_score)

    return {
        "reddit":                   reddit_data,
        "twitter":                  twitter_data,
        "combined_signal":          combined_signal,
        "combined_sentiment_score": combined_score,
        "chart_data":               chart_data,
    }
