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
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

TTL_SENTIMENT = 3600  # 1 hour
_CLI_TIMEOUT = 20     # seconds per subprocess call
_MAX_RETRIES = 3      # retry attempts on CLI failure

# ── Import guard: vaderSentiment ─────────────────────────────────────────────
_vader = None
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
except ImportError:
    logger.warning("vaderSentiment not installed — all scores will default to 0.0")

from cache.redis_client import cache_get, cache_set


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
    if len(cleaned) < 20:
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

    finance_markers = [
        "stock", "share", "buy", "sell", "hold", "target", "results", "earnings",
        "revenue", "profit", "valuation", "pe", "p/e", "nse", "bse", "bullish", "bearish",
    ]
    has_finance_context = any(marker in low for marker in finance_markers)

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
    cleaned = re.sub(r"http\S+", "", str(text))
    cleaned = re.sub(r"[#@]\w+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


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


def _fallback_source(source: str) -> dict:
    """Returns a valid empty fallback dict for 'reddit' or 'twitter'."""
    source_label = "Reddit" if source == "reddit" else "Twitter/X"
    return {
        "posts": [],
        "summary": f"No meaningful {source_label} data available right now.",
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
        logger.warning("rdt CLI not found — skipping Reddit sentiment")
        return []

    company_name = _get_company_name(symbol)
    # Try two queries: symbol-specific, then company name if different
    queries = [f"{symbol} NSE stock"]
    if company_name != symbol:
        queries.append(f"{company_name} India stock")

    all_posts: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for query in queries:
        raw = _run_cli([cli, "search", query, "--limit", "25", "--json"])
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if not parsed.get("ok"):
                logger.warning(f"rdt returned ok=false for query '{query}'")
                continue
            children = (
                parsed.get("data", {})
                      .get("data", {})
                      .get("children", [])
            )
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
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"rdt parse error for query '{query}': {e}")
            continue

    # Deduplicate by url
    seen: set[str] = set()
    unique: list[dict] = []
    for p in all_posts:
        key = p.get("url", p.get("text", "")[:60])
        if key not in seen:
            seen.add(key)
            unique.append(p)

    logger.info(f"Reddit: {len(unique)} posts fetched for {symbol}")
    return unique


# ── Twitter fetch ─────────────────────────────────────────────────────────────

def _fetch_twitter_sync(symbol: str) -> list[dict]:
    """
    Fetch recent Twitter/X posts via twitter CLI.
    Uses twitter search --json; returns unified post list or [] on any failure.
    """
    cli = _find_cli("twitter")
    if not cli:
        logger.warning("twitter CLI not found — skipping Twitter sentiment")
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
            posts.append({
                "text":   text[:500],
                "date":   post_dt.isoformat(),
                "url":    f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "",
                "source": "twitter",
            })

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"twitter parse error for {symbol}: {e}")
        return []

    logger.info(f"Twitter: {len(posts)} posts fetched for {symbol}")
    return posts


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
            "url":    p.get("url", ""),
            "source": source,
        })

    score  = _score_posts(raw_posts)
    signal = _score_to_signal(score)
    label  = _score_to_label(score)
    structured_summary = _build_structured_summary(enriched, signal, source)
    summary = _build_summary(enriched, signal, source)

    return {
        "posts":           enriched,
        "summary":         summary,
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
    reddit_key  = f"stock:sentiment:reddit:v3:{symbol}"
    twitter_key = f"stock:sentiment:twitter:v3:{symbol}"
    chart_key   = f"stock:sentiment:chart:v3:{symbol}"

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
