"""
BreatheSafe — Application Configuration
Reads settings from environment variables and .env files.
Uses pydantic-settings v2 SettingsConfigDict (replaces old class Config style).
"""

import os
import json
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env paths — try /app/.env (Docker) then the file next to this module
_HERE    = Path(__file__).parent          # app/
_APP_ENV = Path("/app/.env")             # Docker: backend/ mounted at /app
_DEV_ENV = _HERE.parent / ".env"         # local: backend/.env (if running bare)

# Pick whichever .env file actually exists; pass both so pydantic tries both
_ENV_FILES = [str(p) for p in (_APP_ENV, _DEV_ENV) if p.exists()] or [".env"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,   # SMTP_USER and smtp_user both match
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME:    str  = "BreatheSafe"
    APP_VERSION: str  = "1.0.1"
    DEBUG:       bool = False
    SECRET_KEY:  str  = ""   # Must be set via environment variable in production

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = ""   # Must be set via environment variable in production

    # ── JWT Auth ─────────────────────────────────────────────────────────────
    JWT_ALGORITHM:               str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS:   int = 7

    # ── External APIs ────────────────────────────────────────────────────────
    OPENAQ_API_KEY:     str = ""
    OPENWEATHER_API_KEY: str = ""

    # ── Email (Gmail SMTP) ───────────────────────────────────────────────────
    SMTP_HOST:     str = "smtp.gmail.com"
    SMTP_PORT:     int = 587
    SMTP_USER:     str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM:    str = "BreatheSafe <noreply@breathesafe.in>"

    # ── Scheduler ────────────────────────────────────────────────────────────
    AQI_FETCH_INTERVAL_MINUTES:   int = 60
    ALERT_CHECK_INTERVAL_MINUTES: int = 30

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
    ]

    # ── Data ─────────────────────────────────────────────────────────────────
    DATA_DIR:   str = "/app/data"
    MODELS_DIR: str = "/app/ml/models"

    # ── CORS validator — handles all formats Render/cloud envs might send ────
    # Render stores env vars as plain strings. pydantic-settings v2 JSON-parses
    # List fields, but if parsing fails it silently falls back to the default
    # (localhost-only), blocking every browser request from the Vercel frontend.
    # This validator handles:
    #   ["https://app.vercel.app"]          — JSON array string
    #   https://app.vercel.app              — bare URL (single origin)
    #   https://a.vercel.app,https://b.com  — comma-separated
    #   *                                   — wildcard (allow all)
    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            # Strip surrounding single or double quotes that shells/Render may add
            # e.g. '["https://app.vercel.app"]' → ["https://app.vercel.app"]
            if (v.startswith("'") and v.endswith("'")) or \
               (v.startswith('"') and v.endswith('"')):
                v = v[1:-1].strip()
            # Try JSON parse first
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(o).strip() for o in parsed]
                except json.JSONDecodeError:
                    pass
            # Comma-separated or single value
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # ── Hard fallback: read SMTP vars directly from OS env if still blank ────
    # This guarantees credentials load even if pydantic's .env parsing fails
    # (e.g. special characters in EMAIL_FROM confuse some parsers).
    @field_validator("SMTP_USER", mode="before")
    @classmethod
    def _smtp_user_fallback(cls, v: str) -> str:
        return v or os.environ.get("SMTP_USER", "")

    @field_validator("SMTP_PASSWORD", mode="before")
    @classmethod
    def _smtp_password_fallback(cls, v: str) -> str:
        return v or os.environ.get("SMTP_PASSWORD", "")

    @field_validator("EMAIL_FROM", mode="before")
    @classmethod
    def _email_from_fallback(cls, v: str) -> str:
        return v or os.environ.get("EMAIL_FROM", "BreatheSafe <noreply@breathesafe.in>")


settings = Settings()
