"""
app/db/session.py
───────────────────────────────────────────────────────────────────────────────
Async SQLAlchemy engine and session factory.

Provides:
  • engine          — AsyncEngine backed by psycopg (SQLAlchemy 2.x).
  • AsyncSessionLocal — sessionmaker producing AsyncSession instances.
  • get_async_session — FastAPI dependency that yields one session per
                        request and commits/rolls back automatically.

All connection parameters are taken from `settings.sqlalchemy_database_uri`
(assembled from POSTGRES_* env vars or DATABASE_URL if set directly).

Usage in routers:
    from app.db.session import get_async_session
    from sqlalchemy.ext.asyncio import AsyncSession

    async def my_endpoint(session: AsyncSession = Depends(get_async_session)):
        ...

Usage at app startup (main.py lifespan):
    from app.db.session import engine
    from app.db.base import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # dev only; use Alembic in prod
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping=True: test connections before handing them out, preventing
# stale-connection errors after the database restarts or the TCP connection
# is dropped by an idle timeout.
#
# echo=settings.DEBUG: log every SQL statement in development — keeps the
# same behaviour as `sqlalchemy.engine` logger in logging.py but scoped
# to this engine.
engine = create_async_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    pool_size=10,          # default pool — tune per deployment
    max_overflow=20,
    pool_timeout=30,       # seconds to wait for a connection from the pool
    pool_recycle=1800,     # recycle connections every 30 min (avoids server-side timeouts)
    future=True,           # SQLAlchemy 2.x style (always True for async)
)

# ── Session factory ───────────────────────────────────────────────────────────
# expire_on_commit=False: prevents SQLAlchemy from expiring ORM objects after
# a commit so we can still access their attributes in the response serialisation
# phase without triggering extra lazy-load queries (which would fail on an
# async session anyway).
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,   # services flush manually for fine-grained control
    autocommit=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an AsyncSession for the duration of one
    HTTP request.

    Transaction lifecycle:
      • The session is opened in a try block.
      • On a clean exit the session is committed (the route's work is saved).
      • On any exception the session is rolled back so no partial writes leak.
      • The session is always closed in the finally block.

    Because `expire_on_commit=False` is set on the factory, ORM objects
    accessed after `await session.commit()` inside a service still hold
    their loaded attribute values — no lazy-load surprises.

    Note: individual service methods call `await session.flush()` (not
    commit) to write to the DB within the transaction without releasing
    the transaction boundary.  The *commit* here (in the dependency) is
    the outer commit that finalises everything once the route handler
    returns successfully.

    Callers that need to commit early (e.g. to refresh auto-generated
    fields before building a response) may do so explicitly; the
    dependency's commit becomes a no-op in that case.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Health-check helper ───────────────────────────────────────────────────────

async def check_db_connection() -> bool:
    """
    Ping the database and return True if reachable.

    Intended for use in a `/health` or `/readiness` endpoint so Kubernetes
    liveness/readiness probes can verify DB connectivity independently of
    request traffic.

    Example in main.py:
        @app.get("/health")
        async def health():
            db_ok = await check_db_connection()
            return {"status": "ok" if db_ok else "degraded", "db": db_ok}
    """
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover
        log.error("Database health check failed", extra={"ctx_error": str(exc)})
        return False
