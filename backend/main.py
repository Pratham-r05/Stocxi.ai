"""
main.py — FastAPI application entry point for Stocxi backend.

Responsibilities:
  - Boot the app with CORS (needed since Next.js on Vercel calls this from a different origin)
  - Register routers
  - Expose /health so Cloudflare Tunnel and uptime monitors can verify the process is alive
  - Load env vars via pydantic-settings (fail fast on missing required keys)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import stock, analysis, search
from config import settings
from cache.redis_client import redis_client


# ── Lifespan: runs once at startup and once at shutdown ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify Redis is reachable on startup so we know immediately if .env is wrong
    from cache.redis_client import redis_client
    try:
        await redis_client.ping()
        print("✅ Redis connected")
    except Exception as e:
        # Non-fatal: app still serves traffic, just without caching
        print(f"⚠️  Redis unavailable on startup: {e}")
    yield
    # Nothing to close — redis-py manages its own connection pool


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Stocxi API",
    description="AI-powered Indian stock analysis — NSE/BSE data + Claude verdict",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# In production: settings.allowed_origins will be ["https://stocxi.vercel.app"]
# In dev: we allow all so Next.js localhost:3000 works without friction
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
# No prefix= here — each router declares its own full prefix
app.include_router(stock.router)
app.include_router(analysis.router)
app.include_router(search.router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    """Lightweight liveness probe that also reports Redis reachability."""
    redis_status = "disconnected"
    try:
        await redis_client.ping()
        redis_status = "connected"
    except Exception:
        pass

    return {"status": "ok", "version": "1.0.0", "redis": redis_status}


# ── Dev entrypoint ─────────────────────────────────────────────────────────────
# Run with: uvicorn main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
