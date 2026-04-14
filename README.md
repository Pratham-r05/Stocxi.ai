# Stocxi 📈

AI-powered Indian stock analysis platform. Built for beginners who want to invest smart without needing to understand financial jargon.

## What It Does

- Search any NSE/BSE stock
- See full fundamentals, technicals, financials in one place
- Click **"Analyse with AI"** → get a plain English verdict (Buy / Hold / Avoid)
- AI breaks down: Fundamentals + Technicals + News separately
- Personalized by risk appetite (Low / Medium / High)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router) |
| Backend | FastAPI (Python 3.11) |
| Data — Price & Fundamentals | yfinance |
| Data — Quarterly, Balance Sheet, Cashflow, Shareholding | Screener.in (scrape) |
| Technicals | pandas-ta |
| AI Analysis | OpenRouter → Claude Sonnet |
| Cache | Upstash Redis |
| Frontend Deploy | Vercel |
| Backend Deploy | Local server (Cloudflare Tunnel) |

---

## Project Structure

```
stocxi/
├── backend/
│   ├── main.py                  # FastAPI app entry
│   ├── routers/
│   │   ├── stock.py             # Stock data endpoints
│   │   └── analysis.py          # AI analysis endpoint
│   ├── services/
│   │   ├── yfinance_service.py  # Price + basic fundamentals
│   │   ├── screener_service.py  # Quarterly, BS, CF, shareholding
│   │   ├── technicals_service.py # pandas-ta calculations
│   │   ├── news_service.py      # News fetching
│   │   └── ai_service.py        # OpenRouter + Claude
│   ├── cache/
│   │   └── redis_client.py      # Upstash Redis client
│   ├── models/
│   │   └── stock_models.py      # Pydantic models
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Home + search
│   │   ├── stock/[symbol]/
│   │   │   └── page.tsx         # Stock detail page
│   │   └── layout.tsx
│   ├── components/
│   │   ├── SearchBar.tsx
│   │   ├── StockHeader.tsx
│   │   ├── FundamentalsTab.tsx
│   │   ├── TechnicalsTab.tsx
│   │   ├── FinancialsTab.tsx
│   │   ├── NewsTab.tsx
│   │   └── AIAnalysis.tsx       # The "Analyse with AI" panel
│   ├── lib/
│   │   └── api.ts               # API call functions
│   └── package.json
├── ARCHITECTURE.md
├── REQUIREMENTS.md
├── PROGRESS.md
├── AI_CONTEXT.md
└── DATAFLOW.md
```

---

## Environment Variables

### Backend (`backend/.env`)
```env
OPENROUTER_API_KEY=your_key_here
UPSTASH_REDIS_URL=your_upstash_url
UPSTASH_REDIS_TOKEN=your_upstash_token
ALLOWED_ORIGINS=http://localhost:3000,https://stocxi.vercel.app
```

### Frontend (`frontend/.env.local`)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Setup & Run

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/stock/{symbol}` | Price + fundamentals + technicals |
| GET | `/stock/{symbol}/financials` | Quarterly, BS, CF, shareholding |
| GET | `/stock/{symbol}/news` | Recent news |
| POST | `/stock/{symbol}/analyse` | AI analysis (Buy/Hold/Avoid) |
| GET | `/search?q={query}` | Stock search autocomplete |

---

## Caching Strategy

| Data Type | TTL |
|---|---|
| Price | 5 minutes |
| Fundamentals | 24 hours |
| Technicals | 15 minutes |
| Financials (quarterly etc.) | 7 days |
| News | 2 hours |
| AI Analysis | 6 hours |

---

## Disclaimer

Stocxi is for educational purposes only. Not SEBI registered. Not financial advice. Always do your own research before investing.
