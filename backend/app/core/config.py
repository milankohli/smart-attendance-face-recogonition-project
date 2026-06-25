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

from pydantic import AnyHttpUrl, PostgresDsn, field_validator
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

    # Optional: provide a full DSN directly (overrides the fields above)
    DATABASE_URL: PostgresDsn | None = None

    # ── JWT / Security ─────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE_THIS_SECRET_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # ── CORS ────────────────────────────────────────────────────────────────
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

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

    # ── Validators ─────────────────────────────────────────────────────────
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _assemble_cors_origins(cls, v):
        """
        Allow CORS origins to be provided as a comma-separated string
        in the environment, e.g.:
            BACKEND_CORS_ORIGINS=http://localhost:3000,https://app.example.com
        """
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def sqlalchemy_database_uri(self) -> str:
        """
        Build the SQLAlchemy connection string.

        Uses DATABASE_URL directly if provided, otherwise assembles it
        from the individual POSTGRES_* fields. The driver is psycopg
        (postgresql+psycopg) for SQLAlchemy 2.x compatibility.
        """
        if self.DATABASE_URL:
            return str(self.DATABASE_URL)

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
