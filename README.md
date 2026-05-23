# Stocxi

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Space+Grotesk&weight=800&size=28&duration=2200&pause=800&color=13C89B&center=true&vCenter=true&width=980&lines=AI-Powered+Indian+Stock+Analysis;NSE+%2B+BSE+%2B+Screener+%2B+News+%2B+Knowledge+Graph;Evidence-Backed+Signals+For+Retail+Investors" alt="Stocxi animated headline" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-16.2.4-black?style=for-the-badge&logo=nextdotjs" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-19.2.4-61DAFB?style=for-the-badge&logo=react&logoColor=111" alt="React" />
  <img src="https://img.shields.io/badge/FastAPI-0.115.6-009688?style=for-the-badge&logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Redis-Upstash-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
</p>

<p align="center">
  <b>Search a stock. Read the data. See the risks. Understand the signal.</b>
</p>

---

## What Is Stocxi?

Stocxi is a full-stack AI stock analysis platform for Indian Stock markets.
It helps retail investors understand NSE/BSE stocks through verified data,
technical indicators, fundamentals, filings, news, and AI-generated analysis.

It is built around one rule:

> Every claim should come from data. No hidden reasoning. No unsupported hype.

Stocxi is not a SEBI-registered advisor. It does not provide financial advice.
It describes what the available data suggests.

---

## Why It Stands Out

- **Indian-market first** - NSE, BSE, Screener, corporate filings, and Indian news.
- **Evidence-backed analysis** - every major claim maps to source data.
- **Multi-agent backend** - separate agents for technicals, fundamentals, news, filings, and context.
- **Knowledge graph layer** - connects signals, contradictions, and supporting evidence.
- **Verifier gate** - strips unsupported AI claims before output.
- **Beginner-friendly UI** - clean stock overview, quick reads, key fundamentals, and risk signals.
- **Deployment-minded** - FastAPI backend, Next.js frontend, Redis cache, env examples, buildable structure.

---

## Product Preview

```mermaid
flowchart LR
  User["Retail investor"] --> Search["Stock search"]
  Search --> Overview["Price + fundamentals"]
  Overview --> Graph["Knowledge graph"]
  Graph --> AI["AI analysis"]
  AI --> Verify["Verifier agent"]
  Verify --> Output["Signals for / against"]
```

---

## Core Features

| Area | What Stocxi Does |
|---|---|
| Stock Overview | Price, change, volume, market cap, PE, PB, 52W range |
| Key Fundamentals | EPS, book value, ROE, ROCE, OPM, NPM, sector, industry |
| Technical Indicators | RSI, MACD, ADX, ATR, Bollinger Bands, EMA, VWAP, OBV |
| Financials | Quarterly results, annual P&L, balance sheet, cash flow, shareholding |
| Announcements | NSE/BSE corporate actions, board meetings, dividends, filings |
| News | Approved news sources with sanitization before AI use |
| AI Analysis | Profile-aware summary with signals in favor and against |
| Knowledge Graph | 2D graph for signal relationships and contradictions |
| Reports | Analysis output and PDF/report generation paths |

---

## Architecture

```mermaid
flowchart TB
  FE["Next.js Frontend"] --> API["FastAPI Backend"]
  API --> Cache["Redis Cache"]
  API --> Orchestrator["Orchestrator Agent"]

  Orchestrator --> TA["Technical Agent"]
  Orchestrator --> FA["Fundamental Agent"]
  Orchestrator --> NA["News Agent"]
  Orchestrator --> AA["Announcement Agent"]
  Orchestrator --> CA["Context Agent"]

  TA --> KG["Knowledge Graph"]
  FA --> KG
  NA --> KG
  AA --> KG
  CA --> KG

  KG --> Anon["Anonymizer"]
  Anon --> LLM["Analysis Agent"]
  LLM --> Verifier["Verifier Agent"]
  Verifier --> Formatter["Output Formatter"]
  Formatter --> FE
```

---

## Data Pipeline

1. User searches a stock.
2. Backend checks Redis cache.
3. On cache miss, agents fetch data in parallel.
4. Data is normalized into typed nodes.
5. Conflicts are reconciled by source priority.
6. Unsafe text is sanitized before AI prompts.
7. Stock identity is anonymized for reasoning.
8. AI creates structured analysis.
9. Verifier removes unsupported claims.
10. Formatter returns user-facing output.

---

## Tech Stack

| Layer | Stack |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind, Recharts |
| Backend | FastAPI, Python, Pydantic |
| Data Sources | NSE, BSE, Screener, yfinance fallback, RSS feeds |
| Technicals | pandas, ta |
| AI | Google Gemini / OpenAI-compatible client |
| Cache | Redis / Upstash |
| Graph | Three.js, React Three Fiber |
| Reports | ReportLab |
| Deployment | Vercel frontend, backend-ready FastAPI service |

---

## Repository Structure

```text
stocxi/
├── frontend/                 # Next.js application
│   ├── app/                  # Routes and pages
│   ├── components/           # UI components
│   └── lib/                  # API client and types
├── backend/                  # FastAPI application
│   ├── agents/               # Specialist analysis agents
│   ├── routers/              # API routes
│   ├── services/             # Business logic
│   ├── fetchers/             # NSE/BSE/Screener clients
│   ├── schemas/              # Pydantic contracts
│   └── cache/                # Redis helpers
├── config/                   # Sources, weights, profiles, versions
├── docs/
│   ├── architecture/         # Architecture, scale, plan docs
│   ├── output/               # AI output instruction docs
│   └── progress/             # Progress and rebuild notes
├── data/                     # Generated stock data markdown
├── graphify-out/             # Knowledge graph outputs
├── fetch_phase1_data.py      # Data fetch CLI
├── build_knowledge_graph.py  # Graph builder CLI
└── run_analysis.py           # End-to-end analysis CLI
```

---

## Local Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `backend/.env`:

```env
REDIS_URL=rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT_ID
GOOGLE_APPLICATION_CREDENTIALS=../vertex_credentials.json
NEWSDATA_API_KEY=YOUR_NEWSDATA_KEY
ALLOWED_ORIGINS_RAW=*
ENVIRONMENT=development
```

Run backend:

```bash
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
```

Fill `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=replace_with_a_long_random_secret
REDIS_URL=rediss://:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

Run frontend:

```bash
npm run dev
```

Open:

- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

## Useful Commands

```bash
# Backend smoke compile
conda run -n stocxi python -m py_compile backend/routers/stock.py

# Frontend production build
cd frontend
npm run build -- --webpack

# Fetch stock data
conda run -n stocxi python fetch_phase1_data.py RELIANCE long

# Build knowledge graph
conda run -n stocxi python build_knowledge_graph.py RELIANCE long

# Run analysis CLI
conda run -n stocxi python run_analysis.py RELIANCE --horizon long --level pro
```

---

## API Snapshot

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend health |
| GET | `/api/v1/search?q=tcs&limit=10` | Symbol search |
| GET | `/api/v1/stock/{symbol}` | Stock overview |
| GET | `/api/v1/stock/{symbol}/financials` | Financial statements |
| GET | `/api/v1/stock/{symbol}/news` | News |
| GET | `/api/v1/stock/{symbol}/announcements` | Announcements |
| GET | `/api/v1/stock/{symbol}/history?period=1y` | Price history |
| GET | `/api/v2/analysis/{symbol}` | Agent analysis |
| GET | `/api/v2/analysis/{symbol}/graph` | Knowledge graph |

---

## Design Principles

- No invented data.
- No unapproved sources.
- No future data leakage.
- No raw HTML inside prompts.
- No unsupported AI claims.
- Always show risk signals.
- Always show disclaimer.

---

## Deployment Notes

Recommended deployment:

1. Deploy `frontend/` as the Vercel frontend project.
2. Deploy `backend/` as the API service.
3. Set production `NEXT_PUBLIC_API_URL`.
4. Set backend `ALLOWED_ORIGINS_RAW` to the frontend domain.
5. Add Redis and AI keys in the hosting dashboard.
6. Keep `.env`, `.env.local`, and credentials out of Git.

---

## Disclaimer

Stocxi is an educational analysis product.
It is not a SEBI-registered investment advisor.
It does not provide investment advice.
Markets involve risk.

