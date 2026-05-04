"""
news_service.py — Top-10 stock news with LLM summarization.

Waterfall (L1 → L2 → L3):
  L1: gnews (Google News via Python lib; free, no API key; confidence=0.65)
  L2: newsdata.io REST API  (NEWSDATA_API_KEY required; confidence=0.80)
  L3: Google News RSS        (free; confidence=0.50)

For each article the service:
  1. Fetches via waterfall.
  2. Runs deterministic key_sentence extraction (article_extractor).
  3. Batch-summarizes via Gemini 2.5 Pro: 5-line summary + relevance score
     + signal classification + horizon relevance per article.
  4. Returns enriched dicts ready for agent_news node building.

Max 10 articles returned, sorted newest-first.
Never raises — returns [] on complete failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests
import yaml
from gnews import GNews

from fetchers.newsdata_client import fetch_stock_news
from util.article_extractor import derive_stock_impact, extract_key_sentence

logger = logging.getLogger(__name__)

_MAX_NEWS       = 10
_MAX_AGE_DAYS   = 7
_TIMEOUT        = 10
_HEADERS        = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Signal-class keywords (mirrors agent_news._CLASS_KEYWORDS for impact lookup)
_CLASS_KEYWORDS: list[tuple[str, list[str]]] = [
    ("regulatory_sebi_action", ["sebi", "penalty", "investigation", "ban", "enforcement",
                                 "adjudication", "insider trading", "show cause"]),
    ("fraud_allegation",       ["fraud", "scam", "irregularity", "misappropriation",
                                 "embezzlement", "manipulation", "siphon"]),
    ("credit_rating_change",   ["downgrade", "upgrade", "crisil", "icra", "care ratings",
                                 "fitch", "moody", "credit rating", "rating action"]),
    ("leadership_change",      ["ceo", "chief executive", "cfo", "chief financial",
                                 "managing director", "chairman", "resignation",
                                 "quits", "appoints", "board change"]),
    ("ma_event",               ["merger", "acquisition", "takeover", "demerger",
                                 "amalgamation", "joint venture", "strategic alliance"]),
    ("major_contract",         ["bags order", "wins contract", "secures deal",
                                 "order win", "major contract", "new order"]),
    ("dividend_or_buyback",    ["dividend", "buyback", "buy-back", "bonus share",
                                 "special dividend", "interim dividend"]),
]


# ── Public async entry point ─────────────────────────────────��────────────────

async def get_news(symbol: str, company_name: str | None = None) -> list[dict[str, Any]]:
    """
    Fetch and enrich top-10 news articles for a stock, async entry point.

    Runs the waterfall (newsdata.io → Google News RSS) in a thread pool,
    then extracts key_sentence + stock_impact for each article.

    Args:
        symbol:       NSE ticker (e.g. "RELIANCE").
        company_name: Full company name for broader matching.

    Returns:
        list[dict] with fields: title, description, content, key_sentence,
        stock_impact, link, published, source, source_name, signal_class.
        Empty list on complete failure.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _get_news_sync, symbol, company_name or ""
    )


# ── Sync pipeline ───────────────────────────────────────────────────────────��─

def _get_news_sync(symbol: str, company_name: str) -> list[dict[str, Any]]:
    """
    Sync waterfall: gnews → newsdata.io → Google News RSS, then LLM enrichment.

    Pipeline:
      1. Fetch via waterfall (gnews L1 → newsdata.io L2 → Google RSS L3)
      2. Normalise + relevance filter
      3. Heuristic enrichment (key_sentence, stock_impact, signal_class)
      4. LLM batch summarization (5-line summary, relevance score, refined
         signal class, horizon relevance per article)

    Args:
        symbol:       NSE ticker.
        company_name: Full company name (may be empty string).

    Returns:
        Enriched article list (max 10) with LLM summaries where available.
    """
    symbol = symbol.upper().strip()

    # L1: gnews (free, no API key, reliable for Indian stocks)
    raw_articles = _fetch_gnews(symbol, company_name)
    if raw_articles:
        logger.info("news_service: gnews → %d articles for %s", len(raw_articles), symbol)
        enriched = _enrich(raw_articles, symbol, company_name)
        return _summarize_articles(enriched, symbol)

    # L2: newsdata.io (rate-limited, may fail on free tier)
    logger.info("news_service: gnews empty for %s, trying newsdata.io", symbol)
    result = fetch_stock_news(symbol, company_name)
    if result.ok:
        raw_articles = _normalise_newsdata(result.payload, symbol, company_name)
        if raw_articles:
            logger.info("news_service: newsdata.io → %d articles for %s", len(raw_articles), symbol)
            enriched = _enrich(raw_articles, symbol, company_name)
            return _summarize_articles(enriched, symbol)

    # L3: Google News RSS (direct fetch)
    logger.info("news_service: newsdata.io empty/missing for %s, trying Google News RSS", symbol)
    raw_articles = _fetch_google_news_rss(symbol, company_name)
    if raw_articles:
        logger.info("news_service: Google News RSS → %d articles for %s", len(raw_articles), symbol)
        enriched = _enrich(raw_articles, symbol, company_name)
        return _summarize_articles(enriched, symbol)

    logger.warning("news_service: no news from any source for %s", symbol)
    return []


# ── Normalisers ────────────────────────────────��──────────────────────────────

def _normalise_newsdata(
    raw: list[dict[str, Any]],
    symbol: str,
    company_name: str,
) -> list[dict[str, Any]]:
    """
    Convert newsdata.io article dicts to the canonical intermediate format.

    Args:
        raw:          List of article dicts from newsdata_client.fetch_stock_news.
        symbol:       NSE ticker for relevance filtering.
        company_name: Company name for relevance filtering.

    Returns:
        Filtered, normalised list (newest-first, max 10).
    """
    articles: list[dict[str, Any]] = []
    for item in raw:
        title = item.get("title", "").strip()
        if not title:
            continue
        if not _is_relevant(title, symbol, company_name):
            continue

        pub_dt: datetime | None = item.get("pub_dt")
        published_iso = pub_dt.isoformat() if pub_dt else item.get("pubDate", "")

        articles.append({
            "title":       title,
            "description": item.get("description", ""),
            "content":     item.get("content", ""),
            "link":        item.get("link", ""),
            "published":   published_iso,
            "source":      item.get("source_id", "newsdata_io"),
            "source_name": item.get("source_name", ""),
            "sentiment":   item.get("sentiment", ""),   # may be empty on free tier
        })

    return articles[:_MAX_NEWS]


# NIFTY 100 company name lookup — used for gnews search query construction.
# Ticker → full company name. Keep alphabetically sorted.
_COMPANY_NAMES: dict[str, str] = {
    "ABB": "ABB India",
    "ACC": "ACC Limited",
    "ADANIENT": "Adani Enterprises",
    "ADANIGREEN": "Adani Green Energy",
    "ADANIPORTS": "Adani Ports",
    "ADANIPOWER": "Adani Power",
    "AMBUJACEM": "Ambuja Cements",
    "APOLLOHOSP": "Apollo Hospitals",
    "ASIANPAINT": "Asian Paints",
    "AXISBANK": "Axis Bank",
    "BAJAJ-AUTO": "Bajaj Auto",
    "BAJAJFINSV": "Bajaj Finserv",
    "BAJFINANCE": "Bajaj Finance",
    "BANKBARODA": "Bank of Baroda",
    "BEL": "Bharat Electronics",
    "BERGEPAINT": "Berger Paints",
    "BHARATFORG": "Bharat Forge",
    "BHARTIARTL": "Bharti Airtel",
    "BIOCON": "Biocon",
    "BOSCHLTD": "Bosch India",
    "BPCL": "Bharat Petroleum",
    "BRITANNIA": "Britannia Industries",
    "BSOFT": "Birlasoft",
    "CANBK": "Canara Bank",
    "CHOLAFIN": "Cholamandalam Finance",
    "CIPLA": "Cipla",
    "COALINDIA": "Coal India",
    "COFORGE": "Coforge",
    "COLPAL": "Colgate Palmolive India",
    "CONCOR": "Container Corporation of India",
    "CROMPTON": "Crompton Greaves",
    "CUMMINSIND": "Cummins India",
    "DABUR": "Dabur India",
    "DALBHARAT": "Dalmia Bharat",
    "DEEPAKNTR": "Deepak Nitrite",
    "DELHIVERY": "Delhivery",
    "DIVISLAB": "Divis Laboratories",
    "DIXON": "Dixon Technologies",
    "DLF": "DLF Limited",
    "DMART": "Avenue Supermarts",
    "DRREDDY": "Dr Reddys Laboratories",
    "EICHERMOT": "Eicher Motors",
    "EXIDEIND": "Exide Industries",
    "FEDERALBNK": "Federal Bank",
    "GAIL": "GAIL India",
    "GLENMARK": "Glenmark Pharmaceuticals",
    "GODREJCP": "Godrej Consumer Products",
    "GODREJPROP": "Godrej Properties",
    "GRASIM": "Grasim Industries",
    "HAL": "Hindustan Aeronautics",
    "HAVELLS": "Havells India",
    "HCLTECH": "HCL Technologies",
    "HDFCAMC": "HDFC Asset Management",
    "HDFCBANK": "HDFC Bank",
    "HDFCLIFE": "HDFC Life Insurance",
    "HEROMOTOCO": "Hero MotoCorp",
    "HINDALCO": "Hindalco Industries",
    "HINDCOPPER": "Hindustan Copper",
    "HINDPETRO": "Hindustan Petroleum",
    "HINDUNILVR": "Hindustan Unilever",
    "ICICIBANK": "ICICI Bank",
    "ICICIGI": "ICICI General Insurance",
    "ICICIPRULI": "ICICI Prudential Life",
    "IDEA": "Vodafone Idea",
    "IDFCFIRSTB": "IDFC First Bank",
    "IEX": "Indian Energy Exchange",
    "IGL": "Indraprastha Gas",
    "INDHOTEL": "Indian Hotels",
    "INDIANB": "Indian Bank",
    "INDIGO": "InterGlobe Aviation IndiGo",
    "INDUSINDBK": "IndusInd Bank",
    "INDUSTOWER": "Indus Towers",
    "INFY": "Infosys",
    "IOC": "Indian Oil Corporation",
    "IPCALAB": "IPCA Laboratories",
    "IRCTC": "Indian Railway Catering",
    "ITC": "ITC Limited",
    "JINDALSTEL": "Jindal Steel Power",
    "JIOFIN": "Jio Financial Services",
    "JSL": "Jindal Stainless",
    "JSWENERGY": "JSW Energy",
    "JSWSTEEL": "JSW Steel",
    "JUBLFOOD": "Jubilant FoodWorks",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "LT": "Larsen Toubro",
    "LTIM": "LTIMindtree",
    "LTTS": "L&T Technology Services",
    "LICI": "Life Insurance Corporation",
    "LUPIN": "Lupin Limited",
    "M&M": "Mahindra Mahindra",
    "M&MFIN": "Mahindra Mahindra Finance",
    "MANAPPURAM": "Manappuram Finance",
    "MARICO": "Marico Limited",
    "MARUTI": "Maruti Suzuki",
    "MAXHEALTH": "Max Healthcare",
    "MCDOWELL-N": "United Spirits",
    "MCX": "Multi Commodity Exchange",
    "METROBRAND": "Metro Brands",
    "MFSL": "Max Financial Services",
    "MGL": "Mahanagar Gas",
    "MOTHERSON": "Samvardhana Motherson",
    "MPHASIS": "Mphasis Limited",
    "MRF": "MRF Limited",
    "MUTHOOTFIN": "Muthoot Finance",
    "NATIONALUM": "National Aluminium",
    "NAUKRI": "Info Edge India",
    "NESTLEIND": "Nestle India",
    "NTPC": "NTPC Limited",
    "OBEROIRLTY": "Oberoi Realty",
    "OFSS": "Oracle Financial Services",
    "ONGC": "Oil and Natural Gas Corporation",
    "PAGEIND": "Page Industries",
    "PAYTM": "One97 Communications Paytm",
    "PEL": "Piramal Enterprises",
    "PERSISTENT": "Persistent Systems",
    "PETRONET": "Petronet LNG",
    "PFC": "Power Finance Corporation",
    "PIDILITIND": "Pidilite Industries",
    "PIIND": "PI Industries",
    "PNB": "Punjab National Bank",
    "POLICYBZR": "PB Fintech PolicyBazaar",
    "POLYCAB": "Polycab India",
    "POONAWALLA": "Poonawalla Fincorp",
    "POWERGRID": "Power Grid Corporation",
    "PRESTIGE": "Prestige Estates",
    "PVRINOX": "PVR INOX",
    "RAMCOCEM": "Ramco Cements",
    "RBLBANK": "RBL Bank",
    "RECLTD": "REC Limited",
    "RELIANCE": "Reliance Industries",
    "SBICARD": "SBI Cards",
    "SBILIFE": "SBI Life Insurance",
    "SBIN": "State Bank of India",
    "SHREECEM": "Shree Cement",
    "SHRIRAMFIN": "Shriram Finance",
    "SIEMENS": "Siemens India",
    "SONACOMS": "Sona BLW Precision",
    "SRF": "SRF Limited",
    "SUNPHARMA": "Sun Pharmaceutical",
    "SUNTV": "Sun TV Network",
    "SUPREMEIND": "Supreme Industries",
    "SYNGENE": "Syngene International",
    "TATACHEM": "Tata Chemicals",
    "TATACOMM": "Tata Communications",
    "TATACONSUM": "Tata Consumer Products",
    "TATAELXSI": "Tata Elxsi",
    "TATAMOTORS": "Tata Motors",
    "TATAPOWER": "Tata Power",
    "TATASTEEL": "Tata Steel",
    "TCS": "Tata Consultancy Services",
    "TECHM": "Tech Mahindra",
    "TITAN": "Titan Company",
    "TORNTPHARM": "Torrent Pharmaceuticals",
    "TORNTPOWER": "Torrent Power",
    "TRENT": "Trent Limited",
    "TVSMOTOR": "TVS Motor Company",
    "UBL": "United Breweries",
    "ULTRACEMCO": "UltraTech Cement",
    "UNIONBANK": "Union Bank of India",
    "UNITDSPR": "United Spirits",
    "UPL": "UPL Limited",
    "VBL": "Varun Beverages",
    "VEDL": "Vedanta Limited",
    "VOLTAS": "Voltas Limited",
    "WIPRO": "Wipro Limited",
    "YESBANK": "Yes Bank",
    "ZOMATO": "Zomato Eternal",
    "ZYDUSLIFE": "Zydus Lifesciences",
}


def _fetch_gnews(symbol: str, company_name: str) -> list[dict[str, Any]]:
    """
    Fetch news from gnews (Google News Python library) as L1 source.

    gnews wraps Google News RSS with a clean API. No API key needed.
    Coverage is consistent for Indian stocks (7/7 in testing).

    Uses company name in search query for better relevance. Falls back to
    built-in _COMPANY_NAMES lookup if company_name is empty.

    Args:
        symbol:       NSE ticker.
        company_name: Company name for better search relevance.

    Returns:
        Normalised article list (max 10), newest-first.
    """
    # Look up company name if not provided
    effective_name = company_name or _COMPANY_NAMES.get(symbol.upper(), "")
    query = f"{effective_name} stock" if effective_name else f"{symbol} NSE"
    try:
        gn = GNews(language="en", country="India", max_results=_MAX_NEWS, period="7d")
        raw = gn.get_news(query)
    except Exception as exc:
        logger.warning("news_service: gnews fetch failed for %s — %s", symbol, exc)
        return []

    if not raw:
        return []

    articles: list[dict[str, Any]] = []
    for item in raw:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        if not _is_relevant(title, symbol, effective_name):
            continue

        # gnews date format: "Fri, 24 Apr 2026 03:25:00 GMT" (RFC-2822)
        pub_date = (item.get("published date") or "").strip()
        pub_dt = _parse_rfc_date(pub_date)
        published_iso = pub_dt.isoformat() if pub_dt else pub_date

        # Publisher info
        publisher = item.get("publisher", {})
        source_name = publisher.get("title", "Google News")

        # gnews description often duplicates title — skip if identical
        description = (item.get("description") or "").strip()
        if description.lower() == title.lower():
            description = ""

        articles.append({
            "title":       title,
            "description": description,
            "content":     "",   # gnews has no article body (Google News redirect URLs)
            "link":        item.get("url", ""),
            "published":   published_iso,
            "source":      "gnews",
            "source_name": source_name,
            "sentiment":   "",
        })

    return _sort_by_date(articles)[:_MAX_NEWS]


def _fetch_google_news_rss(symbol: str, company_name: str) -> list[dict[str, Any]]:
    """
    Fetch news from Google News RSS as L2 fallback.

    Args:
        symbol:       NSE ticker.
        company_name: Company name for query building.

    Returns:
        Normalised article list (max 10).
    """
    query_term = company_name if company_name else f"{symbol} NSE"
    after_date = (datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    query = f"{query_term} stock when:{_MAX_AGE_DAYS}d after:{after_date}"
    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        logger.warning("news_service: Google News RSS failed for %s — %s", symbol, exc)
        return []

    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:_MAX_NEWS * 2]:
        title    = (item.findtext("title") or "").strip()
        link     = (item.findtext("link")  or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        src_el   = item.find("source")
        source   = src_el.text.strip() if src_el is not None else "Google News"

        if not title or not _is_relevant(title, symbol, company_name):
            continue

        pub_dt       = _parse_rfc_date(pub_date)
        published_iso = pub_dt.isoformat() if pub_dt else pub_date

        if pub_dt and pub_dt < datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS):
            continue

        articles.append({
            "title":       title,
            "description": "",
            "content":     "",
            "link":        link,
            "published":   published_iso,
            "source":      "google_news_rss",
            "source_name": source,
            "sentiment":   "",
        })

    return _sort_by_date(articles)[:_MAX_NEWS]


# ── Enrichment ───────────────────────────────────��──────────────────────────���─

def _enrich(
    articles: list[dict[str, Any]],
    symbol: str,
    company_name: str,
) -> list[dict[str, Any]]:
    """
    Add key_sentence, stock_impact, and signal_class to each article dict.

    Args:
        articles:     List of normalised article dicts.
        symbol:       NSE ticker for key sentence scoring.
        company_name: Company name for key sentence scoring.

    Returns:
        Same list with key_sentence, stock_impact, signal_class added in-place.
    """
    for art in articles:
        combined_text = " ".join(filter(None, [
            art.get("description", ""),
            art.get("content", ""),
        ]))

        key_sentence = extract_key_sentence(combined_text, symbol, company_name)
        signal_class = _classify_signal_class(art.get("title", ""))
        stock_impact = derive_stock_impact(signal_class, key_sentence)

        art["key_sentence"]  = key_sentence
        art["stock_impact"]  = stock_impact
        art["signal_class"]  = signal_class

    return articles


# ── LLM Summarization ─────────────────────────────────────────────────────────

_SHORT_TERM_SIGNALS: frozenset[str] = frozenset([
    "dividend", "buyback", "bonus", "split", "result", "quarterly",
    "surge", "crash", "plunge", "rally", "breakout", "volume",
    "open interest", "option", "futures", "ex-date", "record date",
])

_LONG_TERM_SIGNALS: frozenset[str] = frozenset([
    "acquisition", "merger", "demerger", "expansion", "capex",
    "plant", "capacity", "strategy", "restructuring", "ceo",
    "leadership", "credit rating", "debt", "npa", "moat",
    "market share", "innovation", "patent", "regulation", "policy",
])


def _summarize_articles(
    articles: list[dict[str, Any]],
    symbol: str,
) -> list[dict[str, Any]]:
    """
    Batch-summarize news articles using Gemini 2.5 Pro (sync).

    For each article, the LLM returns:
      - summary: 5-line concise summary of the most important information
      - relevance: float 0.0-1.0 indicating how impactful this news is for the stock
      - signal_class: refined classification (regulatory, earnings, ma_event, etc.)
      - horizon: "short", "long", or "both"

    Falls back gracefully — on any failure, articles are returned unchanged.

    Args:
        articles: Enriched article dicts with title, description, content.
        symbol:   NSE ticker for context.

    Returns:
        Same list with llm_summary, llm_relevance, llm_signal_class,
        llm_horizon keys added where possible.
    """
    if not articles:
        return articles

    # Build compact input per article
    numbered: list[str] = []
    for i, art in enumerate(articles):
        title = str(art.get("title") or "")[:200]
        desc = str(art.get("description") or "")[:300]
        content = str(art.get("content") or "")[:400]
        published = str(art.get("published") or "")[:10]
        source = str(art.get("source_name") or art.get("source") or "")[:50]

        body = desc or content or "No article body available."
        chunk = (
            f"[{i}] source={source} date={published}\n"
            f"Headline: {title}\n"
            f"Body: {body}"
        )
        numbered.append(chunk)

    prompt = (
        f"You are a SEBI-aware Indian equity analyst. Analyze these news articles "
        f"about {symbol} and return a JSON array with one object per article.\n\n"
        f"Each object must have exactly these fields:\n"
        f'  - "summary": 5-line concise summary covering ONLY the most important '
        f'information (what happened, key numbers, likely impact). Max 400 chars.\n'
        f'  - "relevance": float 0.0 to 1.0 indicating how impactful this news is '
        f'for the stock price. Material earnings = 0.9, routine dividend = 0.4, '
        f'generic sector news = 0.2.\n'
        f'  - "signal_class": one of ["regulatory_sebi_action", "fraud_allegation", '
        f'"credit_rating_change", "leadership_change", "ma_event", "major_contract", '
        f'"dividend_or_buyback", "earnings_result", "analyst_action", '
        f'"sector_policy", "generic_positive", "generic_negative"]\n'
        f'  - "horizon": one of ["short", "long", "both"] — which investor horizon '
        f'this news is most relevant for. Dividends/earnings/options = short. '
        f'M&A/strategy/leadership = long. Regulatory/earnings = both.\n\n'
        f"Articles:\n\n" + "\n---\n".join(numbered) +
        f"\n\nReturn ONLY a valid JSON array. No markdown, no backticks."
    )

    try:
        from openai import OpenAI

        from config import settings, yaml_cfg

        model_id = yaml_cfg.versions.get("llm", {}).get("active", "google/gemini-2.5-pro")
        if settings.google_api_key:
            client = OpenAI(
                api_key=settings.google_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            model_id = model_id.removeprefix("google/")
        else:
            import google.auth
            import google.auth.transport.requests

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(google.auth.transport.requests.Request())
            client = OpenAI(
                api_key=credentials.token,
                base_url=settings.google_base_url,
            )

        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "Output ONLY a valid JSON array. No markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=8192,
        )

        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        results: list[dict[str, Any]] = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                results = parsed
        except json.JSONDecodeError:
            # Truncated JSON recovery
            try:
                objects = re.findall(r'\{[^{}]+\}', raw)
                for obj_str in objects:
                    try:
                        results.append(json.loads(obj_str))
                    except Exception:
                        pass
            except Exception:
                pass

        if not results:
            logger.warning("_summarize_articles: no results from LLM for %s", symbol)
            return articles

        # Attach results to articles
        enriched_count = 0
        for i, art in enumerate(articles):
            if i < len(results) and isinstance(results[i], dict):
                r = results[i]
                summary = str(r.get("summary", "")).strip()[:400]
                relevance = float(r.get("relevance", 0.5))
                signal_class = str(r.get("signal_class", "")).strip()
                horizon = str(r.get("horizon", "both")).strip()

                if summary:
                    art["llm_summary"] = summary
                    art["llm_relevance"] = max(0.0, min(1.0, relevance))
                    art["llm_signal_class"] = signal_class if signal_class else art.get("signal_class", "generic_positive")
                    art["llm_horizon"] = horizon if horizon in ("short", "long", "both") else "both"
                    enriched_count += 1

        logger.info("_summarize_articles: %s — %d/%d enriched",
                    symbol, enriched_count, len(articles))

    except Exception as exc:
        logger.warning("_summarize_articles: LLM call failed for %s — using heuristic fallback: %s",
                       symbol, exc)

    return articles


# ── Helpers ──────────────────────────────────────────────────────��────────────

def _classify_signal_class(title: str) -> str:
    """
    Classify a headline into one of the signal class keys.

    Args:
        title: News headline string.

    Returns:
        Signal class key string (e.g. "major_contract", "generic_positive").
    """
    low = title.lower()
    for cls, keywords in _CLASS_KEYWORDS:
        if any(kw in low for kw in keywords):
            return cls

    pos_words = frozenset(["profit", "growth", "record", "strong", "beat", "surge",
                            "rally", "rise", "gain", "win", "expansion", "upgrade"])
    neg_words = frozenset(["loss", "decline", "fall", "miss", "concern", "drop",
                            "cut", "penalty", "fraud", "downgrade", "plunge"])
    words = set(re.findall(r"\b\w+\b", low))
    if len(words & pos_words) > len(words & neg_words):
        return "generic_positive"
    if len(words & neg_words) > len(words & pos_words):
        return "generic_negative"
    return "generic_positive"


_NAME_STOPWORDS: frozenset[str] = frozenset([
    "limited", "ltd", "india", "group", "co", "company", "plc",
    "bank", "finance", "financial", "services", "technologies", "tech",
    "industries", "industry", "enterprises", "holdings", "ventures",
    "corp", "corporation", "international", "global",
])

# Tickers that are common English words — symbol-only match produces false positives.
# For these, require company name words in the title.
_COMMON_WORD_TICKERS: frozenset[str] = frozenset([
    "reliance", "sun", "titan", "lt", "power", "india", "coal",
    "dabur", "united", "force", "action", "everest", "amber",
])


def _is_relevant(title: str, symbol: str, company_name: str) -> bool:
    """
    Return True if the headline is clearly about the target stock.

    Matching rules (in order):
    1. For common-word tickers: require company name words (skip symbol match)
    2. Exact whole-word ticker match (e.g. "RELIANCE" in title)
    3. Company's distinctive core words (>=4 chars, non-generic) appear in title

    Args:
        title:        News headline.
        symbol:       NSE ticker.
        company_name: Full company name.

    Returns:
        True if title mentions the stock.
    """
    low = title.lower()
    sym = symbol.lower()

    # For tickers that are common English words, skip symbol-only match
    # to avoid false positives like "reliance on Nvidia"
    is_common_word = sym in _COMMON_WORD_TICKERS

    if not is_common_word and re.search(r"\b" + re.escape(sym) + r"\b", low):
        return True

    if company_name:
        # Keep only distinctive words: >=4 chars, not in stopword list
        core_words = [
            w for w in company_name.lower().split()
            if len(w) >= 4 and w not in _NAME_STOPWORDS
        ]
        if not core_words:
            return False
        # All core words (up to 2) must appear — avoids "bank" matching ICICI for HDFC
        check = core_words[:2]
        return all(re.search(r"\b" + re.escape(w) + r"\b", low) for w in check)

    return False


def _parse_rfc_date(raw: str) -> datetime | None:
    """Parse RFC-2822 date string (RSS pubDate) to UTC datetime."""
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _sort_by_date(articles: list[dict]) -> list[dict]:
    """Sort articles newest-first by 'published' ISO string."""
    def _key(a: dict) -> datetime:
        raw = a.get("published", "")
        try:
            s = raw
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    return sorted(articles, key=_key, reverse=True)
