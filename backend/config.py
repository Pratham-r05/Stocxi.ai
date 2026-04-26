"""
config.py — Application configuration: env settings + YAML config loader.

Two distinct concerns:
  1. Settings (pydantic-settings): secrets and environment-specific values read from .env.
     Never hardcode these — rotate immediately if leaked.
  2. YamlConfig: static config files (sources, versions, weights, profiles) read from
     config/ directory. Loaded once at startup and shared across the application.

Required .env keys:
  REDIS_URL       — Upstash rediss:// URL
  GOOGLE_API_KEY  — Google Gemini API key

Optional .env keys:
  ALLOWED_ORIGINS — Comma-separated CORS origins (default: * for dev)
  ENVIRONMENT     — "development" | "production" (default: development)
  GOOGLE_APPLICATION_CREDENTIALS — path to Vertex AI service-account JSON
"""

from __future__ import annotations

import os as _os
from pathlib import Path
from typing import Any

import yaml as _yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Paths ─────────────────────────────────────────────────────────────────────

_BACKEND_DIR = Path(__file__).parent
_CONFIG_DIR  = _BACKEND_DIR.parent / "config"
_ENV_FILE    = _BACKEND_DIR / ".env"


# ── 1. Env Settings ───────────────────────────────────────────────────────────

class Settings(BaseSettings):
    """
    Typed environment configuration loaded from backend/.env.
    Fails fast on startup if required keys are absent.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required
    redis_url:       str
    google_api_key:  str

    # Optional with safe defaults
    environment:         str = "development"
    allowed_origins_raw: str = "*"
    newsdata_api_key:    str = ""   # newsdata.io — optional, falls back to RSS if absent

    # Google Vertex AI / Gemini
    google_base_url: str = (
        "https://us-central1-aiplatform.googleapis.com/v1beta1/"
        "projects/stocxi-analysis/locations/us-central1/endpoints/openapi/"
    )
    google_model: str = "google/gemini-2.5-pro"
    google_application_credentials: str | None = None

    @property
    def allowed_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list. '*' → allow all (dev)."""
        raw = self.allowed_origins_raw.strip()
        return ["*"] if raw == "*" else [o.strip() for o in raw.split(",")]


# Singleton — import as `from backend.config import settings`
settings = Settings()

# Propagate credentials path so google.auth.default() finds it.
if settings.google_application_credentials:
    _creds = settings.google_application_credentials
    if not _os.path.isabs(_creds):
        _creds = str((_BACKEND_DIR / _creds).resolve())
    _os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", _creds)


# ── 2. YAML Config Loader ─────────────────────────────────────────────────────

def _load_yaml(filename: str) -> dict[str, Any]:
    """
    Load a YAML file from the config/ directory.

    Args:
        filename: bare filename, e.g. "sources.yaml"

    Returns:
        Parsed dict. Never returns None — raises on parse failure.

    Raises:
        FileNotFoundError: if the file doesn't exist.
        ValueError: if the file is empty or not a valid YAML mapping.
    """
    path = _CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Required config file not found: {path}. "
            "Ensure config/ directory is present at the repo root."
        )
    with open(path, encoding="utf-8") as fh:
        data = _yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(
            f"Config file {filename} must be a YAML mapping at the top level, "
            f"got {type(data).__name__}."
        )
    return data


class YamlConfig:
    """
    Lazy-loaded, cached YAML configuration.

    All five config files are loaded once on first access and cached in-process.
    Import the module-level singleton `yaml_cfg` — do not instantiate this class directly.

    Usage:
        from backend.config import yaml_cfg
        ttl = yaml_cfg.sources["technical"][0]["ttl_seconds"]
        model_id = yaml_cfg.versions["llm"]["active"]
        w = yaml_cfg.weights["technical"]["rsi"]["short"]
        mix = yaml_cfg.profiles["category_mix"]["short"]
        bse_code = yaml_cfg.bse_codes.get("RELIANCE")
    """

    def __init__(self) -> None:
        self._sources:   dict[str, Any] | None = None
        self._versions:  dict[str, Any] | None = None
        self._weights:   dict[str, Any] | None = None
        self._profiles:  dict[str, Any] | None = None
        self._bse_codes: dict[str, Any] | None = None
        self._alt_tickers: dict[str, Any] | None = None

    # ── Accessors ──────────────────────────────────────────────────────────────

    @property
    def sources(self) -> dict[str, Any]:
        """Approved data sources, rate limits, TTLs — sources.yaml."""
        if self._sources is None:
            self._sources = _load_yaml("sources.yaml")
        return self._sources

    @property
    def versions(self) -> dict[str, Any]:
        """Pinned model IDs, prompt versions, weight versions — versions.yaml."""
        if self._versions is None:
            self._versions = _load_yaml("versions.yaml")
        return self._versions

    @property
    def weights(self) -> dict[str, Any]:
        """Signal weight table (technical + fundamental + news classes) — weights.yaml."""
        if self._weights is None:
            self._weights = _load_yaml("weights.yaml")
        return self._weights

    @property
    def profiles(self) -> dict[str, Any]:
        """User profile → category mix, risk adjustments — profiles.yaml."""
        if self._profiles is None:
            self._profiles = _load_yaml("profiles.yaml")
        return self._profiles

    @property
    def bse_codes(self) -> dict[str, str]:
        """Static NSE symbol → BSE scrip code fallback map — bse_codes.yaml."""
        if self._bse_codes is None:
            raw = _load_yaml("bse_codes.yaml")
            # bse_codes.yaml top-level may have metadata keys; filter to str:str entries
            self._bse_codes = {k: str(v) for k, v in raw.items() if isinstance(v, (str, int))}
        return self._bse_codes

    @property
    def alt_tickers(self) -> dict[str, str]:
        """NSE symbol → alternative yfinance ticker — alt_tickers.yaml."""
        if self._alt_tickers is None:
            raw = _load_yaml("alt_tickers.yaml")
            self._alt_tickers = {k: str(v) for k, v in raw.items() if isinstance(v, str)}
        return self._alt_tickers

    # ── Convenience helpers ────────────────────────────────────────────────────

    def active_model_id(self) -> str:
        """Return the pinned LLM model ID from versions.yaml."""
        return self.versions["llm"]["active"]

    def prompt_version(self) -> str:
        """Return the pinned prompt version string."""
        return self.versions["prompt_version"]

    def weight_version(self) -> str:
        """Return the current weight table version string."""
        return self.versions["weight_version"]

    def node_schema_version(self) -> int:
        """Return the current node schema version integer."""
        return int(self.versions["node_schema_version"])

    def min_nodes(self) -> dict[str, int]:
        """Return minimum node count thresholds by category."""
        return dict(self.versions.get("min_nodes", {}))

    def category_mix(self, horizon: str) -> dict[str, float]:
        """
        Return outer category weights for the given horizon.

        Args:
            horizon: "short" or "long"

        Returns:
            Dict mapping category name → float weight.

        Raises:
            KeyError: if horizon is not "short" or "long".
        """
        return dict(self.profiles["category_mix"][horizon])

    def risk_adjustments(self, risk: str) -> dict[str, float]:
        """
        Return risk adjustment multipliers for the given risk profile.

        Args:
            risk: "conservative", "moderate", or "aggressive"

        Returns:
            Dict of multiplier keys → float values.

        Raises:
            KeyError: if risk level is not recognised.
        """
        return dict(self.profiles["risk_adjustments"][risk])

    def validate_all(self) -> None:
        """
        Force-load and validate all config files.
        Call once at application startup to fail fast on misconfiguration.

        Raises:
            FileNotFoundError: if any required config file is missing.
            ValueError: if any file fails to parse as a YAML mapping.
        """
        _ = self.sources
        _ = self.versions
        _ = self.weights
        _ = self.profiles
        _ = self.bse_codes
        _ = self.alt_tickers

        # Spot-check critical keys so a truncated/corrupt file surfaces immediately.
        required_keys = {
            "sources":  ["technical", "fundamental", "news", "announcement"],
            "versions": ["llm", "prompt_version", "weight_version", "node_schema_version"],
            "weights":  ["technical", "fundamental"],
            "profiles": ["category_mix", "risk_adjustments"],
        }
        for cfg_name, keys in required_keys.items():
            cfg_data = getattr(self, cfg_name)
            for key in keys:
                if key not in cfg_data:
                    raise ValueError(
                        f"config/{cfg_name}.yaml is missing required top-level key '{key}'."
                    )


# Singleton — import as `from backend.config import yaml_cfg`
yaml_cfg = YamlConfig()
