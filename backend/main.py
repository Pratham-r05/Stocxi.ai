"""
main.py — FastAPI application entry point for Stocxi backend.

Responsibilities:
  - Boot the app with CORS (needed since Next.js on Vercel calls this from a different origin)
  - Register routers
  - Expose /health so Cloudflare Tunnel and uptime monitors can verify the process is alive
  - Load env vars via pydantic-settings (fail fast on missing required keys)
"""

import sys
from pathlib import Path

# Ensure both repo root and backend/ are on path so all import styles resolve
_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT   = _BACKEND_DIR.parent
for _p in (_REPO_ROOT, _BACKEND_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import stock, analysis, search, v2_analysis, knowledge_graph
from config import settings
from cache.redis_client import ping as redis_ping

logger = logging.getLogger(__name__)


# ── Lifespan: runs once at startup and once at shutdown ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify Redis is reachable on startup so we know immediately if .env is wrong
    if await redis_ping():
        logger.info("Redis connected")
    else:
        # Non-fatal: app still serves traffic, just without caching
        logger.warning("Redis unavailable on startup — caching disabled")
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
app.include_router(v2_analysis.router)
app.include_router(knowledge_graph.router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    """Lightweight liveness probe that also reports Redis reachability."""
    redis_status = "connected" if await redis_ping() else "disconnected"

    return {"status": "ok", "version": "1.0.0", "redis": redis_status}


# ── Dev entrypoint ─────────────────────────────────────────────────────────────
# Run with: uvicorn main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
