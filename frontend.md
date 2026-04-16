# frontend.md — Stocxi Frontend Build Spec

> This file is the authoritative instruction set for building the Stocxi frontend.
> An orchestrator agent reads this file and delegates each section to a sub-agent.
> Sub-agents must read this file before touching any code.

---

## Project Context

**Stocxi** — AI-powered Indian stock analysis platform.
Backend: FastAPI on `http://localhost:8000`
Frontend: Next.js 16 (App Router, Turbopack) in `/frontend/`
Stack already scaffolded: `package.json`, `tsconfig.json`, `tailwind.config.ts`, `next.config.ts` all exist. Do NOT re-run `create-next-app`.

---

## Design System (NON-NEGOTIABLE — must match exactly)

### Palette (dark-first)
```
bg-zinc-950     page background (always dark — force dark mode globally)
bg-zinc-900     card background
border-zinc-800 card borders
text-zinc-50    primary text
text-zinc-300   secondary text
text-zinc-400   muted labels / subtext
text-zinc-600   very muted (badges, footers)
```

### Signal colours
| Signal value         | Background + text                             |
|----------------------|-----------------------------------------------|
| BUY / Bullish / Strong / Positive | `bg-emerald-500/15 text-emerald-400 border border-emerald-500/30` |
| AVOID / Bearish / Weak / Negative  | `bg-red-500/15 text-red-400 border border-red-500/30`            |
| HOLD / Mixed / Neutral             | `bg-zinc-700/50 text-zinc-300 border border-zinc-600/30`          |
| Unknown                            | `bg-zinc-800/50 text-zinc-500 border border-zinc-700/30`          |

### Shape & spacing
- Cards: `rounded-xl border bg-zinc-900 border-zinc-800`
- Badges: `rounded-full px-2.5 py-0.5 text-xs font-semibold`
- Section headings: `text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4`
- Input: `rounded-xl bg-zinc-900 border border-zinc-700 text-zinc-100 placeholder:text-zinc-500 focus:ring-1 focus:ring-zinc-500 focus:outline-none`

### Accent
- Logo accent: gradient text `from-violet-400 to-cyan-400`
- Loading shimmer: `animate-pulse bg-zinc-800 rounded-lg`
- Hover on cards: `hover:border-zinc-700 transition-colors`

### Global config
```css
/* Force dark background always — no light mode toggle needed */
html { background: #09090b; color-scheme: dark; }
```

---

## Backend API Reference

Base URL: `http://localhost:8000`

### Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/search?q={query}&limit=10` | Symbol autocomplete |
| GET | `/api/v1/stock/{symbol}` | Overview: price + fundamentals + technicals + sentiment |
| GET | `/api/v1/stock/{symbol}/financials` | Quarterly P&L, balance sheet, cash flow, shareholding |
| GET | `/api/v1/stock/{symbol}/news?limit=10` | News headlines |
| GET | `/api/v1/stock/{symbol}/announcements?limit=10` | BSE corporate announcements |
| GET | `/api/v1/stock/{symbol}/sentiment` | Reddit + Twitter sentiment |
| GET | `/api/v1/analysis/{symbol}?risk_level=low\|medium\|high` | AI verdict |

### Response shapes (key fields only)

**Overview** `GET /api/v1/stock/{symbol}`
```ts
{
  symbol: string, company_name: string, exchange: string, sector: string,
  price: number, change: number, change_percent: number,
  open: number, day_high: number, day_low: number,
  week_52_high: number, week_52_low: number, volume: number,
  market_cap: number, pe_ratio: number, pb_ratio: number, book_value: number,
  eps: number, dividend_yield: number, beta: number, roce: number, roe: number, face_value: number,
  technicals: {
    rsi: number, rsi_signal: string, macd: number, macd_signal: string,
    adx: number, adx_signal: string, atr: number,
    bb_upper: number, bb_lower: number, bb_signal: string,
    ema_20: number, ema_50: number, ema_200: number, ema_signal: string,
    volume_sma_20: number, overall_signal: string,
  },
  sentiment: SentimentData | null,
}
```

**AI Analysis** `GET /api/v1/analysis/{symbol}?risk_level=medium`
```ts
{
  symbol: string, company_name: string, risk_level: string,
  final_verdict: "BUY" | "HOLD" | "AVOID",
  plain_english: string,       // 3-5 sentence narrative for the user
  fundamentals: { verdict: string, summary: string },
  technicals:   { verdict: string, summary: string },
  news:         { verdict: string, summary: string },
  social:       { verdict: string, summary: string },
  risk_match: boolean,
  overall_technical_signal: string,
  current_price: number, change_percent: number,
  generated_at: string, disclaimer: string,
}
```

**Financials** `GET /api/v1/stock/{symbol}/financials`
```ts
{
  quarterly_results: { columns: string[], rows: {label: string, values: number[]}[] },
  annual_results:    { columns: string[], rows: {label: string, values: number[]}[] },
  balance_sheet:     { columns: string[], rows: {label: string, values: number[]}[] },
  cash_flow:         { columns: string[], rows: {label: string, values: number[]}[] },
  shareholding:      { columns: string[], rows: {label: string, values: number[]}[] },
}
```

**News** `GET /api/v1/stock/{symbol}/news`
```ts
{ articles: { title: string, link: string, published: string, source: string }[] }
```

**Announcements** `GET /api/v1/stock/{symbol}/announcements`
```ts
{ announcements: { subject: string, date: string, category: string, pdf_url: string }[] }
```

**Sentiment** `GET /api/v1/stock/{symbol}/sentiment`
```ts
{
  reddit: {
    posts: { title: string, score: number, url: string, text: string, created_at: string }[],
    summary: string, sentiment: string, sentiment_score: number,
    signal: "BUY" | "HOLD" | "AVOID", source: "reddit", fetched_at: string,
  },
  twitter: {
    posts: { text: string, created_at: string, url: string }[],
    summary: string, sentiment: string, sentiment_score: number,
    signal: "BUY" | "HOLD" | "AVOID", source: "twitter", fetched_at: string,
  },
  combined_signal: "BUY" | "HOLD" | "AVOID",
  combined_sentiment_score: number,
  chart_data: { date: string, reddit_score: number, twitter_score: number }[],
}
```

**Search** `GET /api/v1/search?q=RELI`
```ts
{ results: { symbol: string, name: string, exchange: string }[] }
```

---

## Pages & Routes

### `/` — Home Page
**Purpose:** Entry point — search bar + trending chips + hero branding.

**Layout:**
```
Full-screen dark bg (zinc-950)
├── Centered column (max-w-lg, px-4)
│   ├── Logo: gradient "Stocxi" text + tagline
│   ├── SearchBar (with live autocomplete dropdown)
│   └── Trending chips: RELIANCE TCS INFY HDFCBANK WIPRO ITC ADANIPOWER PAYTM
└── Footer: "Not financial advice" note
```

**SearchBar behaviour:**
- Debounce 300ms → call `GET /api/v1/search?q={input}` on each keystroke
- Show dropdown list of matches (symbol + company name)
- Click or Enter → navigate to `/stock/{SYMBOL}`
- Keyboard nav: ArrowUp/Down to select, Enter to confirm, Escape to close
- Minimum 2 chars before showing dropdown

**Trending chips:**
- Static list, clickable → navigate to `/stock/{SYMBOL}`
- Style: small pills `bg-zinc-900 border border-zinc-800 hover:border-zinc-600 text-zinc-300`

---

### `/stock/[symbol]` — Stock Detail Page
**Purpose:** Full analysis page for a single NSE stock.

**This is a server component page.** Fetch overview on server via `fetch()`. Pass data down to client sub-components.

**Page sections (in order from top):**

#### 1. Navbar
- Back arrow (`←`) + "Stocxi" logo (links to `/`)
- Right: nothing for now

#### 2. StockHeader
- Company name (large, zinc-50)
- Symbol chip + exchange chip + sector chip
- Price (large, zinc-50) | change (green/red with ▲▼) | change %
- Day range bar: low ←●→ high with current price marker

#### 3. Quick Stats Grid (2×4 on mobile, 4×2 on desktop)
```
Market Cap | P/E Ratio | 52W High | 52W Low
ROE        | ROCE      | Book Value | Div Yield
```
Cards: rounded-xl bg-zinc-900 border-zinc-800

#### 4. AI Analysis Panel (client component — lazy loaded)
- Risk selector tabs: Low | Medium | High (default: Medium)
- On tab select → call `GET /api/v1/analysis/{symbol}?risk_level={level}`
- Show loading skeleton while fetching (AI is slow — 5-10s)
- Display:
  - `final_verdict` badge (big, centre-aligned): BUY / HOLD / AVOID with signal colour
  - `plain_english` paragraph (the narrative)
  - 4-card grid: Fundamentals | Technicals | News | Social — each with verdict badge + summary text
  - `risk_match` pill: "Suitable for {risk} risk investors ✓" or "⚠ May not suit {risk} risk profile"
  - `generated_at` timestamp (small, muted)
  - Disclaimer text (very small, zinc-600, italic)

#### 5. Technicals Section
- Grid of indicator cards: RSI | MACD | ADX | EMA | BB | Overall
- Each card: indicator name, value (mono font), signal badge
- RSI: also show horizontal bar (0–100) with colour zone markers at 30/70

#### 6. Social Sentiment Section (client component — lazy loaded)
**Loads via `GET /api/v1/stock/{symbol}/sentiment`**
- Combined signal badge at top (big)
- Combined score: horizontal bar from -1 to +1 with current position dot
- Two side-by-side cards (Reddit | Twitter):
  - Source icon/label
  - Signal badge + sentiment label
  - Score number
  - Summary text (multi-line, zinc-300)
  - Post count
- 7-day chart below (pure SVG — NO chart library):
  - Two lines: Reddit (violet) and Twitter (cyan)
  - Y axis: -1 to +1 with 0 gridline
  - X axis: 7 day labels
  - Hover dots with tooltip (date + scores)
- Loading skeleton while fetching
- Graceful empty state if no posts found

#### 7. News Section (client component — lazy loaded)
**Loads via `GET /api/v1/stock/{symbol}/news`**
- List of news cards: title (link, zinc-100), source + published date (zinc-500)
- Max 10 items
- Loading skeleton
- Empty state: "No recent news found"

#### 8. BSE Announcements Section (client component — lazy loaded)
**Loads via `GET /api/v1/stock/{symbol}/announcements`**
- List: subject (title), date, category badge, PDF link button
- Max 10 items
- Compact rows (not full cards — use list style with dividers)
- Empty state: "No recent announcements"

#### 9. Financials Section (client component — lazy loaded)
**Loads via `GET /api/v1/stock/{symbol}/financials`**
- Tab selector: Quarterly P&L | Annual P&L | Balance Sheet | Cash Flow | Shareholding
- Table view: rows as metrics, columns as time periods
- Sticky first column (label), scrollable horizontally
- Positive numbers: zinc-100, negative numbers: red-400
- Loading skeleton

---

## File Structure

```
frontend/
├── app/
│   ├── layout.tsx           (root layout — Geist fonts, dark bg, metadata)
│   ├── globals.css          (tailwind import + html dark override)
│   ├── page.tsx             (Home page — server component)
│   └── stock/
│       └── [symbol]/
│           └── page.tsx     (Stock detail — server component, fetches overview)
│
├── components/
│   ├── ui/
│   │   ├── Badge.tsx        (signal badge — accepts signal string, returns coloured pill)
│   │   ├── Card.tsx         (standard card wrapper)
│   │   ├── Skeleton.tsx     (shimmer loading skeleton)
│   │   └── Tabs.tsx         (tab selector — accepts items + onChange)
│   │
│   ├── home/
│   │   ├── SearchBar.tsx    (input + dropdown autocomplete, client component)
│   │   └── TrendingChips.tsx
│   │
│   ├── stock/
│   │   ├── StockHeader.tsx         (price, change, day range)
│   │   ├── QuickStatsGrid.tsx      (8-cell fundamentals grid)
│   │   ├── TechnicalsSection.tsx   (indicator cards + RSI bar)
│   │   ├── AIAnalysisPanel.tsx     (client, risk tabs, AI verdict display)
│   │   ├── FinancialsSection.tsx   (client, tabbed financial tables)
│   │   ├── NewsSection.tsx         (client, news list)
│   │   └── AnnouncementsSection.tsx (client, BSE list)
│   │
│   └── sentiment/
│       ├── SentimentSection.tsx    (client, container with loading/error)
│       ├── SentimentSummary.tsx    (per-source card: Reddit or Twitter)
│       └── SentimentChart.tsx      (pure SVG 7-day dual-line chart)
│
├── lib/
│   ├── api.ts               (all fetch functions — typed, error handled)
│   └── types.ts             (TypeScript interfaces for all API responses)
│
└── .env.local               (NEXT_PUBLIC_API_URL=http://localhost:8000)
```

---

## lib/api.ts — Required Functions

All functions must:
- Use `NEXT_PUBLIC_API_URL` env var as base URL
- Return `null` (not throw) on any error
- Be fully typed with types from `lib/types.ts`

```ts
fetchStockOverview(symbol: string): Promise<StockOverview | null>
fetchAIAnalysis(symbol: string, riskLevel: 'low'|'medium'|'high'): Promise<AIAnalysis | null>
fetchFinancials(symbol: string): Promise<Financials | null>
fetchNews(symbol: string): Promise<NewsResponse | null>
fetchAnnouncements(symbol: string): Promise<AnnouncementsResponse | null>
fetchSentiment(symbol: string): Promise<SentimentData | null>
searchSymbols(query: string): Promise<SearchResult[]>
```

---

## Agent Build Plan

The orchestrator should delegate to sub-agents in this order. Each sub-agent gets the relevant section of this spec + relevant API contract. Sub-agents must NOT rewrite files they weren't assigned.

### Sub-agent 1 — Foundation
Files: `app/layout.tsx`, `app/globals.css`, `lib/types.ts`, `lib/api.ts`, `.env.local`, `components/ui/Badge.tsx`, `components/ui/Card.tsx`, `components/ui/Skeleton.tsx`, `components/ui/Tabs.tsx`

Tasks:
- Root layout with Geist font, dark forced background, `<html>` no-flicker
- globals.css forcing dark always
- All TypeScript types from API shapes above
- All API functions
- Shared UI primitives (Badge with signal colour logic, Card, Skeleton shimmer, Tabs)

### Sub-agent 2 — Home Page
Files: `app/page.tsx`, `components/home/SearchBar.tsx`, `components/home/TrendingChips.tsx`

Tasks:
- Server component home page
- SearchBar: debounced input → calls `searchSymbols()` → dropdown results → navigate on select
- Keyboard nav in dropdown (arrow keys, enter, escape)
- Trending chips
- Design: centred, minimal, gradient logo, dark bg

### Sub-agent 3 — Stock Header + Fundamentals
Files: `app/stock/[symbol]/page.tsx` (skeleton only — just renders placeholders for sub-components), `components/stock/StockHeader.tsx`, `components/stock/QuickStatsGrid.tsx`

Tasks:
- Server page fetches overview via `fetchStockOverview` (server-side)
- notFound() if null
- StockHeader: company name, symbol/exchange/sector chips, price, change, day range bar
- QuickStatsGrid: 8-cell grid

### Sub-agent 4 — Technicals + AI Panel
Files: `components/stock/TechnicalsSection.tsx`, `components/stock/AIAnalysisPanel.tsx`

Tasks:
- TechnicalsSection: indicator grid, RSI bar
- AIAnalysisPanel: client component, risk tabs (Low/Medium/High), calls `fetchAIAnalysis` on mount + tab change, loading skeleton, verdict display (big badge, plain_english, 4-card breakdown, risk_match, disclaimer)

### Sub-agent 5 — Sentiment Section
Files: `components/sentiment/SentimentSection.tsx`, `components/sentiment/SentimentSummary.tsx`, `components/sentiment/SentimentChart.tsx`

Tasks:
- SentimentSection: calls `fetchSentiment`, loading skeleton, combined signal + score bar
- SentimentSummary: per-source card
- SentimentChart: pure SVG dual line chart, 7 data points, violet (Reddit) + cyan (Twitter) lines, 0 gridline, hover tooltips
- Wire into stock page

### Sub-agent 6 — News + Announcements + Financials
Files: `components/stock/NewsSection.tsx`, `components/stock/AnnouncementsSection.tsx`, `components/stock/FinancialsSection.tsx`

Tasks:
- NewsSection: loads `fetchNews`, list of article cards with external link
- AnnouncementsSection: loads `fetchAnnouncements`, compact list with PDF button
- FinancialsSection: loads `fetchFinancials`, tabbed tables (Quarterly | Annual | Balance Sheet | Cash Flow | Shareholding), sticky label column, scroll horizontally, negative values in red
- Wire all three into stock page

---

## Constraints (never violate)

- **Dark only** — do NOT add a light mode toggle. Force dark everywhere.
- **No chart library** — all charts must be pure SVG inline in React components.
- **No UI library** — no shadcn, radix, chakra, etc. Pure Tailwind only.
- **Server components for data fetching** — only mark as `"use client"` when the component needs browser APIs (useState, useEffect, event handlers).
- **Never throw in api.ts** — all fetch functions return null on error.
- **Loading skeletons required** — every client component that fetches must show a skeleton (pulse animation) while loading.
- **Empty states required** — every list must handle zero items gracefully.
- **TypeScript strict** — no `any` types. Use types from `lib/types.ts`.
- **NEXT_PUBLIC_API_URL** — all API calls must read base URL from this env var, never hardcode `localhost:8000`.
- **Mobile responsive** — use Tailwind grid/flex responsive breakpoints. Min width: 375px.
- **Incremental edits only** — each sub-agent edits only its assigned files. Never touch files owned by another agent.

---

## Running the Frontend

```bash
cd frontend
npm run dev          # starts on http://localhost:3000 with Turbopack
```

Backend must be running on `http://localhost:8000` before testing.

---

## Quality Bar

The finished product should look like a professional fintech dashboard:
- Deep zinc-950 background everywhere
- Cards with subtle zinc-800 borders and zinc-900 backgrounds  
- Gradient logo text (violet → cyan)
- Signal colours that are clearly readable: emerald for positive, red for negative
- Smooth loading skeletons, not blank screens
- Data-dense but not cluttered — good whitespace between sections
