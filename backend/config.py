"""
config.py — Typed environment configuration via pydantic-settings.

Reads from .env file so secrets never touch source code.
Fail-fast on startup if required keys are missing.

Required .env keys:
  REDIS_URL          — Upstash rediss:// URL
  OPENROUTER_API_KEY — Your OpenRouter API key

Optional:
  ALLOWED_ORIGINS    — Comma-separated CORS origins (default: * for dev)
  ENVIRONMENT        — "development" | "production" (default: development)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Required ───────────────────────────────────────────────────────────────
    redis_url: str
    openrouter_api_key: str

    # ── Optional with safe defaults ────────────────────────────────────────────
    environment: str = "development"
    allowed_origins_raw: str = "*"  # Stored as raw string; parsed below

    @property
    def allowed_origins(self) -> list[str]:
        # "*" → allow all (dev). Comma-separated list → production whitelist.
        if self.allowed_origins_raw.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins_raw.split(",")]

    # ── OpenRouter config (derived, not from env) ──────────────────────────────
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Free tier model — zero cost. Change to "anthropic/claude-sonnet-4-5" for premium.
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"


# Singleton — imported everywhere as `from config import settings`
settings = Settings()
