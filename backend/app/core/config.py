"""
app/core/config.py
───────────────────────────────────────────────────────────────────────────────
Centralised application configuration.

All runtime configuration is sourced from environment variables (or a `.env`
file in development) via pydantic's BaseSettings. This keeps secrets and
environment-specific values (DB credentials, JWT secret, CORS origins) out
of source code, and gives every other module a single `settings` object to
import.

Usage:
    from app.core.config import settings
    settings.DATABASE_URL
───────────────────────────────────────────────────────────────────────────────
"""

from datetime import time as time_
from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── General ────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Smart Attendance System"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"   # development | staging | production
    DEBUG: bool = True

    # ── Database (PostgreSQL) ─────────────────────────────────────────────
    POSTGRES_USER: str = "attendance_user"
    POSTGRES_PASSWORD: str = "change_me"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "attendance_db"

    # Optional: provide a full DSN directly (overrides the fields above).
    # Render provides DATABASE_URL as  postgresql://user:pass@host:port/db
    # or  postgres://...  — both are normalised to postgresql+psycopg:// below.
    DATABASE_URL: str | None = None

    # ── JWT / Security ─────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE_THIS_SECRET_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # ── CORS ────────────────────────────────────────────────────────────────
    # Stored as a plain str so pydantic-settings never attempts list-coercion
    # on the raw env value. Use the `cors_origins` property to get List[str].
    # On Render set:  BACKEND_CORS_ORIGINS=https://your-app.vercel.app
    # Multiple origins (comma-separated):
    #   BACKEND_CORS_ORIGINS=https://app.vercel.app,http://localhost:3000
    BACKEND_CORS_ORIGINS: str = ""

    # ── Logging ────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False   # True in production for structured/JSON logs

    # ── File / Object Storage (placeholders for future phases) ────────────
    MEDIA_ROOT: str = "media"          # local dir for dev; S3 bucket in prod
    EXPORTS_DIR: str = "media/exports"

    # Hostel attendance window. Values can be overridden as HH:MM[:SS].
    ATTENDANCE_TIMEZONE: str = "Asia/Kolkata"
    CHECKIN_START: time_ = time_(20, 0)
    CHECKIN_LATE: time_ = time_(21, 0)
    CHECKIN_CLOSE: time_ = time_(0, 0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── CORS helper ────────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> List[str]:
        """
        Parse BACKEND_CORS_ORIGINS env var into a list of origin strings.
        Accepts a single URL or comma-separated list:
            https://app.vercel.app
            https://app.vercel.app,http://localhost:3000
        """
        if not self.BACKEND_CORS_ORIGINS:
            return []
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """
        Build the async SQLAlchemy connection string.

        Priority:
          1. DATABASE_URL env var (set by Render's PostgreSQL add-on).
             Render provides  postgresql://...  or  postgres://...  — both
             are rewritten to  postgresql+psycopg://  which is the driver
             alias required by SQLAlchemy 2.x async with psycopg v3.
          2. Individual POSTGRES_* fields (local dev / docker-compose).

        The driver prefix MUST be  postgresql+psycopg://  — NOT asyncpg,
        NOT the bare  postgresql://  alias — because session.py uses
        create_async_engine with psycopg's async mode.
        """
        if self.DATABASE_URL:
            url = str(self.DATABASE_URL)
            # Render (and Heroku-compatible providers) hand out URLs with
            # the legacy  postgres://  or bare  postgresql://  scheme.
            # SQLAlchemy's async psycopg driver requires  postgresql+psycopg://
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            # If it already has the correct driver prefix, leave it unchanged.
            return url

        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings accessor.

    Using lru_cache ensures the .env file / environment is only parsed
    once per process, while still allowing dependency-injection overrides
    in tests via FastAPI's `app.dependency_overrides`.
    """
    return Settings()


# Module-level singleton for convenient importing: `from app.core.config import settings`
settings = get_settings()
