# Stocxi — Requirements

## Accounts to Create

| Service | URL | Purpose | Cost |
|---|---|---|---|
| OpenRouter | openrouter.ai | Claude API for AI analysis | Pay per use ~$5/month |
| Upstash | upstash.com | Redis cache | Free tier |
| Vercel | vercel.com | Frontend hosting | Free |
| Cloudflare | cloudflare.com | Tunnel for backend | Free |

---

## API Keys Needed

| Key | Where to Get | Where Used |
|---|---|---|
| `OPENROUTER_API_KEY` | openrouter.ai/keys | backend/.env |
| `UPSTASH_REDIS_URL` | upstash.com console | backend/.env |
| `UPSTASH_REDIS_TOKEN` | upstash.com console | backend/.env |

---

## Backend Dependencies (`backend/requirements.txt`)

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.8.2
python-dotenv==1.0.1

# Data fetching
yfinance==0.2.43
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2

# Technicals
pandas==2.2.2
pandas-ta==0.3.14b0
numpy==1.26.4

# Cache
redis==5.0.8
upstash-redis==1.1.0

# HTTP client
httpx==0.27.0

# CORS
python-multipart==0.0.9
```

---

## Frontend Dependencies (`frontend/package.json`)

```json
{
  "dependencies": {
    "next": "15.0.0",
    "react": "19.0.0",
    "react-dom": "19.0.0",
    "typescript": "5.5.4",
    "tailwindcss": "3.4.10",
    "recharts": "2.12.7",
    "axios": "1.7.7",
    "lucide-react": "0.447.0",
    "clsx": "2.1.1",
    "framer-motion": "11.5.4"
  }
}
```

---

## System Requirements

| Requirement | Minimum |
|---|---|
| Python | 3.11 |
| Node.js | 18+ |
| RAM (backend server) | 2GB+ |
| OS (backend) | Ubuntu 24.04 (your server) |

---

## OpenRouter Model

```
Model: anthropic/claude-sonnet-4-5
Fallback: anthropic/claude-haiku-4-5  (cheaper, faster, use if cost is concern)
```

---

## Cloudflare Tunnel Setup (one-time)

```bash
# On Ubuntu server
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
cloudflared tunnel login
cloudflared tunnel create stocxi
cloudflared tunnel route dns stocxi api.stocxi.in  # or any subdomain you own
cloudflared tunnel run stocxi
```

Or quick test without domain:
```bash
cloudflared tunnel --url http://localhost:8000
# gives you a public URL like https://random-name.trycloudflare.com
```

---

## NSE Symbol Format for yfinance

```
NSE stocks: append .NS  → RELIANCE.NS, TCS.NS, INFY.NS
BSE stocks: append .BO  → RELIANCE.BO, TCS.BO

Default: always try .NS first, fallback to .BO
```

---

## Screener.in Symbol Format

```
URL: https://www.screener.in/company/{SYMBOL}/consolidated/
Example: https://www.screener.in/company/RELIANCE/consolidated/

Note: Some companies don't have consolidated view, fallback to:
https://www.screener.in/company/{SYMBOL}/
```
