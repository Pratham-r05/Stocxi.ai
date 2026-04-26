a# Graph Report - .  (2026-04-20)

## Corpus Check
- Corpus is ~45,066 words - fits in a single context window. You may not need a graph.

## Summary
- 686 nodes · 956 edges · 79 communities detected
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 155 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Sentiment Analysis Engine|Sentiment Analysis Engine]]
- [[_COMMUNITY_PDF Report Generation|PDF Report Generation]]
- [[_COMMUNITY_Frontend API Client|Frontend API Client]]
- [[_COMMUNITY_Backend Infrastructure|Backend Infrastructure]]
- [[_COMMUNITY_Report PDF Rendering|Report PDF Rendering]]
- [[_COMMUNITY_AI Analysis Service|AI Analysis Service]]
- [[_COMMUNITY_Analysis Data Collection|Analysis Data Collection]]
- [[_COMMUNITY_News Aggregation|News Aggregation]]
- [[_COMMUNITY_YFinance Data Service|YFinance Data Service]]
- [[_COMMUNITY_Auth & Landing UI|Auth & Landing UI]]
- [[_COMMUNITY_Stock Overview Router|Stock Overview Router]]
- [[_COMMUNITY_AI Analysis Panel|AI Analysis Panel]]
- [[_COMMUNITY_Technicals Service|Technicals Service]]
- [[_COMMUNITY_User Auth Store|User Auth Store]]
- [[_COMMUNITY_Screener Financials|Screener Financials]]
- [[_COMMUNITY_Announcements Service|Announcements Service]]
- [[_COMMUNITY_Price Chart|Price Chart]]
- [[_COMMUNITY_Login Page UI|Login Page UI]]
- [[_COMMUNITY_Hero Search|Hero Search]]
- [[_COMMUNITY_Stock Navbar Actions|Stock Navbar Actions]]
- [[_COMMUNITY_Social Buzz Launcher|Social Buzz Launcher]]
- [[_COMMUNITY_NSE Symbol Search|NSE Symbol Search]]
- [[_COMMUNITY_Technicals Display|Technicals Display]]
- [[_COMMUNITY_Key Fundamentals|Key Fundamentals]]
- [[_COMMUNITY_Market Ticker Bar|Market Ticker Bar]]
- [[_COMMUNITY_Pricing Tiers|Pricing Tiers]]
- [[_COMMUNITY_Price History Chart|Price History Chart]]
- [[_COMMUNITY_Search Bar Interaction|Search Bar Interaction]]
- [[_COMMUNITY_Ticker Bar Logic|Ticker Bar Logic]]
- [[_COMMUNITY_Download Report Button|Download Report Button]]
- [[_COMMUNITY_Stock Section Tabs|Stock Section Tabs]]
- [[_COMMUNITY_Top Stats Bar|Top Stats Bar]]
- [[_COMMUNITY_Sentiment Chart|Sentiment Chart]]
- [[_COMMUNITY_Misc Component 33|Misc Component 33]]
- [[_COMMUNITY_Misc Component 34|Misc Component 34]]
- [[_COMMUNITY_Misc Component 35|Misc Component 35]]
- [[_COMMUNITY_Misc Component 36|Misc Component 36]]
- [[_COMMUNITY_Misc Component 37|Misc Component 37]]
- [[_COMMUNITY_Misc Component 38|Misc Component 38]]
- [[_COMMUNITY_Misc Component 39|Misc Component 39]]
- [[_COMMUNITY_Misc Component 40|Misc Component 40]]
- [[_COMMUNITY_Misc Component 41|Misc Component 41]]
- [[_COMMUNITY_Misc Component 42|Misc Component 42]]
- [[_COMMUNITY_Misc Component 43|Misc Component 43]]
- [[_COMMUNITY_Misc Component 44|Misc Component 44]]
- [[_COMMUNITY_Misc Component 45|Misc Component 45]]
- [[_COMMUNITY_Misc Component 46|Misc Component 46]]
- [[_COMMUNITY_Misc Component 47|Misc Component 47]]
- [[_COMMUNITY_Misc Component 48|Misc Component 48]]
- [[_COMMUNITY_Misc Component 49|Misc Component 49]]
- [[_COMMUNITY_Misc Component 50|Misc Component 50]]
- [[_COMMUNITY_Misc Component 51|Misc Component 51]]
- [[_COMMUNITY_Misc Component 52|Misc Component 52]]
- [[_COMMUNITY_Misc Component 53|Misc Component 53]]
- [[_COMMUNITY_Misc Component 54|Misc Component 54]]
- [[_COMMUNITY_Misc Component 55|Misc Component 55]]
- [[_COMMUNITY_Misc Component 56|Misc Component 56]]
- [[_COMMUNITY_Misc Component 57|Misc Component 57]]
- [[_COMMUNITY_Misc Component 58|Misc Component 58]]
- [[_COMMUNITY_Misc Component 59|Misc Component 59]]
- [[_COMMUNITY_Misc Component 60|Misc Component 60]]
- [[_COMMUNITY_Misc Component 61|Misc Component 61]]
- [[_COMMUNITY_Misc Component 62|Misc Component 62]]
- [[_COMMUNITY_Misc Component 63|Misc Component 63]]
- [[_COMMUNITY_Misc Component 64|Misc Component 64]]
- [[_COMMUNITY_Misc Component 65|Misc Component 65]]
- [[_COMMUNITY_Misc Component 66|Misc Component 66]]
- [[_COMMUNITY_Misc Component 67|Misc Component 67]]
- [[_COMMUNITY_Misc Component 68|Misc Component 68]]
- [[_COMMUNITY_Misc Component 69|Misc Component 69]]
- [[_COMMUNITY_Misc Component 70|Misc Component 70]]
- [[_COMMUNITY_Misc Component 71|Misc Component 71]]
- [[_COMMUNITY_Misc Component 72|Misc Component 72]]
- [[_COMMUNITY_Misc Component 73|Misc Component 73]]
- [[_COMMUNITY_Misc Component 74|Misc Component 74]]
- [[_COMMUNITY_Misc Component 75|Misc Component 75]]
- [[_COMMUNITY_Misc Component 76|Misc Component 76]]
- [[_COMMUNITY_Misc Component 77|Misc Component 77]]
- [[_COMMUNITY_Misc Component 78|Misc Component 78]]

## God Nodes (most connected - your core abstractions)
1. `GET()` - 69 edges
2. `build_stock_report_pdf()` - 21 edges
3. `cache_get()` - 19 edges
4. `cache_set()` - 17 edges
5. `_collect_analysis_inputs()` - 14 edges
6. `apiFetch()` - 12 edges
7. `search()` - 12 edges
8. `_calculate_technicals()` - 12 edges
9. `get_stock_overview()` - 11 edges
10. `analyse()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `getRedisClient` --semantically_similar_to--> `redis_client`  [INFERRED] [semantically similar]
  frontend/lib/userStore.ts → backend/cache/redis_client.py
- `Social Buzz default icon — two overlapping chat bubbles (Reddit orange, Twitter/X blue) on dark background` --rationale_for--> `get_sentiment`  [INFERRED]
  frontend/public/social-buzz-default.svg → backend/services/sentiment_service.py
- `Product Flow: Search > Analyze > Decide` --references--> `search_symbols`  [INFERRED]
  README.md → backend/services/search_service.py
- `Product Flow: Search > Analyze > Decide` --references--> `get_price_and_fundamentals`  [INFERRED]
  README.md → backend/services/yfinance_service.py
- `Vercel triangle logo (white triangle on transparent background)` --rationale_for--> `Stocxi Project`  [INFERRED]
  frontend/public/vercel.svg → README.md

## Hyperedges (group relationships)
- **Authentication Flow: NextAuth, Google, Credentials, userStore** — nextauth_authoptions, nextauth_googleprovider, nextauth_credentialsprovider, register_userstore, register_route [INFERRED 0.90]
- **Stock Page Composition: StockPage + fetchStockOverview + StockLoading** — stockpage_stockpage, stockpage_fetchstockoverview, stockloading_stockloading [INFERRED 0.85]
- **Landing Page: HomePage, LandingNavbar, HowItWorksSection** — page_homepage, landingnavbar_landingnavbar, howitworks_howitworkssection [EXTRACTED 1.00]
- **Stock page data-fetching sections share the symbol prop and async fetch pattern** — pricechart_pricechart, newssection_newssection, aianalysispanel_aianalysispanel, financialssection_financialssection, announcementssection_announcementssection, socialbuzzlauncher_socialbuzzlauncher [INFERRED 0.90]
- **Home landing page sections form the marketing funnel flow** — herosection_herosection, problemsection_problemsection, solutionsection_solutionsection, pricingsection_pricingsection, landingfooter_landingfooter [INFERRED 0.85]
- **StockNavbar, DownloadReportButton, and TrackStockSearch all operate at the stock-page session-level** — stocknavbar_stocknavbar, downloadreportbutton_downloadreportbutton, trackstocksearch_trackstocksearch [INFERRED 0.80]
- **AI Analysis Pipeline: collect inputs → AI call → cache → response** — routers_analysis_collectinputs, ai_service_analyse, redis_client_cache_set, routers_analysis_getanalysis [EXTRACTED 0.95]
- **News Fallback Chain: ScanX → Google News RSS → yfinance** — news_service_fetchscanxnews, news_service_fetchgooglenews, news_service_fetchyfinancenews, news_service_getnewssync [EXTRACTED 0.95]
- **Sentiment Display: SentimentSection → SentimentDonut + SentimentSummary using SentimentData type** — sentimentsection_sentimentsection, sentimentsection_sentimentdonut, sentimentsummary_sentimentsummary, types_sentimentdata [INFERRED 0.85]
- **3-tier OHLCV source fallback: NSE intraday → Yahoo chart → yfinance → jugaad-data** — yfinance_service_fetchnseintraday1d, yfinance_service_fetchfromyahoochart, yfinance_service_jugaad, technicals_service_tryyfinance, technicals_service_tryjugaad [INFERRED 0.88]
- **Social sentiment pipeline: fetch (Reddit/Twitter/GoogleNews) → score (VADER) → summarize → cache** — sentiment_service_fetchredditsync, sentiment_service_fetchtwittersync, sentiment_service_fetchsocialfromgooglenews, sentiment_service_processsource, sentiment_service_vadersentiment, sentiment_service_getsentiment [EXTRACTED 0.95]
- **PDF report data aggregation: financials + price + technicals feed into tiered PDF builder** — screener_service_getfinancials, yfinance_service_getpriceandfundamentals, technicals_service_calculatetechnicals, report_service_buildstockreportpdf [INFERRED 0.85]

## Communities

### Community 0 - "Sentiment Analysis Engine"
Cohesion: 0.06
Nodes (59): _build_ai_summary_lines(), _build_chart_data(), _build_structured_summary(), _build_summary(), _build_summary_lines(), _clean_summary_text(), _extract_themes(), _fallback_source() (+51 more)

### Community 1 - "PDF Report Generation"
Cohesion: 0.04
Nodes (56): API Endpoints, Product Flow: Search > Analyze > Decide, Stocxi Project, Tech Stack: FastAPI, Next.js, Redis, OpenRouter, _build_minimal_pdf, build_stock_report_pdf, _draw_financial_change_chart, _draw_price_momentum_chart (+48 more)

### Community 2 - "Frontend API Client"
Cohesion: 0.04
Nodes (44): load(), apiFetch(), fetchAIAnalysis(), fetchAnnouncements(), fetchFinancials(), fetchHistory(), fetchNews(), fetchSentiment() (+36 more)

### Community 3 - "Backend Infrastructure"
Cohesion: 0.05
Nodes (48): _fetch_from_nse, get_announcements, _get_announcements_bse, _get_bse_code, VercelEntrypoint, BaseSettings, config.py — Typed environment configuration via pydantic-settings.  Reads from ., Settings (+40 more)

### Community 4 - "Report PDF Rendering"
Cohesion: 0.1
Nodes (37): _ascii_clean(), _beginner_action_lines(), _build_minimal_pdf(), build_stock_report_pdf(), _draw_bullets(), _draw_financial_change_chart(), _draw_footer(), _draw_price_momentum_chart() (+29 more)

### Community 5 - "AI Analysis Service"
Cohesion: 0.08
Nodes (35): analyse(), _build_report_fallback_payload(), _build_report_user_prompt(), _build_rule_based_fallback(), _build_user_prompt(), _build_user_prompt, _call_openrouter(), _call_openrouter_report() (+27 more)

### Community 6 - "Analysis Data Collection"
Cohesion: 0.11
Nodes (33): _build_financial_snapshot(), _build_price_movement_snapshot(), _build_quick_ai_stub(), _build_volume_context(), _collect_analysis_inputs(), _compact_announcements(), _compact_news(), download_analysis_report() (+25 more)

### Community 7 - "News Aggregation"
Cohesion: 0.11
Nodes (28): _extract_scanx_entries_from_state(), _fetch_google_news(), _fetch_scanx_news(), _fetch_yfinance_news(), get_news(), _get_news_sync(), _is_recent_news(), _is_relevant_news_title() (+20 more)

### Community 8 - "YFinance Data Service"
Cohesion: 0.13
Nodes (22): main(), Quick smoke test for yfinance_service and screener_service. Run from backend/ di, section(), test_screener(), test_technicals(), test_yfinance(), test_yfinance_invalid(), _fetch_from_nse() (+14 more)

### Community 9 - "Auth & Landing UI"
Cohesion: 0.1
Nodes (19): HowItWorksSection, LandingNavbar(), CreateAccountTab, LoginContent, LoginPage, SignInTab, authOptions, CredentialsProvider (+11 more)

### Community 10 - "Stock Overview Router"
Cohesion: 0.12
Nodes (21): _clean_logo_candidate(), _compute_eps(), _compute_pb(), _extract_best_logo_url(), _extract_domain(), get_stock_overview(), _normalize_website_url(), routers/stock.py — Stock data endpoints.  Endpoints:     GET /api/v1/stock/{symb (+13 more)

### Community 11 - "AI Analysis Panel"
Cohesion: 0.11
Nodes (20): AIAnalysis type, AIAnalysisPanel, fetchAIAnalysis call, RISK_TABS (low|medium|high), formatMarketCap(), formatPE(), formatPercent(), formatPrice() (+12 more)

### Community 12 - "Technicals Service"
Cohesion: 0.18
Nodes (18): _adx_signal(), _bb_signal(), _calculate_technicals(), _download_history(), _ema_signal(), _f(), _last_valid(), _macd_signal() (+10 more)

### Community 13 - "User Auth Store"
Cohesion: 0.23
Nodes (15): isValidSymbol(), POST(), addUser(), findUserByEmail, findUserByEmail(), getRedisClient(), getUserStockSearches(), readUsers() (+7 more)

### Community 14 - "Screener Financials"
Cohesion: 0.18
Nodes (13): _extract_mf_holdings(), _fetch_screener(), get_financials(), _parse_company_website(), _parse_table(), _parse_top_ratios(), screener_service.py — Scrape quarterly financials + key ratios from Screener.in., Extract key ratios from Screener's #top-ratios section.     Returns dict with: p (+5 more)

### Community 15 - "Announcements Service"
Cohesion: 0.19
Nodes (12): _fetch_from_nse(), _get_announcements(), _get_bse_code(), _is_recent_announcement(), _parse_nse_dt(), announcements_service.py — Fetch recent corporate announcements.  Source strateg, Resolve NSE ticker → BSE scrip code via BSE's company search API.     Returns th, Fetch recent corporate announcements for a BSE scrip code.     Returns list of c (+4 more)

### Community 16 - "Price Chart"
Cohesion: 0.29
Nodes (5): formatDate(), formatTooltipDate(), isIntradayDate(), load(), parseChartDate()

### Community 17 - "Login Page UI"
Cohesion: 0.22
Nodes (0): 

### Community 18 - "Hero Search"
Cohesion: 0.25
Nodes (6): HeroSection(), SearchBar, SearchResult type usage, searchSymbols call, STOCK_POOL, TrendingChips()

### Community 19 - "Stock Navbar Actions"
Cohesion: 0.22
Nodes (7): DownloadReportButton, /api/v1/analysis/{symbol}/report endpoint, ReportTier (orbiter|stellar|apex), SessionProviderWrapper(), StockNavbar, TrackStockSearch(), /api/user/stock-search API route

### Community 20 - "Social Buzz Launcher"
Cohesion: 0.25
Nodes (2): load(), openWithFetch()

### Community 21 - "NSE Symbol Search"
Cohesion: 0.32
Nodes (7): _fallback_symbols(), _load_nse_symbols(), services/search_service.py — NSE symbol autocomplete.  Strategy:   1. Try nsepyt, Fetch all NSE equity symbols from nsepython.     Returns list of {symbol, name,, Top-50 most traded NSE stocks — used if nsepython is unavailable.     This ensur, Return NSE symbols matching `query` as a prefix (case-insensitive).      Args:, search_symbols()

### Community 22 - "Technicals Display"
Cohesion: 0.29
Nodes (0): 

### Community 23 - "Key Fundamentals"
Cohesion: 0.4
Nodes (0): 

### Community 24 - "Market Ticker Bar"
Cohesion: 0.6
Nodes (5): isIndianMarketOpen, MarketTickerBar, /api/market-ticker API route, NSE All Indices Fetch, Market Ticker API Route

### Community 25 - "Pricing Tiers"
Cohesion: 0.4
Nodes (5): Free Tier (3 analyses), Max Tier (₹499/month), PricingCard, PricingSection, Pro Tier (₹199/month)

### Community 26 - "Price History Chart"
Cohesion: 0.4
Nodes (5): CustomTooltip, fetchHistory call, HistoryPoint type, Period type (1d|1w|1mo|6mo|1y), PriceChart

### Community 27 - "Search Bar Interaction"
Cohesion: 0.67
Nodes (2): handleKeyDown(), selectResult()

### Community 28 - "Ticker Bar Logic"
Cohesion: 0.67
Nodes (2): isIndianMarketOpen(), loop()

### Community 29 - "Download Report Button"
Cohesion: 0.5
Nodes (0): 

### Community 30 - "Stock Section Tabs"
Cohesion: 0.5
Nodes (0): 

### Community 31 - "Top Stats Bar"
Cohesion: 0.5
Nodes (0): 

### Community 32 - "Sentiment Chart"
Cohesion: 0.5
Nodes (0): 

### Community 33 - "Misc Component 33"
Cohesion: 1.0
Nodes (2): Badge(), getSignalClasses()

### Community 34 - "Misc Component 34"
Cohesion: 1.0
Nodes (2): Skeleton(), SkeletonCard()

### Community 35 - "Misc Component 35"
Cohesion: 0.67
Nodes (0): 

### Community 36 - "Misc Component 36"
Cohesion: 0.67
Nodes (3): fetchNews call, NewsArticle type, NewsSection

### Community 37 - "Misc Component 37"
Cohesion: 0.67
Nodes (3): openai==1.57.4, OpenAI/OpenRouter AI client, _build_ai_summary_lines

### Community 38 - "Misc Component 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Misc Component 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Misc Component 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Misc Component 41"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Misc Component 42"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Misc Component 43"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "Misc Component 44"
Cohesion: 1.0
Nodes (1): Vercel serverless entrypoint that exposes the FastAPI app.

### Community 45 - "Misc Component 45"
Cohesion: 1.0
Nodes (2): RootLayout, SessionProviderWrapper

### Community 46 - "Misc Component 46"
Cohesion: 1.0
Nodes (2): AnnouncementsSection, fetchAnnouncements call

### Community 47 - "Misc Component 47"
Cohesion: 1.0
Nodes (2): get_stock_financials, test_screener

### Community 48 - "Misc Component 48"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Misc Component 49"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "Misc Component 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Misc Component 51"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Misc Component 52"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Misc Component 53"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Misc Component 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Misc Component 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Misc Component 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Misc Component 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Misc Component 58"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Misc Component 59"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Misc Component 60"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Misc Component 61"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Misc Component 62"
Cohesion: 1.0
Nodes (0): 

### Community 63 - "Misc Component 63"
Cohesion: 1.0
Nodes (0): 

### Community 64 - "Misc Component 64"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Misc Component 65"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "Misc Component 66"
Cohesion: 1.0
Nodes (0): 

### Community 67 - "Misc Component 67"
Cohesion: 1.0
Nodes (1): PostCSS Config

### Community 68 - "Misc Component 68"
Cohesion: 1.0
Nodes (1): Next.js Config

### Community 69 - "Misc Component 69"
Cohesion: 1.0
Nodes (1): SectionHeader UI Component

### Community 70 - "Misc Component 70"
Cohesion: 1.0
Nodes (1): ProblemSection

### Community 71 - "Misc Component 71"
Cohesion: 1.0
Nodes (1): StockSectionTabs

### Community 72 - "Misc Component 72"
Cohesion: 1.0
Nodes (1): StockHeader

### Community 73 - "Misc Component 73"
Cohesion: 1.0
Nodes (1): _fetch_nse_historical_week

### Community 74 - "Misc Component 74"
Cohesion: 1.0
Nodes (1): fastapi==0.115.6

### Community 75 - "Misc Component 75"
Cohesion: 1.0
Nodes (1): redis==5.2.1

### Community 76 - "Misc Component 76"
Cohesion: 1.0
Nodes (1): File/document icon — generic document with folded corner and text lines

### Community 77 - "Misc Component 77"
Cohesion: 1.0
Nodes (1): Globe/web icon — stylized globe for web/international links

### Community 78 - "Misc Component 78"
Cohesion: 1.0
Nodes (1): Window/browser icon — browser window outline with three dots (traffic lights)

## Knowledge Gaps
- **250 isolated node(s):** `config.py — Typed environment configuration via pydantic-settings.  Reads from .`, `Quick smoke test for yfinance_service and screener_service. Run from backend/ di`, `main.py — FastAPI application entry point for Stocxi backend.  Responsibilities:`, `Lightweight liveness probe that also reports Redis reachability.`, `routers/analysis.py — AI-powered stock analysis endpoint.  Endpoint:   GET /api/` (+245 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Misc Component 38`** (2 nodes): `loading.tsx`, `StockLoading()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 39`** (2 nodes): `Card()`, `Card.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 40`** (2 nodes): `InfoTooltip.tsx`, `InfoTooltip()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 41`** (2 nodes): `HowItWorksSection.tsx`, `HowItWorksSection()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 42`** (2 nodes): `LandingFooter.tsx`, `LandingFooter()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 43`** (2 nodes): `SentimentSection.tsx`, `updateSizeState()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 44`** (2 nodes): `index.py`, `Vercel serverless entrypoint that exposes the FastAPI app.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 45`** (2 nodes): `RootLayout`, `SessionProviderWrapper`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 46`** (2 nodes): `AnnouncementsSection`, `fetchAnnouncements call`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 47`** (2 nodes): `get_stock_financials`, `test_screener`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 48`** (1 nodes): `postcss.config.mjs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 49`** (1 nodes): `next-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 50`** (1 nodes): `proxy.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 51`** (1 nodes): `eslint.config.mjs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 52`** (1 nodes): `next.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 53`** (1 nodes): `layout.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 54`** (1 nodes): `route.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 55`** (1 nodes): `SectionHeader.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 56`** (1 nodes): `SolutionSection.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 57`** (1 nodes): `ProblemSection.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 58`** (1 nodes): `PricingSection.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 59`** (1 nodes): `StockHeader.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 60`** (1 nodes): `StockNavbar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 61`** (1 nodes): `SentimentSummary.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 62`** (1 nodes): `types.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 63`** (1 nodes): `Navbar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 64`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 65`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 66`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 67`** (1 nodes): `PostCSS Config`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 68`** (1 nodes): `Next.js Config`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 69`** (1 nodes): `SectionHeader UI Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 70`** (1 nodes): `ProblemSection`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 71`** (1 nodes): `StockSectionTabs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 72`** (1 nodes): `StockHeader`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 73`** (1 nodes): `_fetch_nse_historical_week`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 74`** (1 nodes): `fastapi==0.115.6`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 75`** (1 nodes): `redis==5.2.1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 76`** (1 nodes): `File/document icon — generic document with folded corner and text lines`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 77`** (1 nodes): `Globe/web icon — stylized globe for web/international links`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Misc Component 78`** (1 nodes): `Window/browser icon — browser window outline with three dots (traffic lights)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GET()` connect `Analysis Data Collection` to `Sentiment Analysis Engine`, `Backend Infrastructure`, `Report PDF Rendering`, `AI Analysis Service`, `News Aggregation`, `YFinance Data Service`, `Stock Overview Router`, `User Auth Store`, `Screener Financials`, `Announcements Service`?**
  _High betweenness centrality (0.233) - this node is a cross-community bridge._
- **Why does `cache_get()` connect `Backend Infrastructure` to `Sentiment Analysis Engine`, `Stock Overview Router`, `Analysis Data Collection`, `News Aggregation`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Why does `apiFetch()` connect `Frontend API Client` to `Backend Infrastructure`?**
  _High betweenness centrality (0.112) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `GET()` (e.g. with `getUserStockSearches()` and `readUsers()`) actually correct?**
  _`GET()` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `build_stock_report_pdf()` (e.g. with `download_analysis_report()` and `GET()`) actually correct?**
  _`build_stock_report_pdf()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `cache_get()` (e.g. with `get_analysis()` and `download_analysis_report()`) actually correct?**
  _`cache_get()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `cache_set()` (e.g. with `get_analysis()` and `download_analysis_report()`) actually correct?**
  _`cache_set()` has 10 INFERRED edges - model-reasoned connections that need verification._