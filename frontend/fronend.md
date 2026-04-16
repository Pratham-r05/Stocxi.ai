You are helping build a futuristic UI for StockSense India (stocxi) — an AI-powered Indian stock analysis platform.

## STEP 1: Read the codebase
Explore the entire project at: /Users/prathamraj/Documents/Placement-Prep/10.Projects/stocxi

Read and understand:
- All backend API routes (FastAPI)
- Agent architecture (fundamental/technical/sentiment/macro agents)
- GraphRAG + KuzuDB usage
- Data models and schemas
- What data each endpoint returns
- Auth flow if any

## STEP 2: Map data to UI components
For each data source/endpoint, identify which UI component will consume it.

## STEP 3: Build a complete UI plan for these pages:

### Page 1: Landing Page
- Hero section with animated stock ticker tape
- Feature highlights (multi-agent AI, GraphRAG, real-time analysis)
- CTA: "Analyze a Stock"
- Dark theme, glassmorphism, neon accents (blue/cyan/green)

### Page 2: Login / Auth Page
- Minimal centered card
- Email + password or token-based (match existing auth)
- Animated background (particle mesh or flowing lines)

### Page 3: Stock Search Page (post-login)
- Large centered search bar with autocomplete
- Recent searches, trending stocks
- Typeahead powered by backend

### Page 4: Stock Analysis Dashboard (main page)
Build ALL these sections as tabs or scrollable sections:

**4a. Overview Header**
- Stock name, price, % change, market cap, PE, EPS
- Pill badges for 1D/5D/1M/6M/1Y/5Y returns

**4b. Price Chart (PRIMARY - must be excellent)**
- Candlestick + line toggle
- Volume bars below
- Time range selector
- Crosshair tooltip showing OHLCV + delivery %
- Use lightweight-charts or recharts/D3
- NOT a basic line chart — full TradingView-style

**4c. Key Fundamentals Panel**
- Right sidebar: MarketCap, EPS, PE, PB, BookValue, EBITDA, DivYield, ROE, D/E
- Color-coded good/bad values

**4d. AI Analysis Section**
- Multi-agent output cards: Fundamental | Technical | Sentiment | Macro
- Each card has: agent name, confidence score, verdict (Buy/Hold/Sell), key insights
- Final combined recommendation with reasoning
- Streaming output effect if possible

**4e. Financials**
- Quarterly table: Revenue, Expenses, EBITDA, Operating Profit %, Depreciation, Interest, PBT, Tax
- Toggle: Annual / Quarterly, Consolidated / Standalone
- Growth rate badges: Revenue Growth, Net Income Growth, Cash Flow Change, ROE, ROCE, EBITDA Margin

**4f. Balance Sheet**
- Table: Total Assets, Fixed Assets, Current Assets, CWIP, Investments, Liabilities, Equity
- Years: 2018–2025
- Show % change toggle

**4g. Cash Flows**
- Net Cash Flow, Operating, Investing, Financing by year
- Waterfall or grouped bar chart

**4h. Analyst Forecast**
- EBITDA/EPS/Revenue/Price forecast chart
- Buy/Hold/Sell consensus (100% Buy = full green ring)
- Estimated vs Actual lines

**4i. Peer Comparison**
- Table: LTP, MarketCap, PE, Revenue, YoY Revenue Growth, Net Profit, YoY Profit Growth, RSI
- Highlight best-in-peer with rank badges (#1, #2)

**4j. News & Announcements**
- Company news feed with date badges
- SEBI/Exchange announcements list
- Block trade alerts

**4k. Shareholding Pattern**
- Donut chart: Promoter, FII, DII, Public, Others
- Timeline line chart showing holding % change
- Current % labels

**4l. MF Holdings**
- Table: Fund name, Current Holding %, 1M Change, 3M Change, 6M Trend sparkline

**4m. Technicals**
- Indicator pills: RSI, MACD, Bollinger, EMA signals
- Bearish/Neutral/Bullish scale bar (like the ScanX screenshot)
- Individual indicator cards with value + signal

## STEP 4: Tech stack recommendation
Based on what you find in the backend, recommend:
- Frontend framework (Next.js / React)
- Charting lib (lightweight-charts recommended for price chart)
- State management
- API integration pattern
- Component library (shadcn/ui or custom)

## STEP 5: Output a detailed implementation plan
- File/folder structure
- Component hierarchy
- Which backend endpoints map to which components
- Suggested color palette and design tokens
- Priority order to build (MVP first)

Reference: The screenshots provided are from ScanX (Dhan). The new UI should be SIGNIFICANTLY more futuristic, dark, and visually impressive — think Bloomberg Terminal meets Vercel dashboard meets sci-fi HUD.

Be specific. Reference actual file names and functions you find in the codebase.