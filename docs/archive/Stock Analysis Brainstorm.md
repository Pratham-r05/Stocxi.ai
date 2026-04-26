# Stocxi — AI Stock Analysis Platform
## Master Brainstorming Document for Opus 4.7

---

## IMPORTANT: How to Use This Document

This document is the **complete brain dump** of everything decided about Stocxi so far. Your job as Opus is to:

1. Read everything carefully
2. Ask clarifying questions if anything is unclear
3. Help design each phase in depth — starting with Phase 1 (deep brainstorming) and Phase 2 (strict architecture)
4. Challenge assumptions where needed
5. Help build the strict architecture rulebook that the AI model must follow

Do NOT skip ahead. Work phase by phase.

---

## 1. What is Stocxi?

Stocxi is an AI-powered stock analysis platform built for **Indian retail investors who have no finance background.** The core idea — a non-finance person searches any stock name, and the platform gives them a clear, transparent, evidence-backed analysis based on all available data.

**Live URL:** https://stocxi.vercel.app
**Target Market:** Indian retail investors (NSE/BSE)
**Stage:** Basic MVP live. Now planning and building the full intelligent analysis layer.
**Builder:** Solo developer, bootstrapped, validating before investing money

> ⚠️ Legal boundary: Stocxi is NOT a SEBI registered advisor. It CANNOT say "BUY this stock." It presents what the data suggests and lets the user decide. Every output must include a disclaimer. The language is always "signals suggest" never "you should buy."

---

## 2. The Core Problem

Most stock platforms show 20+ raw metrics (PE ratio, MACD, RSI, EV/EBITDA etc.) with zero explanation. A non-finance person sees pure noise. They don't know what the numbers mean, how they connect, or what action to take.

**Stocxi solves this** by:
- Fetching all relevant data from strict, approved sources only
- Structuring it into a knowledge graph of nodes
- Using AI to find relationships between nodes
- Presenting transparent, plain-English reasoning — not just a verdict, but the full thinking process

---

## 3. The 5 Phases of Building Stocxi

### Phase 1 — Deep Brainstorming (current phase)
- Understand every aspect of what we are building
- Clarify all requirements, data sources, edge cases
- Understand backtesting requirements fully
- This document is the output of Phase 1

### Phase 2 — Architecture Design
- Design the complete strict architecture
- Every rule the AI model must follow — what to fetch, what to ignore, how to format, how to reason
- This architecture must be so strict that the model cannot hallucinate or make random decisions
- Data pipeline design, node structure, storage strategy, analysis protocol
- The architecture document becomes the law of the system — model must follow it exactly

### Phase 3 — Data Pipeline Implementation
- Build data fetching one source at a time
- Store everything in strict structured format
- Validate data quality before moving to next source
- Order: fetch → format as node → store → validate → move to next source

### Phase 4 — Knowledge Graph + AI Reasoning
- Once all data is stored correctly, build the knowledge graph
- Connect nodes with relationships
- Build and test the AI analysis prompt
- Test whether the model reasons correctly over the structured data

### Phase 5 — Backtesting + Paper Trading
- Give the model historical data only (no future leakage)
- Model generates analysis for historical date
- Compare against what actually happened
- Simulate paper trading with hypothetical money
- Measure accuracy, iterate, improve
- This is the validation proof before showing to any investor or domain expert

---

## 4. User Profile System

Before any stock analysis, the user sets their profile once. All analysis is personalized to this profile.

| Preference | Options |
|---|---|
| Investment Horizon | Short Term / Long Term |
| Sector Preference | IT, Banking, Pharma, FMCG, Energy, Auto, Infrastructure, etc. |
| Risk Appetite | Conservative / Moderate / Aggressive |

**Why this matters:** The same stock gets completely different analysis based on profile. RELIANCE for a long-term conservative investor vs a short-term aggressive trader = two different analyses with different signal weights and different data emphasis.

---

## 5. Data Layers

### 5.1 Technical Indicators (17 total)

All 17 must be calculated and stored as nodes. No exceptions.

**Trend (4):**
- Simple Moving Average (SMA)
- Exponential Moving Average (EMA)
- Ichimoku Cloud
- Parabolic SAR

**Momentum (5):**
- RSI — Relative Strength Index
- MACD — Moving Average Convergence Divergence
- Stochastic Oscillator
- Williams %R
- ROC — Rate of Change

**Volatility (2):**
- Bollinger Bands
- ATR — Average True Range

**Volume (4):**
- OBV — On-Balance Volume
- VWAP — Volume Weighted Average Price (short term / intraday relevance only)
- CMF — Chaikin Money Flow
- MFI — Money Flow Index

**Strength (2):**
- ADX — Average Directional Index
- 52-Week High/Low Ratio

**Chart Reading (horizon-dependent):**
- Short term investor: focus on 1M-3M price action, recent momentum patterns
- Long term investor: focus on 3Y-5Y cycle position, accumulation/distribution over time
- Fibonacci Retracement: visual/optional only, not used in AI reasoning nodes

**Data source for technicals:** yfinance (15-minute delayed — acceptable for analysis, not live trading)
**Refresh frequency:** Daily

---

### 5.2 Fundamental Data

**Refresh frequency:** Weekly (fundamentals don't change daily)
**Storage:** Pre-fetched and stored for all major NSE/BSE stocks in database

**Data points:**
- Quarterly results — last 4 quarters
- Annual reports — last 2 years
- Balance sheet — assets, liabilities, cash flow
- Market capitalization
- Revenue growth YoY
- ROCE, ROE
- PE ratio, EV/EBITDA, PEG ratio
- Debt/Equity ratio
- Promoter holding %
- Promoter pledging % (red flag if high or increasing)
- FII holding % (trend matters — increasing = bullish signal)
- DII holding %
- Mutual fund holding %

**APPROVED data sources — STRICT, no other sources:**
- Screener.in — quarterly/annual results, ratios, balance sheet
- BSE official API — shareholding pattern, filings
- NSE official API — shareholding, filings
- yfinance — market cap, basic fundamentals
- Tickertape or Trendlyne — MF holdings, institutional data

---

### 5.3 News Layer

**Refresh frequency:** Every few hours
**Critical rule: Signal vs Noise filtering is mandatory**

**APPROVED sources — fetch ONLY from these, absolutely no exceptions:**
- Moneycontrol (moneycontrol.com)
- Economic Times Markets (economictimes.indiatimes.com/markets)
- Business Standard (business-standard.com)
- Livemint (livemint.com)
- Reuters India
- Bloomberg Quint / BQ Prime
- NSE/BSE official press releases

**NEVER fetch from:**
- Random blogs or financial opinion websites
- YouTube titles or video descriptions
- Twitter/X or any social media platform
- WhatsApp forwards or message aggregators
- Any source not explicitly listed in the approved list above

**FETCH a news item if ANY of these conditions are true:**
- Directly mentions the company by its exact name
- Mentions the company's sector AND has material market impact
- Government / SEBI / RBI policy that directly affects this stock or sector
- Material business event: merger, acquisition, demerger, contract win, contract loss, fraud allegation, leadership change, major fundraise

**DO NOT FETCH if ANY of these conditions are true:**
- Generic market commentary (e.g., "Sensex fell 200 points today")
- Duplicate story from multiple sources — keep only the earliest or most detailed version
- Older than 30 days for short term analysis
- Older than 90 days for long term analysis
- No clear and direct connection to the specific company or its sector
- Opinion pieces or editorials with no factual data

---

### 5.4 BSE/NSE Announcements Layer

**Refresh frequency:** Every few hours
**Source:** BSE and NSE official filing APIs ONLY
**Signal quality:** Highest possible — zero noise, all officially filed by company

**Announcement types to capture:**
- Quarterly results declaration date and actual results
- Board meeting outcomes
- Dividend declarations
- Merger / Acquisition / Demerger announcements
- Promoter buying shares (bullish signal)
- Promoter selling shares (flag for analysis)
- SEBI actions, penalties, investigations
- Insider trading disclosures
- Management or leadership changes (CEO, CFO, board members)
- Rights issue, bonus issue, stock split
- Loan defaults or credit rating changes

---

## 6. Node Structure — Universal Format

Every single piece of data across ALL layers must be stored in this exact JSON format.
No exceptions. If data cannot fit this structure, it is dropped entirely.

```json
{
  "stock": "RELIANCE",
  "category": "technical | fundamental | news | announcement",
  "name": "RSI | Revenue_Growth | CEO_Change | Dividend_Declared",
  "value": "67.2 | 12% YoY | New CEO appointed | ₹5 per share",
  "date": "2025-04-18",
  "signal": "positive | negative | neutral",
  "confidence": 0.85,
  "source": "yfinance | Screener.in | Moneycontrol | BSE",
  "horizon_relevance": "short | long | both",
  "weight": 0.0
}
```

**Weight field:** Not all signals are equal. A promoter pledging increase is more serious than a single-day RSI reading. Weights are pre-defined in the architecture for each node type — this is part of Phase 2 architecture design.

---

## 7. Knowledge Graph — Relationship Building

Once all nodes are stored, the AI builds relationships between them. This is the core intelligence of Stocxi.

**Types of relationships:**
- **Agreement:** Two nodes pointing same direction — strengthens overall signal
- **Contradiction:** Two nodes pointing opposite directions — must be reasoned through explicitly
- **Causation:** One event likely caused or will cause another
- **Context:** One node explains or qualifies the meaning of another

**Example relationship chain:**
```
FII holding increasing +2.1% [positive, high weight]
  → AGREES WITH → Revenue growing 12% YoY [positive, high weight]
    → AGREES WITH → MACD bullish crossover [positive, medium weight]
      → SUPPORTED BY → Positive sector policy announcement [positive, medium weight]
        → CONTRADICTED BY → Promoter pledging increased 1.2% [negative, medium weight]
          → CONCLUSION: Strong bullish signal with one moderate risk flag
```

The model must go back and forth between nodes — not read them linearly. It must actively search for both supporting and contradicting connections.

---

## 8. Analysis Protocol — The 80/20 Rule

### 80% Strict (model must follow exactly, zero deviation):

```
STEP 1: Validate — confirm all nodes are properly formatted. Drop malformed nodes.
STEP 2: Technical analysis — read all 17 indicator nodes, form technical verdict
STEP 3: Fundamental analysis — read all fundamental nodes, form fundamental verdict
STEP 4: News sentiment — read all news nodes, form sentiment verdict
STEP 5: Announcement analysis — read all announcement nodes, form event verdict
STEP 6: Apply user profile weights:
         Short term:  technical 50% | news 30% | fundamental 15% | announcements 5%
         Long term:   fundamental 50% | announcements 20% | technical 20% | news 10%
STEP 7: List all agreements found across 4 verdicts
STEP 8: List all contradictions found — reason through each one explicitly
STEP 9: Generate structured output following exact output format below
```

### 20% Model Intelligence (free thinking within structured data only):

After completing all strict steps, model has freedom to:
- Find non-obvious connections between nodes that the strict steps did not surface
- Spot unusual patterns (e.g., price rising but OBV falling = distribution signal most miss)
- Apply contextual judgment to contradicting signals
- Think like a senior analyst: "What is this stock really telling me beyond the raw numbers?"

**Critical constraint on the 20%:** The model can ONLY reason over nodes that exist in the provided structured data. It cannot assume, invent, recall from training, or fetch any information not provided as a node. Creative thinking means connecting real dots — not creating new dots.

---

## 9. Final Output Structure

### Header (always shown — free and pro)
```
Stock: RELIANCE | NSE: RELIANCE.NS | BSE: 500325
Current Price: ₹1,284.50 (15 min delayed)
Analysis Date: April 21, 2025
Investor Profile: Long Term | Moderate Risk
Overall Signal: Bullish (4/5 categories align positively)
Confidence Level: 74%
```

### Section 1 — What the Data Suggests
Plain English. Every single claim backed by a specific data point with source. No jargon. No invented context.

### Section 2 — Signals Working in Favor
Every positive node listed with its value, source, and why it matters.

### Section 3 — Signals Working Against
Every negative or cautionary node listed. Transparency is non-negotiable. Never hide risks.

### Section 4 — How the Model Reasoned (Strategy Transparency)
The exact reasoning chain shown step by step. User sees the thinking, not just the conclusion.

### Section 5 — Key Relationships Found (Knowledge Graph Output)
Node connections the model discovered, shown as a chain. Visual in report, text in UI.

### Section 6 — Downloadable Visual Report (Pro feature)

**Must include visual charts — not text only:**
- Price chart (1M, 3M, 6M, 1Y, 3Y depending on horizon)
- Technical indicator charts with signal annotations
- Fundamental trend charts (revenue, profit, debt over quarters)
- Knowledge graph visualization — nodes and relationships as a visual map
- News sentiment trend chart (last 30/90 days)
- FII/DII/Promoter holding trend chart

**Short Term Report:** Technical deep dive, 1M-3M price action, entry/exit signals, news sentiment, risk/reward ratio

**Long Term Report:** Fundamentals deep dive with trend charts, 3Y financial trends, valuation analysis, annual report highlights, sector outlook

**Format:** PDF, Stocxi branded
**Mandatory disclaimer on every report:** "This analysis is AI-generated for educational purposes only. Stocxi is not a SEBI registered investment advisor. This is not financial advice. Please consult a qualified financial advisor before making any investment decisions."

---

## 10. Backtesting System

**Purpose:** Validate that Stocxi's analysis actually works with real historical data. Build credibility. Prove the product before showing to investors or domain experts.

**Absolute rule:** Zero future data leakage. Model sees ONLY data that existed on the test date.

### Backtesting Steps:
```
1. Select test stock (e.g., RELIANCE) and test date (e.g., October 1, 2024)
2. Fetch all data as it existed ON that exact date only
   - Technicals: calculated from price history up to Oct 1 only
   - Fundamentals: only reports published before Oct 1
   - News: only articles published before Oct 1
   - Announcements: only filings submitted before Oct 1
3. Run full analysis — model generates verdict with confidence score
4. Record the verdict and full reasoning
5. Fast forward to outcome date (test date + 1M, 3M, or 6M)
6. Check actual stock performance vs verdict direction
7. Record result: correct/incorrect and magnitude
8. Repeat across minimum 50-100 stocks, multiple historical dates
```

### Paper Trading Simulation:
Give the model a hypothetical ₹10,000. Model must:
- Decide which stocks to allocate capital to based on its analysis
- Decide position sizing based on confidence score (higher confidence = larger position)
- Hold for defined period (1M / 3M / 6M)
- Track simulated P&L
- Compare performance against Nifty50 benchmark

**Success criteria:** If model consistently outperforms Nifty50 in backtesting = system has real value.

### Metrics to Track:
| Metric | Description |
|---|---|
| Overall signal accuracy % | How often signal direction was correct |
| Avg return on bullish signals | When bullish, what was the actual avg return |
| Avg return on bearish signals | When bearish, what loss was avoided |
| Accuracy by sector | Which sectors model performs best in |
| Short term vs long term accuracy | Which horizon is more reliable |
| Confidence calibration | When model says 80% confident, is it right 80% of time? |
| False positive rate | Bullish signal was wrong |
| False negative rate | Missed a good stock |

---

## 11. AI Model Strategy

### Testing/Validation Phase (now — zero cost):
- Manual testing via Claude.ai — paste structured data + prompt, evaluate output quality
- Opencode subscription — for building and coding the infrastructure
- Google AI Studio (Gemini 2.5 Flash) — free tier (1500 req/day) for backend testing

### Production Phase (after validation):
- Primary: Gemini 2.5 Flash (~₹0.5-2 per full analysis)
- Upgrade path: Claude Sonnet API for deep reasoning when revenue supports it
- Cost at 100 analyses/day: ~₹50-200/day — manageable at early scale

### Core Testing Philosophy:
Test the brain before building the body. Validate prompt + reasoning quality manually via Claude.ai BEFORE writing any backend infrastructure. If the intelligence quality is poor, the infrastructure is worthless.

---

## 12. Tech Stack

| Component | Technology |
|---|---|
| Frontend | Already built — Vercel (HTML/JS) |
| Backend | FastAPI (Python) |
| Database | PostgreSQL or Supabase |
| Technical data | yfinance Python library |
| Fundamental data | Screener.in, BSE/NSE official APIs |
| News data | NewsAPI + approved source scrapers |
| Announcement data | BSE/NSE official APIs |
| AI analysis | Gemini 2.5 Flash / Claude API |
| PDF report generation | WeasyPrint or ReportLab (Python) |
| Chart generation in reports | Matplotlib or Plotly |
| Auth | Already implemented |
| Hosting | Vercel (frontend) + Railway or Render (backend) |

---

## 13. Pricing Model

| Plan | Price | Key Features |
|---|---|---|
| Free | ₹0 | 3 total analyses, basic indicators, BSE announcements, news headlines, signal verdict |
| Pro | ₹199/month | Unlimited analyses, deep AI analysis, all 17 indicators, price history charts, quarterly/annual financial tables, visual downloadable report, backtesting dashboard |
| Max | ₹499/month (coming soon) | Everything in Pro + mutual fund analysis, portfolio overlap, risk-adjusted scoring |

---

## 14. Key Differentiators

1. **Personalized by user profile** — same stock, completely different analysis based on horizon and risk appetite
2. **Transparent reasoning** — user sees exactly how and why the model reached its conclusion. Never a black box.
3. **Strict data architecture** — prevents hallucination, ensures every claim is backed by real verified data
4. **Knowledge graph relationships** — finds non-obvious connections between signals that humans and basic screeners miss
5. **Backtesting with paper trading** — proves historical accuracy. No other Indian retail platform does this transparently.
6. **Indian market focused** — NSE/BSE, Indian approved news sources only, BSE/NSE announcements, Indian regulatory context
7. **Built for non-finance people** — every indicator explained in plain English, no assumed knowledge
8. **Visual downloadable reports** — charts, graphs, knowledge graph map — not just text

---

## 15. Open Questions for Opus to Help Resolve

**Architecture questions:**
- What is the correct weight for each of the 17 technical indicators?
- How should contradicting signals be ranked in severity? (e.g., is promoter pledging more serious than negative RSI?)
- What happens when a data source is unavailable? What is the fallback strategy?
- How many nodes is too many for one prompt? Token limit considerations?
- How to prevent the model from using its training knowledge about a stock instead of only using provided node data?

**Backtesting questions:**
- How many stocks and how many historical dates needed for statistically significant results?
- How to handle survivorship bias? (only testing stocks that still exist skews results)
- What is the minimum acceptable accuracy % before the system is considered validated?
- How to simulate realistic paper trading accounting for liquidity and bid-ask spread?

**Product questions:**
- Should the knowledge graph be shown visually in the UI or only in the downloadable report?
- How do we handle stocks with very limited data (small cap, recently listed companies)?
- How is the confidence score calculated? Should the model explain it to the user?
- On-demand analysis only, or scheduled refresh?

**Technical questions:**
- Best approach for fetching Screener.in data reliably without getting blocked?
- How to structure the system prompt to enforce 80% strict + allow 20% free reasoning?
- How to make model ignore its training priors about a stock and only use node data?

---

## 16. Session Goal with Opus

Work through these in order:

1. Validate the overall architecture — anything flawed or missing?
2. Design the node weight system — assign importance weights to each data type and indicator
3. Design contradiction resolution protocol — exact rules for conflicting signals
4. Design the system prompt structure — enforces 80% strict + 20% free reasoning
5. Design the backtesting methodology — sample size, date selection, success criteria
6. Design the paper trading simulation — position sizing rules, benchmark comparison
7. Identify gaps — what has not been thought of that could break the system?

---

*This document is the complete Phase 1 brainstorming output for Stocxi.*
*Built by Pratham. Brainstorming session with Claude Sonnet.*
*Next: Deep architecture session with Claude Opus 4.7*
